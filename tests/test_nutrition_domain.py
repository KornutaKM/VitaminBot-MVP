from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from vitaminbot.domain import (
    AmountBasis,
    AmountRecord,
    CandidateResolution,
    CandidateState,
    ConfirmationState,
    ConsumedIntakeEvent,
    Derivation,
    DomainValidationError,
    EntityCandidate,
    EvidenceStatus,
    IntakePlan,
    Jurisdiction,
    PlannedIntakeEvent,
    ProductFormulationVersion,
    ProductIdentity,
    QuantityBasis,
    ResolutionStatus,
    ScientificResolutionState,
    ServingDefinition,
    SourceRecord,
    SourceType,
    SubjectKind,
    TrackedSupplementInstance,
    Unit,
    UnitDimension,
    canonical_unit_for_dimension,
    unit_dimension,
)


SOURCE_ID = "label:example:v1"
PORTION_ID = "basis:portion"
CAPSULE_ID = "consumption-unit:capsule"


def test_magnesium_compound_mass_and_elemental_magnesium_are_distinct() -> None:
    compound = AmountRecord(
        amount_id="amount:magnesium-citrate",
        subject_kind=SubjectKind.INGREDIENT,
        subject_id="ingredient:magnesium-citrate",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal("500"),
        unit=Unit.MILLIGRAM,
        amount_basis=AmountBasis.INGREDIENT_COMPOUND,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
    )
    elemental = AmountRecord(
        amount_id="amount:elemental-magnesium",
        subject_kind=SubjectKind.ANALYTE,
        subject_id="analyte:magnesium",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal("100"),
        unit=Unit.MILLIGRAM,
        amount_basis=AmountBasis.ELEMENTAL,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
    )

    assert compound.subject_id != elemental.subject_id
    assert compound.amount_basis is AmountBasis.INGREDIENT_COMPOUND
    assert elemental.amount_basis is AmountBasis.ELEMENTAL


def test_compound_amount_cannot_be_labeled_as_elemental_analyte_amount() -> None:
    with pytest.raises(DomainValidationError):
        AmountRecord(
            amount_id="amount:invalid",
            subject_kind=SubjectKind.INGREDIENT,
            subject_id="ingredient:magnesium-citrate",
            source_id=SOURCE_ID,
            resolution_status=ResolutionStatus.RESOLVED,
            evidence_status=EvidenceStatus.DECLARED,
            value=Decimal("500"),
            unit=Unit.MILLIGRAM,
            amount_basis=AmountBasis.ELEMENTAL,
            quantity_basis=QuantityBasis.PER_LABEL_PORTION,
            quantity_basis_id=PORTION_ID,
        )


def test_unresolved_compound_only_magnesium_is_not_numeric_elemental_intake() -> None:
    unresolved = AmountRecord(
        amount_id="amount:magnesium-unresolved",
        subject_kind=SubjectKind.INGREDIENT,
        subject_id="ingredient:magnesium-citrate",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.AMBIGUOUS,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal("500"),
        unit=Unit.MILLIGRAM,
        amount_basis=AmountBasis.INGREDIENT_COMPOUND,
        quantity_basis=None,
        raw_text="Magnesium citrate 500 mg",
    )

    assert unresolved.deterministically_usable is False


def test_vitamin_d_iu_has_no_generic_mass_canonicalization() -> None:
    assert unit_dimension(Unit.INTERNATIONAL_UNIT) is UnitDimension.ACTIVITY
    assert unit_dimension(Unit.MICROGRAM) is UnitDimension.MASS
    assert canonical_unit_for_dimension(UnitDimension.ACTIVITY) is None
    assert canonical_unit_for_dimension(UnitDimension.MASS) is Unit.MICROGRAM


def test_fish_oil_material_is_not_epa_or_dha() -> None:
    fish_oil = AmountRecord(
        amount_id="amount:fish-oil",
        subject_kind=SubjectKind.INGREDIENT,
        subject_id="ingredient:fish-oil",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal("1000"),
        unit=Unit.MILLIGRAM,
        amount_basis=AmountBasis.MATERIAL,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
    )
    epa = AmountRecord(
        amount_id="amount:epa",
        subject_kind=SubjectKind.ANALYTE,
        subject_id="analyte:epa",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal("180"),
        unit=Unit.MILLIGRAM,
        amount_basis=AmountBasis.ANALYTE,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
    )
    dha = AmountRecord(
        amount_id="amount:dha",
        subject_kind=SubjectKind.ANALYTE,
        subject_id="analyte:dha",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal("120"),
        unit=Unit.MILLIGRAM,
        amount_basis=AmountBasis.ANALYTE,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
    )

    assert fish_oil.subject_kind is SubjectKind.INGREDIENT
    assert {epa.subject_id, dha.subject_id} == {"analyte:epa", "analyte:dha"}
    assert fish_oil.value != epa.value + dha.value


def test_consumption_unit_portion_and_daily_portion_are_distinct_bases() -> None:
    per_capsule = ServingDefinition(
        basis_id="basis:capsule",
        basis_type=QuantityBasis.PER_CONSUMPTION_UNIT,
        label_text="per capsule",
        source_id=SOURCE_ID,
        basis_quantity=Decimal("1"),
        basis_unit=Unit.COUNT,
        consumption_unit_id=CAPSULE_ID,
    )
    per_serving = ServingDefinition(
        basis_id="basis:serving",
        basis_type=QuantityBasis.PER_LABEL_PORTION,
        label_text="serving: 2 capsules",
        source_id=SOURCE_ID,
        basis_quantity=Decimal("2"),
        basis_unit=Unit.COUNT,
        consumption_unit_id=CAPSULE_ID,
    )
    daily_portion = ServingDefinition(
        basis_id="basis:daily",
        basis_type=QuantityBasis.PER_RECOMMENDED_DAILY_PORTION,
        label_text="recommended daily portion: 3 capsules",
        source_id=SOURCE_ID,
        basis_quantity=Decimal("3"),
        basis_unit=Unit.COUNT,
        consumption_unit_id=CAPSULE_ID,
    )

    assert len({per_capsule.basis_type, per_serving.basis_type, daily_portion.basis_type}) == 3


def test_plan_can_contain_multiple_daily_events_without_becoming_label_recommendation() -> None:
    plan = IntakePlan(
        plan_id="plan:1",
        tracked_instance_id="instance:1",
        version="1",
        events=(
            PlannedIntakeEvent(
                event_id="event:morning",
                consumption_unit_id=CAPSULE_ID,
                consumption_units=Decimal("1"),
                schedule_label="morning",
            ),
            PlannedIntakeEvent(
                event_id="event:evening",
                consumption_unit_id=CAPSULE_ID,
                consumption_units=Decimal("1"),
                schedule_label="evening",
            ),
        ),
    )

    assert len(plan.events) == 2
    assert all(isinstance(event, PlannedIntakeEvent) for event in plan.events)


def test_unknown_quantity_serializes_as_none_not_zero() -> None:
    unknown = AmountRecord(
        amount_id="amount:unknown",
        subject_kind=SubjectKind.ANALYTE,
        subject_id="analyte:vitamin-d",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.UNKNOWN,
        evidence_status=EvidenceStatus.UNKNOWN,
        raw_text="Vitamin D amount unreadable",
    )

    payload = unknown.to_payload()

    assert payload["value"] is None
    assert payload["unit"] is None
    assert payload["resolution_status"] == "unknown"


def test_derived_amount_requires_versioned_rule_provenance() -> None:
    with pytest.raises(DomainValidationError):
        AmountRecord(
            amount_id="amount:derived",
            subject_kind=SubjectKind.ANALYTE,
            subject_id="analyte:vitamin-d",
            source_id=SOURCE_ID,
            resolution_status=ResolutionStatus.RESOLVED,
            evidence_status=EvidenceStatus.DERIVED,
            value=Decimal("25"),
            unit=Unit.MICROGRAM,
            amount_basis=AmountBasis.ANALYTE,
            quantity_basis=QuantityBasis.PER_LABEL_PORTION,
            quantity_basis_id=PORTION_ID,
        )


def test_derived_amount_retains_input_and_rule_lineage() -> None:
    derivation = Derivation(
        rule_id="conversion:example",
        rule_version="1",
        authority_source_id="source:authority",
        input_amount_ids=("amount:raw",),
    )
    derived = AmountRecord(
        amount_id="amount:derived",
        subject_kind=SubjectKind.ANALYTE,
        subject_id="analyte:example",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DERIVED,
        value=Decimal("25"),
        unit=Unit.MICROGRAM,
        amount_basis=AmountBasis.ANALYTE,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
        derivation=derivation,
    )

    payload = derived.to_payload()
    assert payload["derivation"] == {
        "rule_id": "conversion:example",
        "rule_version": "1",
        "authority_source_id": "source:authority",
        "input_amount_ids": ["amount:raw"],
    }


def test_equivalent_amount_requires_explicit_equivalence_basis() -> None:
    with pytest.raises(DomainValidationError):
        AmountRecord(
            amount_id="amount:equivalent",
            subject_kind=SubjectKind.ANALYTE,
            subject_id="analyte:example",
            source_id=SOURCE_ID,
            resolution_status=ResolutionStatus.RESOLVED,
            evidence_status=EvidenceStatus.DECLARED,
            value=Decimal("1"),
            unit=Unit.MICROGRAM,
            amount_basis=AmountBasis.EQUIVALENT,
            quantity_basis=QuantityBasis.PER_LABEL_PORTION,
            quantity_basis_id=PORTION_ID,
        )


def test_unknown_market_jurisdiction_is_explicit_without_fabricated_default() -> None:
    product = ProductIdentity(
        product_id="product:unknown-market",
        name="Unknown-market product",
        market_jurisdiction_status=ResolutionStatus.UNKNOWN,
    )

    payload = product.to_payload()

    assert payload["market_jurisdiction_status"] == "unknown"
    assert payload["market_jurisdiction"] is None


def test_resolved_market_jurisdiction_requires_value() -> None:
    with pytest.raises(DomainValidationError):
        ProductIdentity(
            product_id="product:invalid-resolved-market",
            name="Invalid",
            market_jurisdiction_status=ResolutionStatus.RESOLVED,
        )


def test_unresolved_market_jurisdiction_rejects_guessed_value() -> None:
    with pytest.raises(DomainValidationError):
        ProductIdentity(
            product_id="product:invalid-guessed-market",
            name="Invalid",
            market_jurisdiction_status=ResolutionStatus.AMBIGUOUS,
            market_jurisdiction=Jurisdiction(code="EU"),
        )


def test_canonical_formulation_tracked_instance_and_plan_are_separate_entities() -> None:
    product = ProductIdentity(
        product_id="product:1",
        name="Example",
        market_jurisdiction_status=ResolutionStatus.RESOLVED,
        market_jurisdiction=Jurisdiction(code="EU"),
    )
    formulation = ProductFormulationVersion(
        formulation_id="formulation:1:v1",
        product_id=product.product_id,
        version="1",
        source_ids=(SOURCE_ID,),
    )
    instance = TrackedSupplementInstance(
        instance_id="instance:1",
        formulation_id=formulation.formulation_id,
        container_label="opened bottle",
    )
    plan = IntakePlan(
        plan_id="plan:1",
        tracked_instance_id=instance.instance_id,
        version="1",
        events=(),
    )

    assert product.product_id != formulation.formulation_id
    assert formulation.formulation_id != instance.instance_id
    assert plan.tracked_instance_id == instance.instance_id


def test_planned_event_does_not_imply_consumed_event() -> None:
    planned = PlannedIntakeEvent(
        event_id="event:planned",
        consumption_unit_id=CAPSULE_ID,
        consumption_units=Decimal("1"),
        schedule_label="morning",
    )
    consumed = ConsumedIntakeEvent(
        event_id="event:consumed",
        tracked_instance_id="instance:1",
        consumption_unit_id=CAPSULE_ID,
        consumption_units=Decimal("1"),
        consumed_at=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
        confirmation_source_id="source:user-confirmation",
    )

    assert planned.event_id != consumed.event_id
    assert not hasattr(planned, "consumed_at")


def test_duplicate_candidates_are_retained_after_confirmation() -> None:
    first = EntityCandidate(
        candidate_id="candidate:1",
        canonical_entity_id="formulation:a",
        source_id="source:ocr",
    )
    second = EntityCandidate(
        candidate_id="candidate:2",
        canonical_entity_id="formulation:b",
        source_id="source:catalog",
        state=CandidateState.ACTIVE,
    )
    resolution = CandidateResolution(
        candidate_set_id="candidate-set:1",
        candidates=(first, second),
        confirmation_state=ConfirmationState.CONFIRMED,
        scientific_resolution_state=ScientificResolutionState.UNRESOLVED,
        selected_candidate_id=first.candidate_id,
    )

    assert len(resolution.candidates) == 2
    assert {candidate.candidate_id for candidate in resolution.candidates} == {
        "candidate:1",
        "candidate:2",
    }


def test_unconfirmed_candidate_resolution_cannot_select_candidate() -> None:
    candidate = EntityCandidate(
        candidate_id="candidate:unconfirmed",
        canonical_entity_id="formulation:a",
        source_id="source:ocr",
    )

    with pytest.raises(DomainValidationError):
        CandidateResolution(
            candidate_set_id="candidate-set:unconfirmed",
            candidates=(candidate,),
            confirmation_state=ConfirmationState.UNCONFIRMED,
            selected_candidate_id=candidate.candidate_id,
        )


def test_confirmed_candidate_resolution_cannot_select_excluded_candidate() -> None:
    excluded = EntityCandidate(
        candidate_id="candidate:excluded",
        canonical_entity_id="formulation:excluded",
        source_id="source:catalog",
        state=CandidateState.EXCLUDED,
    )

    with pytest.raises(DomainValidationError):
        CandidateResolution(
            candidate_set_id="candidate-set:excluded",
            candidates=(excluded,),
            confirmation_state=ConfirmationState.CONFIRMED,
            scientific_resolution_state=ScientificResolutionState.UNRESOLVED,
            selected_candidate_id=excluded.candidate_id,
        )


def test_source_serialization_preserves_version_and_supersession() -> None:
    source = SourceRecord(
        source_id="efsa:example:v2",
        authority="EFSA",
        source_type=SourceType.EFSA_OPINION,
        title="Example opinion",
        stable_identifier="doi:example",
        version="2",
        retrieved_on=date(2026, 9, 20),
        jurisdiction=Jurisdiction(code="EU"),
        published_on=date(2026, 1, 14),
        locator="Section 5",
        supersedes_source_id="efsa:example:v1",
    )

    payload = source.to_payload()

    assert payload["version"] == "2"
    assert payload["jurisdiction"] == {"code": "EU", "parent_code": None}
    assert payload["supersedes_source_id"] == "efsa:example:v1"
