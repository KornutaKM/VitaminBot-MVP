import json
from pathlib import Path
from typing import cast

import pytest

from vitaminbot.recognition import (
    EXTRACTION_SCHEMA_VERSION,
    AcquisitionMethod,
    AmbiguityCode,
    ConfidenceBand,
    ConfidenceMetadata,
    CorrectionRecord,
    DownstreamEligibility,
    ExplicitEquivalentObservation,
    FieldConfirmationState,
    FieldObservation,
    LabelExtraction,
    LabelRowObservation,
    PresenceState,
    ProductIdentityObservation,
    RecognitionValidationError,
    RecordState,
    SemanticState,
    SourceAsset,
    SourceKind,
    SourceRegion,
    record_transition_allowed,
    require_record_transition,
    validate_extraction_payload,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "recognition"


def _load_fixture(name: str) -> dict[str, object]:
    raw = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


@pytest.mark.parametrize(
    "name",
    [
        "magnesium_b6.json",
        "vitamin_d_iu.json",
        "omega3_epa_dha.json",
        "ambiguous_magnesium_citrate.json",
        "conflicting_observations.json",
        "missing_serving_information.json",
    ],
)
def test_golden_fixtures_validate_against_versioned_contract(
    name: str,
) -> None:
    extraction = validate_extraction_payload(_load_fixture(name))

    assert extraction.schema_version == EXTRACTION_SCHEMA_VERSION
    assert extraction.to_payload()["schema_version"] == EXTRACTION_SCHEMA_VERSION


def test_ambiguous_magnesium_fixture_fails_closed_without_elemental_amount() -> None:
    extraction = validate_extraction_payload(_load_fixture("ambiguous_magnesium_citrate.json"))

    assert extraction.record_state is RecordState.USER_RESOLUTION_REQUIRED
    assert extraction.requires_user_resolution is True
    assert extraction.record_ambiguities == (AmbiguityCode.COMPOUND_VS_ELEMENTAL_UNCLEAR,)
    assert len(extraction.rows) == 1

    row = extraction.rows[0]
    assert row.row_raw_text == "Magnesium Citrate 500 mg"
    assert row.elemental_or_equivalent is None
    assert row.semantic_state is SemanticState.UNRESOLVED
    assert row.downstream_eligibility is DownstreamEligibility.BLOCKED_UNRESOLVED


def test_vitamin_d_fixture_preserves_iu_without_mass_conversion() -> None:
    extraction = validate_extraction_payload(_load_fixture("vitamin_d_iu.json"))

    row = extraction.rows[0]
    assert row.quantity is not None
    assert row.unit is not None
    assert row.quantity.raw_text == "1000"
    assert row.unit.raw_text == "IU"
    assert row.unit.normalized_candidate == "IU"


def test_omega3_fixture_keeps_fish_oil_epa_and_dha_as_separate_rows() -> None:
    extraction = validate_extraction_payload(_load_fixture("omega3_epa_dha.json"))

    names = [row.printed_name.raw_text for row in extraction.rows]
    assert names == [
        "Fish Oil",
        "Total Omega-3 Fatty Acids",
        "EPA",
        "DHA",
    ]
    assert all(row.elemental_or_equivalent is None for row in extraction.rows)


def test_conflicting_observations_preserve_both_values_without_auto_selection() -> None:
    extraction = validate_extraction_payload(_load_fixture("conflicting_observations.json"))

    assert extraction.record_state is RecordState.USER_RESOLUTION_REQUIRED
    assert extraction.requires_user_resolution is True
    assert extraction.record_ambiguities == (AmbiguityCode.CONFLICTING_OBSERVATIONS,)
    assert [row.row_raw_text for row in extraction.rows] == ["Zinc 15 mg", "Zinc 10 mg"]

    quantities = []
    region_ids = []
    for row in extraction.rows:
        assert row.quantity is not None
        assert row.semantic_state is SemanticState.UNRESOLVED
        assert row.downstream_eligibility is DownstreamEligibility.BLOCKED_UNRESOLVED
        quantities.append(row.quantity.raw_text)
        region_ids.extend(region.region_id for region in row.quantity.source_regions)

    assert quantities == ["15", "10"]
    assert len(set(region_ids)) == 2
    assert all(
        row.printed_name.confirmation_state is FieldConfirmationState.UNCONFIRMED
        for row in extraction.rows
    )


def test_missing_serving_remains_unresolved_without_inference() -> None:
    extraction = validate_extraction_payload(_load_fixture("missing_serving_information.json"))

    assert extraction.record_state is RecordState.USER_RESOLUTION_REQUIRED
    assert extraction.requires_user_resolution is True
    assert extraction.record_ambiguities == (AmbiguityCode.MISSING_SERVING_INFORMATION,)
    assert extraction.serving is not None
    assert extraction.serving.serving_size.presence_state is PresenceState.NOT_VISIBLE
    assert extraction.serving.serving_size.raw_text is None
    assert extraction.serving.serving_size.normalized_candidate is None
    assert extraction.serving.serving_basis is None

    row = extraction.rows[0]
    assert row.row_raw_text == "Vitamin C 250 mg"
    assert row.quantity is not None
    assert row.quantity.raw_text == "250"
    assert row.semantic_state is SemanticState.UNRESOLVED
    assert row.downstream_eligibility is DownstreamEligibility.BLOCKED_UNRESOLVED


def test_high_confidence_never_auto_confirms_field() -> None:
    observation = FieldObservation(
        field_id="row:magnesium:quantity",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="200",
        normalized_candidate="200",
        confidence=ConfidenceMetadata(band=ConfidenceBand.HIGH),
    )

    assert observation.confirmation_state is FieldConfirmationState.UNCONFIRMED
    assert observation.needs_attention is False


def test_low_confidence_routes_attention_but_does_not_guess() -> None:
    observation = FieldObservation(
        field_id="row:b12:unit",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="µg",
        normalized_candidate=None,
        confidence=ConfidenceMetadata(band=ConfidenceBand.LOW),
        ambiguity_codes=(AmbiguityCode.UNIT_UNCLEAR,),
        semantic_state=SemanticState.UNRESOLVED,
        downstream_eligibility=(DownstreamEligibility.BLOCKED_UNRESOLVED),
    )

    assert observation.needs_attention is True
    assert observation.confirmation_state is FieldConfirmationState.UNCONFIRMED
    assert observation.normalized_candidate is None


def test_present_field_requires_raw_source_text() -> None:
    with pytest.raises(RecognitionValidationError):
        FieldObservation(
            field_id="row:missing",
            source_kind=SourceKind.LABEL_IMAGE,
            presence_state=PresenceState.PRESENT,
            raw_text=None,
        )


def test_semantically_unresolved_field_cannot_be_downstream_candidate() -> None:
    with pytest.raises(RecognitionValidationError):
        FieldObservation(
            field_id="row:ambiguous",
            source_kind=SourceKind.LABEL_IMAGE,
            presence_state=PresenceState.PRESENT,
            raw_text="Magnesium citrate 500 mg",
            semantic_state=SemanticState.UNRESOLVED,
            downstream_eligibility=(DownstreamEligibility.CANDIDATE_FOR_NORMALIZATION),
        )


def test_rejected_field_cannot_remain_downstream_normalization_candidate() -> None:
    with pytest.raises(RecognitionValidationError):
        FieldObservation(
            field_id="row:rejected",
            source_kind=SourceKind.LABEL_IMAGE,
            presence_state=PresenceState.PRESENT,
            raw_text="15",
            normalized_candidate="15",
            confirmation_state=FieldConfirmationState.REJECTED,
            downstream_eligibility=DownstreamEligibility.CANDIDATE_FOR_NORMALIZATION,
        )


def test_rejected_field_routes_attention_when_blocked() -> None:
    observation = FieldObservation(
        field_id="row:rejected",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="15",
        normalized_candidate="15",
        confirmation_state=FieldConfirmationState.REJECTED,
        downstream_eligibility=DownstreamEligibility.BLOCKED_UNRESOLVED,
    )

    assert observation.needs_attention is True


def test_user_corrected_field_requires_correction_history() -> None:
    with pytest.raises(RecognitionValidationError):
        FieldObservation(
            field_id="row:corrected",
            source_kind=SourceKind.MANUAL_INPUT,
            presence_state=PresenceState.PRESENT,
            raw_text="250 µg",
            confirmation_state=(FieldConfirmationState.USER_CORRECTED),
        )


def test_correction_history_preserves_original_observation() -> None:
    observation = FieldObservation(
        field_id="row:corrected",
        source_kind=SourceKind.MANUAL_INPUT,
        presence_state=PresenceState.PRESENT,
        raw_text="250 µg",
        normalized_candidate="250 µg",
        confirmation_state=(FieldConfirmationState.USER_CORRECTED),
        corrections=(
            CorrectionRecord(
                original_raw_text="250 mg",
                corrected_raw_text="250 µg",
                corrected_at="2026-09-20T06:00:00Z",
            ),
        ),
    )

    payload = observation.to_payload()
    assert payload["corrections"] == [
        {
            "original_raw_text": "250 mg",
            "corrected_raw_text": "250 µg",
            "corrected_at": "2026-09-20T06:00:00Z",
        }
    ]


def test_explicit_equivalent_requires_visible_relationship_evidence() -> None:
    subject = FieldObservation(
        field_id="equivalent:subject",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="magnesium",
    )
    quantity = FieldObservation(
        field_id="equivalent:quantity",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="80",
    )
    unit = FieldObservation(
        field_id="equivalent:unit",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="mg",
    )

    explicit = ExplicitEquivalentObservation(
        relationship_text="providing magnesium 80 mg",
        subject=subject,
        quantity=quantity,
        unit=unit,
    )

    assert explicit.relationship_text == "providing magnesium 80 mg"


def test_compound_vs_elemental_ambiguity_cannot_coexist_with_explicit_equivalent() -> None:
    subject = FieldObservation(
        field_id="equivalent:subject",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="magnesium",
    )
    quantity = FieldObservation(
        field_id="equivalent:quantity",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="80",
    )
    unit = FieldObservation(
        field_id="equivalent:unit",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="mg",
    )
    explicit = ExplicitEquivalentObservation(
        relationship_text="providing magnesium 80 mg",
        subject=subject,
        quantity=quantity,
        unit=unit,
    )

    with pytest.raises(RecognitionValidationError):
        LabelRowObservation(
            row_id="row:magnesium",
            row_raw_text=("Magnesium citrate 500 mg, providing magnesium 80 mg"),
            printed_name=FieldObservation(
                field_id="row:magnesium:name",
                source_kind=SourceKind.LABEL_IMAGE,
                presence_state=PresenceState.PRESENT,
                raw_text="Magnesium citrate",
            ),
            elemental_or_equivalent=explicit,
            ambiguity_codes=(AmbiguityCode.COMPOUND_VS_ELEMENTAL_UNCLEAR,),
            semantic_state=SemanticState.UNRESOLVED,
            downstream_eligibility=(DownstreamEligibility.BLOCKED_UNRESOLVED),
        )


def test_ready_for_confirmation_cannot_hide_low_confidence_field() -> None:
    low_confidence_name = FieldObservation(
        field_id="product_name",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="Example",
        confidence=ConfidenceMetadata(band=ConfidenceBand.LOW),
    )

    with pytest.raises(RecognitionValidationError):
        LabelExtraction(
            extraction_id="extraction:low-confidence",
            acquisition_method=AcquisitionMethod.PHOTO,
            source_assets=(
                SourceAsset(
                    asset_id="img:1",
                    source_kind=SourceKind.LABEL_IMAGE,
                    reference="fixture://low-confidence",
                ),
            ),
            raw_label_text="Example",
            product_identity=ProductIdentityObservation(product_name=low_confidence_name),
            rows=(),
            record_state=(RecordState.READY_FOR_USER_CONFIRMATION),
        )


def test_accepted_record_requires_explicit_confirmation_revision_and_fields() -> None:
    product_name = FieldObservation(
        field_id="product_name",
        source_kind=SourceKind.MANUAL_INPUT,
        presence_state=PresenceState.PRESENT,
        raw_text="Example",
    )

    with pytest.raises(RecognitionValidationError):
        LabelExtraction(
            extraction_id="extraction:not-confirmed",
            acquisition_method=AcquisitionMethod.MANUAL,
            source_assets=(
                SourceAsset(
                    asset_id="manual:1",
                    source_kind=SourceKind.MANUAL_INPUT,
                    reference="manual://entry",
                ),
            ),
            raw_label_text="Example",
            product_identity=ProductIdentityObservation(product_name=product_name),
            rows=(),
            record_state=RecordState.ACCEPTED_FOR_STORAGE,
            confirmation_revision=1,
        )


def test_accepted_record_rejects_rejected_field_even_when_downstream_blocked() -> None:
    rejected_product_name = FieldObservation(
        field_id="product_name",
        source_kind=SourceKind.MANUAL_INPUT,
        presence_state=PresenceState.PRESENT,
        raw_text="Rejected Example",
        normalized_candidate="Rejected Example",
        confirmation_state=FieldConfirmationState.REJECTED,
        downstream_eligibility=DownstreamEligibility.BLOCKED_UNRESOLVED,
    )

    with pytest.raises(RecognitionValidationError):
        LabelExtraction(
            extraction_id="extraction:rejected-field",
            acquisition_method=AcquisitionMethod.MANUAL,
            source_assets=(
                SourceAsset(
                    asset_id="manual:1",
                    source_kind=SourceKind.MANUAL_INPUT,
                    reference="manual://entry",
                ),
            ),
            raw_label_text="Rejected Example",
            product_identity=ProductIdentityObservation(product_name=rejected_product_name),
            rows=(),
            record_state=RecordState.ACCEPTED_FOR_STORAGE,
            confirmation_revision=1,
        )


def test_photo_field_region_must_reference_known_source_asset() -> None:
    product_name = FieldObservation(
        field_id="product_name",
        source_kind=SourceKind.LABEL_IMAGE,
        presence_state=PresenceState.PRESENT,
        raw_text="Example",
        source_regions=(
            SourceRegion(
                asset_id="img:missing",
                region_id="region:1",
                bbox=(0.1, 0.1, 0.8, 0.2),
            ),
        ),
    )

    with pytest.raises(RecognitionValidationError):
        LabelExtraction(
            extraction_id="extraction:bad-region",
            acquisition_method=AcquisitionMethod.PHOTO,
            source_assets=(
                SourceAsset(
                    asset_id="img:1",
                    source_kind=SourceKind.LABEL_IMAGE,
                    reference="fixture://known",
                ),
            ),
            raw_label_text="Example",
            product_identity=ProductIdentityObservation(product_name=product_name),
            rows=(),
            record_state=RecordState.EXTRACTED_UNCONFIRMED,
        )


def test_schema_version_is_rejected_when_unknown() -> None:
    payload = _load_fixture("vitamin_d_iu.json")
    payload["schema_version"] = "99.0.0"

    with pytest.raises(RecognitionValidationError):
        validate_extraction_payload(payload)


def test_confirmation_state_machine_allows_review_then_acceptance() -> None:
    assert record_transition_allowed(
        RecordState.EXTRACTED_UNCONFIRMED,
        RecordState.READY_FOR_USER_CONFIRMATION,
    )
    assert record_transition_allowed(
        RecordState.READY_FOR_USER_CONFIRMATION,
        RecordState.ACCEPTED_FOR_STORAGE,
    )
    require_record_transition(
        RecordState.READY_FOR_USER_CONFIRMATION,
        RecordState.ACCEPTED_FOR_STORAGE,
    )


def test_confirmation_state_machine_rejects_silent_auto_accept() -> None:
    assert not record_transition_allowed(
        RecordState.EXTRACTED_UNCONFIRMED,
        RecordState.ACCEPTED_FOR_STORAGE,
    )
    with pytest.raises(RecognitionValidationError):
        require_record_transition(
            RecordState.EXTRACTED_UNCONFIRMED,
            RecordState.ACCEPTED_FOR_STORAGE,
        )
