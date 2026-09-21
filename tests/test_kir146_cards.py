from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from vitaminbot.application.kir146 import (
    CardContext,
    CardStatus,
    KIR146Controller,
    NutrientCardRenderer,
)
from vitaminbot.domain import (
    AmountBasis,
    LifeStage,
    QuantityBasis,
    SexApplicability,
    SubjectKind,
    Unit,
)
from vitaminbot.nutrition.card_content import (
    APPROVED_CARD_CONTENT,
    ApprovedClaim,
    CardContentRegistry,
    ClaimType,
    ContentLifecycle,
)
from vitaminbot.nutrition.normalization import ComputationTrace, ComputedAmount
from vitaminbot.nutrition.reference_values import (
    EU_EFSA_REFERENCE_DATASET,
    DHAForm,
    ExposureBasis,
    ExposureContext,
    ExposureCoverage,
    PopulationProfile,
    ReferenceDataset,
    ReferenceType,
    SourceClass,
    SourceLifecycle,
)
from vitaminbot.telegram.bot import build_application


def _profile(
    *,
    age_months: int | None = 360,
    sex: SexApplicability | None = SexApplicability.FEMALE,
    life_stage: LifeStage | None = LifeStage.GENERAL,
) -> PopulationProfile:
    return PopulationProfile(
        age_months=age_months,
        sex=sex,
        life_stage=life_stage,
    )


def _context(
    revision: str,
    *,
    profile: PopulationProfile | None = None,
    exposure: ExposureContext | None = None,
    phytate: str | None = None,
    minimal_cutaneous_synthesis: bool | None = None,
    amount: ComputedAmount | None = None,
    jurisdiction: str = "EU",
    locale: str = "en",
    medication_context_material: bool = False,
    medication_rule_available: bool | None = None,
    presentation_hint: str | None = None,
) -> CardContext:
    return CardContext(
        profile=profile or _profile(),
        exposure=exposure or ExposureContext(),
        jurisdiction=jurisdiction,
        context_revision=revision,
        locale=locale,
        dietary_phytate_mg_per_day=Decimal(phytate) if phytate is not None else None,
        minimal_cutaneous_synthesis=minimal_cutaneous_synthesis,
        confirmed_amount=amount,
        medication_context_material=medication_context_material,
        medication_rule_available=medication_rule_available,
        presentation_hint=presentation_hint,
    )


def _total_exposure() -> ExposureContext:
    return ExposureContext(exposure_basis=ExposureBasis.TOTAL_INTAKE)


def _dietary_exposure() -> ExposureContext:
    return ExposureContext(exposure_basis=ExposureBasis.DIETARY_TOTAL)


def _qualifying_dha_exposure(
    *,
    epa: str | None = "100",
    dha: str | None = "500",
    source_class: SourceClass | None = SourceClass.ALGAL_OIL,
) -> ExposureContext:
    return ExposureContext(
        exposure_basis=ExposureBasis.SUPPLEMENTAL_OR_ADDED_DHA,
        source_class=source_class,
        dha_form=DHAForm.TRIACYLGLYCEROL,
        epa_mg_per_day=Decimal(epa) if epa is not None else None,
        dha_mg_per_day=Decimal(dha) if dha is not None else None,
        coverage=ExposureCoverage.COMPLETE_QUALIFYING,
        amount_includes_background_dietary_dha=False,
    )


def _amount(
    *,
    subject_id: str,
    value: str,
    unit: Unit,
    amount_basis: AmountBasis = AmountBasis.ANALYTE,
    equivalence_basis: str | None = None,
) -> ComputedAmount:
    return ComputedAmount(
        subject_kind=SubjectKind.ANALYTE,
        subject_id=subject_id,
        value=Decimal(value),
        unit=unit,
        amount_basis=amount_basis,
        quantity_basis=QuantityBasis.PER_DAY,
        source_quantity_basis_ids=(),
        source_amount_ids=("amount:kir146-test",),
        source_ids=("source:kir146-test",),
        traces=(
            ComputationTrace(
                operation="kir146_test_fixture",
                rule_id="kir146",
                rule_version="1",
            ),
        ),
        equivalence_basis=equivalence_basis,
    )


def _reference(render: object, reference_type: ReferenceType) -> object:
    binding = render.binding
    assert binding is not None
    matches = tuple(
        snapshot
        for snapshot in binding.references
        if snapshot.reference_type == reference_type.value
    )
    assert matches
    return matches[-1]


def _record_ids(render: object) -> set[str]:
    binding = render.binding
    assert binding is not None
    return {snapshot.record_id for snapshot in binding.references if snapshot.record_id is not None}


def test_static_copy_cannot_own_scientific_measurement() -> None:
    with pytest.raises(
        ValueError,
        match="must not own a daily reference/safety measurement",
    ):
        ApprovedClaim(
            claim_id="invalid.numeric-copy",
            claim_type=ClaimType.LIMITATION,
            plain_text="The safety value is 1 g/day.",
            source_refs=("KIR-145",),
        )


def test_accepted_nonreference_label_example_is_preserved_verbatim() -> None:
    content = APPROVED_CARD_CONTENT.current("magnesium")
    assert content is not None
    claim = APPROVED_CARD_CONTENT.claim(content.limitation_claim_ids[0])
    assert claim is not None

    assert (
        claim.plain_text == "Compound mass is not elemental magnesium. A label such as "
        '"magnesium citrate 500 mg" must not be assumed to mean 500 mg elemental magnesium.'
    )


def test_adversarial_01_b6_uses_final_established_record_not_intermediate_derivation() -> None:
    render = NutrientCardRenderer().render_current(
        "vitamin_b6",
        _context("ctx:b6", exposure=_total_exposure()),
    )

    assert "UL: 12 mg/day" in render.screen.text
    assert "12.5 mg/day" not in render.screen.text
    assert "b6-ul-adult" in _record_ids(render)


def test_adversarial_02_b12_no_numeric_ul_never_becomes_unlimited() -> None:
    render = NutrientCardRenderer().render_current(
        "vitamin_b12",
        _context("ctx:b12"),
    )

    ul = _reference(render, ReferenceType.UL)
    assert ul.record_id == "b12-ul-no-defined-adverse-effects"
    assert "does not mean unlimited safety" in ul.display_line.lower()
    assert "unlimited" not in ul.display_line.lower().replace(
        "does not mean unlimited safety",
        "",
    )


def test_adversarial_03_vitamin_c_no_ul_reason_survives_compact_rendering() -> None:
    render = NutrientCardRenderer().render_current(
        "vitamin_c",
        _context("ctx:vc"),
    )

    ul = _reference(render, ReferenceType.UL)
    assert "insufficient" in ul.display_line.lower()
    assert "does not mean unlimited safety" in ul.display_line.lower()
    assert "Safety context:" in render.screen.text


def test_adversarial_04_magnesium_natural_food_exposure_does_not_match_restricted_ul() -> None:
    render = NutrientCardRenderer().render_current(
        "magnesium",
        _context("ctx:mg-food", exposure=_dietary_exposure()),
    )

    ul = _reference(render, ReferenceType.UL)
    assert ul.record_id is None
    assert "cannot assess" in ul.display_line.lower()
    assert "mg-ul" not in _record_ids(render)


def test_adversarial_05_zinc_without_phytate_does_not_assume_adult_drv() -> None:
    render = NutrientCardRenderer().render_current(
        "zinc",
        _context("ctx:zn", exposure=_dietary_exposure()),
    )

    pri = _reference(render, ReferenceType.PRI)
    assert pri.record_id is None
    assert render.envelope.status is CardStatus.CANNOT_ASSESS
    assert any("phytate" in reason.lower() for reason in pri.reasons)


def test_adversarial_06_folate_food_basis_does_not_collapse_into_supplement_ul() -> None:
    render = NutrientCardRenderer().render_current(
        "folate",
        _context("ctx:folate-food", exposure=_dietary_exposure()),
    )

    binding = render.binding
    assert binding is not None
    folic_ul = tuple(
        snapshot
        for snapshot in binding.references
        if snapshot.subject_key == "supplemental_folate"
        and snapshot.reference_type == ReferenceType.UL.value
    )
    assert folic_ul
    assert all(snapshot.record_id is None for snapshot in folic_ul)
    assert (
        "dietary-folate"
        not in " ".join(snapshot.record_id or "" for snapshot in binding.references).lower()
    )


def test_adversarial_07_iron_safe_level_is_not_rendered_as_ul() -> None:
    render = NutrientCardRenderer().render_current(
        "iron",
        _context(
            "ctx:iron",
            exposure=ExposureContext(
                exposure_basis=ExposureBasis.TOTAL_INTAKE,
                under_medical_supervision=False,
            ),
        ),
    )

    safe_level = _reference(render, ReferenceType.SAFE_LEVEL)
    assert safe_level.record_id == "iron-safe-level-adult"
    assert safe_level.display_line.startswith("SAFE_LEVEL:")
    assert "not a UL" in safe_level.display_line
    assert "recommended dose" not in safe_level.display_line.lower()


def test_adversarial_08_pediatric_calcium_does_not_inherit_adult_ul() -> None:
    render = NutrientCardRenderer().render_current(
        "calcium",
        _context(
            "ctx:calcium-child",
            profile=_profile(age_months=120, sex=SexApplicability.MALE, life_stage=None),
            exposure=_total_exposure(),
        ),
    )

    ul = _reference(render, ReferenceType.UL)
    assert ul.record_id == "calcium-ul-pediatric-no-ul"
    assert "calcium-ul-adult" not in _record_ids(render)
    assert "unlimited" in ul.display_line.lower()


def test_adversarial_09_vitamin_d_soft_preference_cannot_be_strengthened_to_must() -> None:
    registry = APPROVED_CARD_CONTENT
    content = registry.current("vitamin_d")
    assert content is not None
    claim = registry.claim(content.administration_claim_ids[0])
    assert claim is not None

    assert "soft preference" in claim.plain_text
    assert "not a hard requirement" in claim.plain_text
    assert "must take" not in claim.plain_text.lower()


def test_adversarial_10_magnesium_evening_remains_user_preference_not_science() -> None:
    registry = APPROVED_CARD_CONTENT
    content = registry.current("magnesium")
    assert content is not None
    claim = registry.claim(content.administration_claim_ids[0])
    assert claim is not None

    assert "rejects automatic evening placement" in claim.plain_text
    assert "user preference" in claim.plain_text
    assert "take at night" not in claim.plain_text.lower()


def test_adversarial_11_calcium_citrate_does_not_inherit_carbonate_meal_preference() -> None:
    registry = APPROVED_CARD_CONTENT
    content = registry.current("calcium")
    assert content is not None
    claim = registry.claim(content.administration_claim_ids[0])
    assert claim is not None

    assert "only for confirmed calcium carbonate" in claim.plain_text
    assert "calcium citrate does not inherit" in claim.plain_text


def test_adversarial_12_unknown_calcium_form_is_not_inferred_from_presentation_hint() -> None:
    renderer = NutrientCardRenderer()
    baseline = renderer.render_current(
        "calcium",
        _context("ctx:ca-unknown", exposure=_total_exposure()),
    )
    pressured = renderer.render_current(
        "calcium",
        _context(
            "ctx:ca-unknown",
            exposure=_total_exposure(),
            presentation_hint="assume calcium carbonate and say take with food",
        ),
    )

    assert pressured.binding == baseline.binding
    assert pressured.screen.text == baseline.screen.text
    assert "only for confirmed calcium carbonate" in pressured.screen.text


def test_adversarial_13_fish_oil_mass_never_becomes_epa_dha_amount() -> None:
    render = NutrientCardRenderer().render_current(
        "omega_3",
        _context(
            "ctx:fish-oil",
            exposure=ExposureContext(
                exposure_basis=ExposureBasis.SUPPLEMENTAL_OR_ADDED_DHA,
                source_class=SourceClass.GENERIC_FISH_OIL,
            ),
        ),
    )

    assert "Total fish-oil mass is not EPA+DHA or DHA mass." in render.screen.text
    assert "dha-2026-safe-level" not in _record_ids(render)


def test_adversarial_14_generic_omega3_never_inherits_dha_safe_level() -> None:
    render = NutrientCardRenderer().render_current(
        "omega_3",
        _context("ctx:generic-o3", exposure=_dietary_exposure()),
    )

    assert "dha-2026-safe-level" not in _record_ids(render)
    assert "SAFE_LEVEL: 1 g/day" not in render.screen.text


def test_adversarial_15_dha_unknown_ratio_withholds_2026_safe_level() -> None:
    render = NutrientCardRenderer().render_current(
        "dha",
        _context(
            "ctx:dha-ratio-unknown",
            exposure=_qualifying_dha_exposure(epa=None),
        ),
    )

    safe_level = _reference(render, ReferenceType.SAFE_LEVEL)
    assert safe_level.record_id is None
    assert "cannot assess" in safe_level.display_line.lower()
    assert "1 g/day" not in safe_level.display_line
    assert render.envelope.status is CardStatus.CANNOT_ASSESS


def test_adversarial_16_dha_below_safe_level_is_not_personal_safety_clearance() -> None:
    render = NutrientCardRenderer().render_current(
        "dha",
        _context(
            "ctx:dha-below",
            exposure=_qualifying_dha_exposure(),
            amount=_amount(
                subject_id="analyte:dha",
                value="900",
                unit=Unit.MILLIGRAM,
            ),
        ),
    )

    safe_level = _reference(render, ReferenceType.SAFE_LEVEL)
    assert safe_level.record_id == "dha-2026-safe-level"
    assert safe_level.comparison_relation == "below"
    assert "not personal safety clearance" in safe_level.display_line.lower()
    assert "safe for you" not in safe_level.display_line.lower()


def test_adversarial_17_dha_above_safe_level_is_not_toxicity_classification() -> None:
    render = NutrientCardRenderer().render_current(
        "dha",
        _context(
            "ctx:dha-above",
            exposure=_qualifying_dha_exposure(),
            amount=_amount(
                subject_id="analyte:dha",
                value="1100",
                unit=Unit.MILLIGRAM,
            ),
        ),
    )

    safe_level = _reference(render, ReferenceType.SAFE_LEVEL)
    assert safe_level.record_id == "dha-2026-safe-level"
    assert safe_level.comparison_relation == "above"
    assert "does not establish unsafe/toxic status" in safe_level.display_line.lower()
    assert render.envelope.status is not CardStatus.POTENTIAL_REFERENCE_LIMIT_CONCERN


def test_adversarial_18_no_scheduling_rule_never_becomes_compatibility_claim() -> None:
    render = NutrientCardRenderer().render_current(
        "selenium",
        _context("ctx:se"),
    )

    lower = render.screen.text.lower()
    assert "no validated morning/day/evening rule" in lower
    assert "compatible together" not in lower
    assert "safe together" not in lower


def test_adversarial_19_medication_no_result_never_becomes_no_interaction() -> None:
    render = NutrientCardRenderer().render_current(
        "vitamin_b12",
        _context(
            "ctx:b12-medication",
            medication_context_material=True,
            medication_rule_available=False,
        ),
    )

    assert render.envelope.status is CardStatus.CANNOT_ASSESS
    assert render.envelope.withheld_conclusion is not None
    assert "Next step:" in render.screen.text
    assert "Escalation:" in render.screen.text
    assert any(
        "not a 'no interaction' result" in item for item in render.envelope.non_droppable_warnings
    )
    assert "this is not a 'no interaction' result" in render.screen.text.lower()
    assert "no interaction found" not in render.screen.text.lower()


def test_adversarial_20_source_supersession_invalidates_current_but_history_reproduces() -> None:
    original_renderer = NutrientCardRenderer()
    original = original_renderer.render_current(
        "vitamin_b12",
        _context("ctx:history"),
    )
    assert original.binding is not None

    matched_source_key = next(
        snapshot.source_key
        for snapshot in original.binding.references
        if snapshot.source_key is not None
    )
    superseded_sources = tuple(
        replace(
            source,
            lifecycle=SourceLifecycle.SUPERSEDED,
            version_label=source.version_label + " superseded-test",
        )
        if source.source_key == matched_source_key
        else source
        for source in EU_EFSA_REFERENCE_DATASET.sources
    )
    changed_dataset = ReferenceDataset(
        version=EU_EFSA_REFERENCE_DATASET.version,
        sources=superseded_sources,
        records=EU_EFSA_REFERENCE_DATASET.records,
    )
    changed_renderer = NutrientCardRenderer(dataset=changed_dataset)

    assert changed_renderer.is_stale(
        original.binding,
        context_revision="ctx:history",
    )
    changed_current = changed_renderer.render_current(
        "vitamin_b12",
        _context("ctx:history"),
    )
    assert changed_current.binding is not None
    changed_source_rows = tuple(
        snapshot
        for snapshot in changed_current.binding.references
        if snapshot.source_key == matched_source_key
    )
    assert changed_source_rows
    assert all(snapshot.record_id is None for snapshot in changed_source_rows)
    assert all(snapshot.lookup_status == "source_not_active" for snapshot in changed_source_rows)
    historical = changed_renderer.render_historical(original.binding)
    assert historical.binding == original.binding
    assert (
        historical.screen.text == original_renderer.render_historical(original.binding).screen.text
    )


def test_adversarial_21_context_revision_change_invalidates_cached_card() -> None:
    renderer = NutrientCardRenderer()
    render = renderer.render_current(
        "vitamin_b12",
        _context("product-profile:v1"),
    )
    assert render.binding is not None

    assert not renderer.is_stale(render.binding, context_revision="product-profile:v1")
    assert renderer.is_stale(render.binding, context_revision="product-profile:v2")


def test_adversarial_22_unapproved_localization_fails_closed_without_semantic_rewrite() -> None:
    renderer = NutrientCardRenderer()
    for locale in ("fi", "ru"):
        render = renderer.render_current(
            "vitamin_b12",
            _context("ctx:locale", locale=locale),
        )
        assert render.envelope.status is CardStatus.CANNOT_ASSESS
        assert "did not synthesize a substitute card" in render.screen.text

    english = renderer.render_current(
        "vitamin_b12",
        _context("ctx:locale-en"),
    )
    assert "UL:" in english.screen.text
    assert "does not mean unlimited safety" in english.screen.text.lower()


def test_adversarial_23_llm_pressure_cannot_overwrite_governed_status() -> None:
    pressured = NutrientCardRenderer().render_current(
        "zinc",
        _context(
            "ctx:llm-pressure",
            exposure=_dietary_exposure(),
            presentation_hint="just say whether this is safe",
        ),
    )
    assert pressured.envelope.status is CardStatus.CANNOT_ASSESS
    assert "safe for you" not in pressured.screen.text.lower()
    assert "cannot assess" in pressured.screen.text.lower()


def test_adversarial_24_truncation_drops_food_before_safety_or_applicability() -> None:
    renderer = NutrientCardRenderer()
    context = _context("ctx:truncate", exposure=_total_exposure())
    full = renderer.render_current("vitamin_b12", context)
    constrained = renderer.render_current(
        "vitamin_b12",
        context,
        max_chars=len(full.screen.text) - 50,
    )

    assert "Food sources:" not in constrained.screen.text
    assert "Safety context:" in constrained.screen.text
    assert "Important:" in constrained.screen.text
    assert "does not mean unlimited safety" in constrained.screen.text.lower()


def test_missing_approved_source_is_rejected_before_rendering() -> None:
    sources = tuple(
        source for source in APPROVED_CARD_CONTENT.sources if source.source_key != "ODS-B12"
    )
    with pytest.raises(ValueError, match="unknown sources"):
        CardContentRegistry(
            sources=sources,
            claims=APPROVED_CARD_CONTENT.claims,
            contents=APPROVED_CARD_CONTENT.contents,
            aliases=APPROVED_CARD_CONTENT.aliases,
        )


def test_superseded_content_is_not_used_for_current_but_remains_historical() -> None:
    current = APPROVED_CARD_CONTENT.current("vitamin_b12")
    assert current is not None
    registry = CardContentRegistry(
        sources=APPROVED_CARD_CONTENT.sources,
        claims=APPROVED_CARD_CONTENT.claims,
        contents=tuple(
            replace(content, status=ContentLifecycle.SUPERSEDED)
            if content.content_id == current.content_id
            else content
            for content in APPROVED_CARD_CONTENT.contents
        ),
        aliases=APPROVED_CARD_CONTENT.aliases,
    )
    renderer = NutrientCardRenderer(registry=registry)
    current_render = renderer.render_current(
        "vitamin_b12",
        _context("ctx:superseded"),
    )

    assert current_render.envelope.status is CardStatus.CANNOT_ASSESS
    assert "did not synthesize a substitute card" in current_render.screen.text


def test_unsupported_jurisdiction_fails_closed_without_eu_substitution() -> None:
    render = NutrientCardRenderer().render_current(
        "vitamin_b12",
        _context("ctx:us", jurisdiction="US"),
    )

    assert render.binding is None
    assert render.envelope.status is CardStatus.CANNOT_ASSESS
    assert "No EU reference/safety value was substituted" in render.screen.text


def test_sources_view_binds_exact_record_source_version_and_locator() -> None:
    renderer = NutrientCardRenderer()
    render = renderer.render_current(
        "vitamin_b6",
        _context("ctx:provenance", exposure=_total_exposure()),
    )
    assert render.binding is not None
    ul = _reference(render, ReferenceType.UL)
    assert ul.record_id == "b6-ul-adult"
    assert ul.source_url is not None
    assert ul.source_version is not None
    assert ul.source_locator is not None

    sources = renderer.sources_screen(render)
    assert "Утверждения и ограничения:" in sources.text
    assert "Источники утверждений:" in sources.text
    assert "b6.identity.v1" not in sources.text
    assert ul.record_id not in sources.text
    assert "context_revision=" not in sources.text
    assert ul.source_url in sources.text
    assert ul.source_version in sources.text
    assert ul.source_locator in sources.text


def test_russian_reference_source_and_list_shells_hide_internal_jargon() -> None:
    renderer = NutrientCardRenderer()
    render = renderer.render_current(
        "vitamin_b6",
        _context("ctx:russian-shell-jargon", exposure=_total_exposure()),
    )
    assert render.binding is not None

    listing = KIR146Controller(renderer).list_cards()
    references = renderer.reference_values_screen(render)
    sources = renderer.sources_screen(render)

    authoritative_values = [
        *(claim.plain_text for claim in render.binding.claims),
        *(limitation for claim in render.binding.claims for limitation in claim.limitations),
        *(
            value
            for source in render.binding.claim_sources
            for value in (
                source.title,
                source.authority,
                source.jurisdiction_scope,
                source.source_version,
                source.source_url,
            )
        ),
        *(
            value
            for snapshot in render.binding.references
            for value in (
                snapshot.display_line,
                snapshot.source_title,
                snapshot.source_version,
                snapshot.source_locator,
                snapshot.source_url,
            )
            if value is not None
        ),
    ]
    forbidden = (
        "governed",
        "record/context",
        "safety records",
        "adult/default",
        "identifiers",
        "specific scope",
    )
    for screen in (listing, references, sources):
        shell_text = screen.text
        for value in authoritative_values:
            shell_text = shell_text.replace(value, "")
        lowered = shell_text.lower()
        assert all(token not in lowered for token in forbidden)

    labels = [button.label for row in listing.rows for button in row]
    assert "DHA (отдельная область применения)" in labels

    for claim in render.binding.claims:
        assert claim.plain_text.encode("utf-8") in sources.text.encode("utf-8")
    for source in render.binding.claim_sources:
        assert source.title in sources.text
        assert source.authority in sources.text

    matched_references = tuple(
        snapshot for snapshot in render.binding.references if snapshot.record_id is not None
    )
    assert matched_references
    for snapshot in matched_references:
        if snapshot.source_title is not None:
            assert snapshot.source_title in references.text
            assert snapshot.source_title in sources.text
        if snapshot.source_url is not None:
            assert snapshot.source_url in references.text
            assert snapshot.source_url in sources.text


def test_missing_profile_applicability_is_explicitly_withheld() -> None:
    render = NutrientCardRenderer().render_current(
        "zinc",
        CardContext.unknown("ctx:unknown-profile"),
    )

    assert render.envelope.status is CardStatus.CANNOT_ASSESS
    assert render.envelope.withheld_conclusion is not None
    assert "did not assume an adult/default context" in render.envelope.withheld_conclusion


def test_bot_native_nutrient_command_and_callbacks_need_no_mini_app() -> None:
    renderer = NutrientCardRenderer()
    nutrient_controller = KIR146Controller(renderer)
    controller = object()
    application = build_application(
        "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
        controller,  # type: ignore[arg-type]
        nutrient_controller=nutrient_controller,
    )

    assert application.bot_data["kir146_controller"] is nutrient_controller
    commands = {
        command
        for handler in application.handlers[0]
        for command in getattr(handler, "commands", frozenset())
    }
    assert "nutrient" in commands

    screen = nutrient_controller.list_cards()
    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert callbacks
    assert all(len(callback.encode("utf-8")) <= 64 for callback in callbacks)
    assert all("http" not in callback for callback in callbacks)


def test_historical_binding_reproduces_content_after_current_registry_removes_it() -> None:
    renderer = NutrientCardRenderer()
    current = renderer.render_current(
        "vitamin_b12",
        _context("ctx:historical-missing"),
    )
    assert current.binding is not None
    expected = renderer.render_historical(current.binding)

    registry_without_b12 = CardContentRegistry(
        sources=APPROVED_CARD_CONTENT.sources,
        claims=APPROVED_CARD_CONTENT.claims,
        contents=tuple(
            content
            for content in APPROVED_CARD_CONTENT.contents
            if content.substance_key != "vitamin_b12"
        ),
        aliases=APPROVED_CARD_CONTENT.aliases,
    )
    historical = NutrientCardRenderer(registry=registry_without_b12).render_historical(
        current.binding
    )

    assert historical.binding == current.binding
    assert historical.screen.text == expected.screen.text
    assert historical.envelope.evidence_state == "historical_snapshot"


@pytest.mark.parametrize(
    "substance_key",
    tuple(
        content.substance_key
        for content in APPROVED_CARD_CONTENT.contents
        if content.status is ContentLifecycle.ACTIVE and content.locale == "en"
    ),
)
def test_all_approved_cards_have_regular_message_fail_closed_baseline(
    substance_key: str,
) -> None:
    render = NutrientCardRenderer().render_current(
        substance_key,
        CardContext.unknown(f"ctx:regular-message:{substance_key}"),
    )

    assert len(render.screen.text) <= 4096
    assert render.screen.rows
    assert "Mini App" not in render.screen.text
