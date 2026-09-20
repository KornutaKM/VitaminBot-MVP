from decimal import Decimal

import pytest

from vitaminbot.domain import (
    AmountBasis,
    AmountRecord,
    EvidenceStatus,
    LifeStage,
    QuantityBasis,
    ResolutionStatus,
    SexApplicability,
    SubjectKind,
    Unit,
)
from vitaminbot.nutrition import (
    aggregate_daily_contributions,
    AggregationIssue,
    ApplicabilityReason,
    apply_scientific_conversion,
    CALCIUM_ANALYTE_ID,
    CALCIUM_CARBONATE_FORM_ID,
    CALCIUM_CITRATE_FORM_ID,
    compare_amount_to_reference,
    ComparisonRelation,
    ComparisonStatus,
    ComputationTrace,
    ComputedAmount,
    ConfirmedPlannedContribution,
    convert_mass,
    DHAForm,
    DimensionMismatchError,
    DuplicateFlagKind,
    EU_EFSA_REFERENCE_DATASET,
    evaluate_rule_engine,
    EventRelation,
    ExposureBasis,
    ExposureContext,
    ExposureCoverage,
    GlobalReason,
    IRON_ANALYTE_ID,
    ItemSourceKind,
    lookup_reference,
    LookupStatus,
    MealContextPreference,
    NormalizationOutcome,
    PopulationProfile,
    ReferenceQuery,
    ReferenceStatus,
    ReferenceType,
    RoutineBucket,
    rule_result_is_stale,
    RuleEngineGlobalStatus,
    RuleReason,
    RuleStatus,
    RuleWarning,
    SchedulingItem,
    SchedulingRuleId,
    SourceClass,
    SplitAction,
    UnresolvedReason,
    UserRoutinePreference,
    VITAMIN_D_ANALYTE_ID,
    VITAMIN_D_D2_D3_RULE,
    ZINC_ANALYTE_ID,
)


CONTEXT_REVISION = "kir121:ctx:v1"


def _trace(
    *,
    operation: str = "kir121-independent-fixture",
    plan_id: str | None = None,
    plan_version: str | None = None,
) -> ComputationTrace:
    return ComputationTrace(
        operation=operation,
        rule_id="KIR-121",
        rule_version="1",
        plan_id=plan_id,
        plan_version=plan_version,
    )


def _daily_amount(
    *,
    subject_kind: SubjectKind = SubjectKind.ANALYTE,
    subject_id: str,
    value: str,
    unit: Unit = Unit.MILLIGRAM,
    amount_basis: AmountBasis = AmountBasis.ELEMENTAL,
    plan_id: str = "plan:test",
    plan_version: str = "1",
) -> ComputedAmount:
    return ComputedAmount(
        subject_kind=subject_kind,
        subject_id=subject_id,
        value=Decimal(value),
        unit=unit,
        amount_basis=amount_basis,
        quantity_basis=QuantityBasis.PER_DAY,
        source_quantity_basis_ids=("basis:test",),
        source_amount_ids=(f"amount:{subject_id}:{value}",),
        source_ids=("source:kir121-fixture",),
        traces=(
            _trace(
                operation="planned_daily_normalization",
                plan_id=plan_id,
                plan_version=plan_version,
            ),
        ),
    )


def _contribution(
    contribution_id: str,
    tracked_instance_id: str,
    *,
    subject_kind: SubjectKind = SubjectKind.ANALYTE,
    subject_id: str = "analyte:magnesium",
    value: str = "100",
    unit: Unit = Unit.MILLIGRAM,
    amount_basis: AmountBasis = AmountBasis.ELEMENTAL,
    product_id: str | None = None,
    plan_id: str | None = None,
) -> ConfirmedPlannedContribution:
    resolved_plan_id = plan_id or f"plan:{tracked_instance_id}"
    amount = _daily_amount(
        subject_kind=subject_kind,
        subject_id=subject_id,
        value=value,
        unit=unit,
        amount_basis=amount_basis,
        plan_id=resolved_plan_id,
    )
    return ConfirmedPlannedContribution(
        contribution_id=contribution_id,
        confirmation_ref=f"confirmation:{contribution_id}",
        product_id=product_id or f"product:{tracked_instance_id}",
        formulation_id=f"formulation:{tracked_instance_id}",
        tracked_instance_id=tracked_instance_id,
        plan_id=resolved_plan_id,
        plan_version="1",
        expected_subject_kind=subject_kind,
        expected_subject_id=subject_id,
        expected_amount_basis=amount_basis,
        expected_equivalence_basis=None,
        expected_unit=unit,
        outcome=NormalizationOutcome(
            status=ResolutionStatus.RESOLVED,
            amount=amount,
        ),
    )


def _unresolved_contribution() -> ConfirmedPlannedContribution:
    return ConfirmedPlannedContribution(
        contribution_id="unknown",
        confirmation_ref="confirmation:unknown",
        product_id="product:unknown",
        formulation_id="formulation:unknown",
        tracked_instance_id="instance:unknown",
        plan_id="plan:unknown",
        plan_version="1",
        expected_subject_kind=SubjectKind.ANALYTE,
        expected_subject_id="analyte:magnesium",
        expected_amount_basis=AmountBasis.ELEMENTAL,
        expected_equivalence_basis=None,
        expected_unit=Unit.MILLIGRAM,
        outcome=NormalizationOutcome(
            status=ResolutionStatus.UNKNOWN,
            reason=UnresolvedReason.INPUT_UNRESOLVED,
        ),
    )


def _profile(*, age_months: int | None = 360) -> PopulationProfile:
    return PopulationProfile(
        age_months=age_months,
        sex=SexApplicability.FEMALE,
        life_stage=LifeStage.GENERAL,
    )


def _reference_query(
    substance_key: str,
    reference_type: ReferenceType,
    *,
    age_months: int | None = 360,
    exposure: ExposureContext | None = None,
) -> ReferenceQuery:
    return ReferenceQuery(
        substance_key=substance_key,
        reference_type=reference_type,
        profile=_profile(age_months=age_months),
        exposure=exposure or ExposureContext(),
        context_revision=CONTEXT_REVISION,
    )


def _event_amount(
    *,
    subject_id: str,
    value: str,
    unit: Unit = Unit.MILLIGRAM,
    amount_basis: AmountBasis = AmountBasis.ELEMENTAL,
    chemical_form_id: str | None = None,
) -> ComputedAmount:
    return ComputedAmount(
        subject_kind=SubjectKind.ANALYTE,
        subject_id=subject_id,
        value=Decimal(value),
        unit=unit,
        amount_basis=amount_basis,
        quantity_basis=QuantityBasis.ABSOLUTE,
        source_quantity_basis_ids=(),
        source_amount_ids=(f"event-amount:{subject_id}:{value}",),
        source_ids=("source:kir121-fixture",),
        traces=(_trace(),),
        chemical_form_id=chemical_form_id,
    )


def _item(
    item_id: str,
    *amounts: ComputedAmount,
    source_kind: ItemSourceKind = ItemSourceKind.SUPPLEMENT,
    units: str = "1",
    schedulable: bool = True,
    fixed_combination_id: str | None = None,
    event_id: str | None = None,
) -> SchedulingItem:
    return SchedulingItem(
        item_id=item_id,
        product_id=f"product:{item_id}",
        formulation_id=f"formulation:{item_id}",
        tracked_instance_id=f"instance:{item_id}",
        plan_id=f"plan:{item_id}",
        plan_version="1",
        event_id=event_id or f"event:{item_id}",
        context_revision=CONTEXT_REVISION,
        source_kind=source_kind,
        amounts=tuple(amounts),
        confirmed_consumption_units=Decimal(units),
        units_independently_schedulable=schedulable,
        fixed_combination_id=fixed_combination_id,
    )


def _evaluate(
    *items: SchedulingItem,
    medication: bool = False,
    preferences: tuple[UserRoutinePreference, ...] = (),
):
    from vitaminbot.nutrition import RuleEvaluationContext

    return evaluate_rule_engine(
        RuleEvaluationContext(
            context_revision=CONTEXT_REVISION,
            items=tuple(items),
            user_preferences=preferences,
            medication_context_present=medication,
        )
    )


def _for_rule(result: object, rule_id: SchedulingRuleId):
    scheduling = result.scheduling_results  # type: ignore[attr-defined]
    return tuple(candidate for candidate in scheduling if candidate.rule_id is rule_id)


def test_mass_order_of_magnitude_and_activity_dimension_fail_closed() -> None:
    assert convert_mass(Decimal("1"), Unit.MILLIGRAM, Unit.MICROGRAM) == Decimal("1000")
    assert convert_mass(Decimal("1000"), Unit.MICROGRAM, Unit.MILLIGRAM) == Decimal("1")

    with pytest.raises(DimensionMismatchError):
        convert_mass(Decimal("1000"), Unit.INTERNATIONAL_UNIT, Unit.MICROGRAM)


def test_vitamin_d_iu_conversion_requires_confirmed_supported_form() -> None:
    amount = AmountRecord(
        amount_id="amount:vitamin-d",
        subject_kind=SubjectKind.ANALYTE,
        subject_id=VITAMIN_D_ANALYTE_ID,
        source_id="source:label",
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal("1000"),
        unit=Unit.INTERNATIONAL_UNIT,
        amount_basis=AmountBasis.ANALYTE,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id="basis:serving",
    )

    outcome = apply_scientific_conversion(
        amount,
        VITAMIN_D_D2_D3_RULE,
        chemical_form_id=None,
    )

    assert outcome.status is ResolutionStatus.UNRESOLVED_IDENTITY
    assert outcome.amount is None
    assert outcome.reason is UnresolvedReason.CHEMICAL_FORM_REQUIRED


def test_compound_magnesium_never_joins_elemental_magnesium_total() -> None:
    elemental = _contribution(
        "elemental",
        "elemental",
        subject_id="analyte:magnesium",
        value="100",
    )
    compound = _contribution(
        "compound",
        "compound",
        subject_kind=SubjectKind.INGREDIENT,
        subject_id="ingredient:magnesium-citrate",
        value="500",
        amount_basis=AmountBasis.INGREDIENT_COMPOUND,
    )

    result = aggregate_daily_contributions((elemental, compound))

    assert len(result.aggregates) == 2
    elemental_total = next(
        aggregate
        for aggregate in result.aggregates
        if aggregate.key.subject_id == "analyte:magnesium"
    )
    compound_total = next(
        aggregate
        for aggregate in result.aggregates
        if aggregate.key.subject_id == "ingredient:magnesium-citrate"
    )
    assert elemental_total.known_total == Decimal("100000")
    assert compound_total.known_total == Decimal("500000")


def test_total_fish_oil_epa_and_dha_remain_three_distinct_aggregates() -> None:
    fish_oil = _contribution(
        "fish-oil",
        "fish-oil",
        subject_kind=SubjectKind.INGREDIENT,
        subject_id="ingredient:fish-oil",
        value="1000",
        amount_basis=AmountBasis.MATERIAL,
    )
    epa = _contribution(
        "epa",
        "epa",
        subject_id="analyte:epa",
        value="180",
        amount_basis=AmountBasis.ANALYTE,
    )
    dha = _contribution(
        "dha",
        "dha",
        subject_id="analyte:dha",
        value="120",
        amount_basis=AmountBasis.ANALYTE,
    )

    result = aggregate_daily_contributions((fish_oil, epa, dha))
    assert {aggregate.key.subject_id for aggregate in result.aggregates} == {
        "ingredient:fish-oil",
        "analyte:epa",
        "analyte:dha",
    }


def test_retry_duplicate_is_suppressed_but_distinct_products_are_not_deduplicated() -> None:
    original = _contribution("retry:1", "instance:same")
    retry = _contribution("retry:2", "instance:same")
    distinct = _contribution(
        "distinct",
        "instance:other",
        product_id="product:other",
        plan_id="plan:other",
    )

    result = aggregate_daily_contributions((original, retry, distinct))
    aggregate = result.aggregates[0]

    assert aggregate.known_total == Decimal("200000")
    assert len(aggregate.contributors) == 2
    assert any(
        flag.kind is DuplicateFlagKind.EXACT_REPEAT_SUPPRESSED
        for flag in result.duplicate_flags
    )


def test_unresolved_contributor_is_not_zero_and_marks_total_incomplete() -> None:
    known = _contribution("known", "instance:known")

    result = aggregate_daily_contributions((known, _unresolved_contribution()))
    aggregate = result.aggregates[0]

    assert aggregate.known_total == Decimal("100000")
    assert aggregate.is_complete is False
    assert AggregationIssue.UNRESOLVED_CONTRIBUTOR in aggregate.issues
    assert len(result.unresolved_contributors) == 1


def test_missing_age_does_not_fall_back_to_adult_calcium_ul() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _reference_query(
            "calcium",
            ReferenceType.UL,
            age_months=None,
            exposure=ExposureContext(exposure_basis=ExposureBasis.TOTAL_INTAKE),
        ),
    )

    assert result.status is LookupStatus.INDETERMINATE
    assert ApplicabilityReason.MISSING_AGE in result.reasons


def test_b6_uses_final_established_ul_not_intermediate_derivation() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _reference_query(
            "vitamin_b6",
            ReferenceType.UL,
            exposure=ExposureContext(exposure_basis=ExposureBasis.TOTAL_INTAKE),
        ),
    )

    assert result.status is LookupStatus.MATCHED
    assert result.match is not None
    assert result.match.record.value == Decimal("12")
    assert result.match.record.unit is Unit.MILLIGRAM
    assert result.match.record.value != Decimal("12.5")


def test_no_ul_state_remains_non_numeric_not_infinity() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _reference_query("vitamin_c", ReferenceType.UL),
    )

    assert result.status is LookupStatus.MATCHED
    assert result.match is not None
    assert result.match.record.value is None
    assert result.match.record.status is ReferenceStatus.NO_UL_INSUFFICIENT_DATA


def test_dha_ratio_boundary_and_generic_fish_oil_fail_closed() -> None:
    boundary_exposure = ExposureContext(
        exposure_basis=ExposureBasis.SUPPLEMENTAL_OR_ADDED_DHA,
        source_class=SourceClass.ALGAL_OIL,
        dha_form=DHAForm.TRIACYLGLYCEROL,
        epa_mg_per_day=Decimal("150"),
        dha_mg_per_day=Decimal("500"),
        coverage=ExposureCoverage.COMPLETE_QUALIFYING,
        amount_includes_background_dietary_dha=False,
    )
    boundary = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _reference_query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=boundary_exposure,
        ),
    )
    generic = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _reference_query(
            "fish_oil",
            ReferenceType.SAFE_LEVEL,
            exposure=boundary_exposure,
        ),
    )

    assert boundary.status is LookupStatus.NOT_APPLICABLE
    assert ApplicabilityReason.EPA_DHA_RATIO_NOT_QUALIFYING in boundary.reasons
    assert generic.status is LookupStatus.NOT_FOUND


def test_below_dha_safe_level_never_becomes_personal_safety_clearance() -> None:
    exposure = ExposureContext(
        exposure_basis=ExposureBasis.SUPPLEMENTAL_OR_ADDED_DHA,
        source_class=SourceClass.ALGAL_OIL,
        dha_form=DHAForm.TRIACYLGLYCEROL,
        epa_mg_per_day=Decimal("100"),
        dha_mg_per_day=Decimal("500"),
        coverage=ExposureCoverage.COMPLETE_QUALIFYING,
        amount_includes_background_dietary_dha=False,
    )
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _reference_query("dha", ReferenceType.SAFE_LEVEL, exposure=exposure),
    )
    comparison = compare_amount_to_reference(
        _daily_amount(
            subject_id="analyte:dha",
            value="900",
            unit=Unit.MILLIGRAM,
            amount_basis=AmountBasis.ANALYTE,
        ),
        lookup,
    )

    assert comparison.status is ComparisonStatus.COMPARABLE
    assert comparison.relation is ComparisonRelation.BELOW
    assert comparison.personal_safety_conclusion_withheld is True


def test_iron_zinc_threshold_uses_exact_elemental_supplement_amount() -> None:
    zinc = _item(
        "zinc",
        _event_amount(subject_id=ZINC_ANALYTE_ID, value="10"),
    )
    below = _item(
        "iron-below",
        _event_amount(subject_id=IRON_ANALYTE_ID, value="24.9"),
    )
    exact = _item(
        "iron-exact",
        _event_amount(subject_id=IRON_ANALYTE_ID, value="25"),
    )

    below_result = _evaluate(below, zinc)
    exact_result = _evaluate(exact, zinc)

    assert not any(
        candidate.status is RuleStatus.MATCHED_PREFERENCE
        for candidate in _for_rule(
            below_result,
            SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT,
        )
    )
    assert any(
        candidate.reason is RuleReason.IRON_THRESHOLD_NOT_MET
        for candidate in _for_rule(
            below_result,
            SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT,
        )
    )

    exact_match = next(
        candidate
        for candidate in _for_rule(
            exact_result,
            SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT,
        )
        if candidate.status is RuleStatus.MATCHED_PREFERENCE
    )
    assert exact_match.event_relation is EventRelation.AVOID_SAME_EVENT
    assert exact_match.minimum_gap_minutes is None
    assert RuleWarning.NULL_GAP_MUST_REMAIN_NULL in exact_match.warnings


def test_fortified_food_iron_cannot_trigger_supplemental_iron_zinc_rule() -> None:
    iron = _item(
        "fortified-iron",
        _event_amount(subject_id=IRON_ANALYTE_ID, value="30"),
        source_kind=ItemSourceKind.FORTIFIED_FOOD,
    )
    zinc = _item(
        "zinc",
        _event_amount(subject_id=ZINC_ANALYTE_ID, value="10"),
    )

    result = _evaluate(iron, zinc)
    candidates = _for_rule(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT)

    assert not any(
        candidate.status is RuleStatus.MATCHED_PREFERENCE for candidate in candidates
    )
    assert any(
        candidate.reason is RuleReason.IRON_SOURCE_NOT_SUPPLEMENT
        for candidate in candidates
    )


def test_calcium_form_applicability_does_not_leak_across_forms() -> None:
    carbonate = _item(
        "carbonate",
        _event_amount(
            subject_id=CALCIUM_ANALYTE_ID,
            value="500",
            chemical_form_id=CALCIUM_CARBONATE_FORM_ID,
        ),
    )
    citrate = _item(
        "citrate",
        _event_amount(
            subject_id=CALCIUM_ANALYTE_ID,
            value="500",
            chemical_form_id=CALCIUM_CITRATE_FORM_ID,
        ),
    )
    unknown = _item(
        "unknown",
        _event_amount(subject_id=CALCIUM_ANALYTE_ID, value="500"),
    )

    result = _evaluate(carbonate, citrate, unknown)
    candidates = _for_rule(result, SchedulingRuleId.CALCIUM_CARBONATE_WITH_MEAL)
    by_item = {candidate.item_ids[0]: candidate for candidate in candidates}

    assert by_item["carbonate"].status is RuleStatus.MATCHED_PREFERENCE
    assert (
        by_item["carbonate"].meal_context_preference
        is MealContextPreference.WITH_MEAL
    )
    assert by_item["citrate"].reason is RuleReason.CALCIUM_FORM_NOT_CARBONATE
    assert by_item["unknown"].status is RuleStatus.INSUFFICIENT_EVIDENCE
    assert by_item["unknown"].reason is RuleReason.CALCIUM_FORM_REQUIRED


def test_calcium_iron_null_gap_and_fixed_combination_limits_are_preserved() -> None:
    calcium = _item(
        "calcium",
        _event_amount(subject_id=CALCIUM_ANALYTE_ID, value="300"),
    )
    iron = _item(
        "iron",
        _event_amount(subject_id=IRON_ANALYTE_ID, value="10"),
    )

    separate = _evaluate(calcium, iron)
    separate_match = next(
        candidate
        for candidate in _for_rule(
            separate,
            SchedulingRuleId.CALCIUM_IRON_AVOID_SAME_EVENT,
        )
        if candidate.status is RuleStatus.MATCHED_PREFERENCE
    )
    assert separate_match.event_relation is EventRelation.AVOID_SAME_EVENT
    assert separate_match.minimum_gap_minutes is None

    combo = _item(
        "combo",
        _event_amount(subject_id=CALCIUM_ANALYTE_ID, value="300"),
        _event_amount(subject_id=IRON_ANALYTE_ID, value="10"),
        fixed_combination_id="fixed:calcium-iron",
    )
    fixed = _for_rule(
        _evaluate(combo),
        SchedulingRuleId.CALCIUM_IRON_AVOID_SAME_EVENT,
    )[0]
    assert fixed.status is RuleStatus.CANNOT_OPTIMIZE_FIXED_COMBINATION
    assert fixed.event_relation is None
    assert fixed.minimum_gap_minutes is None


def test_broad_ethyl_ester_omega3_rule_remains_disabled() -> None:
    omega = _item(
        "omega",
        _event_amount(
            subject_id="analyte:epa-plus-dha",
            value="1000",
            amount_basis=AmountBasis.ANALYTE,
            chemical_form_id="chemical-form:ethyl-ester",
        ),
    )

    result = _evaluate(omega)

    assert len(result.scheduling_results) == 1
    only = result.scheduling_results[0]
    assert only.rule_id is SchedulingRuleId.NO_SUPPORTED_RULE_FOUND
    assert RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE in only.warnings


def test_calcium_split_rearranges_existing_units_but_never_creates_dose() -> None:
    one_unit = _item(
        "one-unit",
        _event_amount(subject_id=CALCIUM_ANALYTE_ID, value="1000"),
        units="1",
    )
    two_units = _item(
        "two-units",
        _event_amount(subject_id=CALCIUM_ANALYTE_ID, value="1000"),
        units="2",
    )

    one = _for_rule(
        _evaluate(one_unit),
        SchedulingRuleId.CALCIUM_SPLIT_EVENT_PREFERENCE,
    )
    two = _for_rule(
        _evaluate(two_units),
        SchedulingRuleId.CALCIUM_SPLIT_EVENT_PREFERENCE,
    )

    assert not any(
        candidate.status is RuleStatus.MATCHED_PREFERENCE for candidate in one
    )
    assert any(
        candidate.reason is RuleReason.INTACT_UNITS_NOT_REARRANGEABLE
        for candidate in one
    )

    matched = next(
        candidate for candidate in two if candidate.status is RuleStatus.MATCHED_PREFERENCE
    )
    assert matched.split_action is SplitAction.DISTRIBUTE_EXISTING_INTACT_UNITS
    assert matched.personalized_dose_instruction_allowed is False
    assert RuleWarning.NO_PERSONALIZED_DOSE in matched.warnings


def test_high_risk_context_withholds_generic_scheduling() -> None:
    vitamin_d = _item(
        "vitamin-d",
        _event_amount(
            subject_id=VITAMIN_D_ANALYTE_ID,
            value="25",
            unit=Unit.MICROGRAM,
            amount_basis=AmountBasis.ANALYTE,
        ),
    )

    result = _evaluate(vitamin_d, medication=True)

    assert result.global_status is RuleEngineGlobalStatus.WITHHELD_HIGH_RISK_CONTEXT
    assert GlobalReason.MEDICATION_CONTEXT_UNVALIDATED in result.global_reasons
    assert result.scheduling_results == ()


def test_user_routine_preference_is_not_scientific_provenance() -> None:
    magnesium = _item(
        "magnesium",
        _event_amount(subject_id="analyte:magnesium", value="100"),
    )
    preference = UserRoutinePreference(
        preference_id="user:evening",
        item_id="magnesium",
        bucket=RoutineBucket.EVENING,
        context_revision=CONTEXT_REVISION,
    )

    result = _evaluate(magnesium, preferences=(preference,))

    assert result.user_preferences == (preference,)
    assert result.user_preferences[0].provenance_kind == "user_preference"
    assert result.scheduling_results[0].rule_id is SchedulingRuleId.NO_SUPPORTED_RULE_FOUND
    assert result.scheduling_results[0].clock_time_preference is None


def test_schedule_result_is_stale_after_context_correction() -> None:
    calcium = _item(
        "calcium",
        _event_amount(
            subject_id=CALCIUM_ANALYTE_ID,
            value="500",
            chemical_form_id=CALCIUM_CARBONATE_FORM_ID,
        ),
    )
    result = _evaluate(calcium)
    matched = next(
        candidate
        for candidate in _for_rule(
            result,
            SchedulingRuleId.CALCIUM_CARBONATE_WITH_MEAL,
        )
        if candidate.status is RuleStatus.MATCHED_PREFERENCE
    )

    assert rule_result_is_stale(matched, context_revision=CONTEXT_REVISION) is False
    assert rule_result_is_stale(matched, context_revision="kir121:ctx:v2") is True
