from dataclasses import replace
from decimal import Decimal

import pytest

from vitaminbot.domain import (
    AmountBasis,
    LifeStage,
    QuantityBasis,
    SexApplicability,
    SubjectKind,
    Unit,
    UnitDimension,
)
from vitaminbot.nutrition.aggregation import (
    AggregateKey,
    AggregationIssue,
    DailyAggregate,
    DailyAggregationResult,
    DuplicateFlag,
    DuplicateFlagKind,
    ResolvedContribution,
)
from vitaminbot.nutrition.normalization import ComputationTrace, ComputedAmount
from vitaminbot.nutrition.reference_values import (
    ComparisonRelation,
    ExposureBasis,
    ExposureContext,
    PopulationProfile,
    ReferenceQuery,
    ReferenceType,
)
from vitaminbot.nutrition.rules import (
    CALCIUM_ANALYTE_ID,
    CALCIUM_CARBONATE_FORM_ID,
    CALCIUM_CITRATE_FORM_ID,
    DEFAULT_RULESET,
    IRON_ANALYTE_ID,
    RULESET_VERSION,
    VITAMIN_D_ANALYTE_ID,
    ZINC_ANALYTE_ID,
    AdministrationInstruction,
    BoundDailyAggregation,
    DuplicateResultStatus,
    EventRelation,
    GlobalReason,
    InstructionKind,
    ItemSourceKind,
    MealContextPreference,
    MealSlot,
    ReferenceComparisonRequest,
    ReferenceEvaluationStatus,
    ResolutionPath,
    RoutineBucket,
    RuleDataError,
    RuleDecisionClass,
    RuleEngineGlobalStatus,
    RuleEvaluationContext,
    RuleReason,
    RuleSet,
    RuleSourceLifecycle,
    RuleStatus,
    RuleWarning,
    SchedulingItem,
    SchedulingRuleId,
    SplitAction,
    UserRoutinePreference,
    evaluate_rule_engine,
    rule_result_is_stale,
)


def _trace() -> ComputationTrace:
    return ComputationTrace(
        operation="test_event_snapshot",
        rule_id="test",
        rule_version="1",
    )


def _amount(
    *,
    subject_id: str,
    value: str,
    unit: Unit = Unit.MILLIGRAM,
    amount_basis: AmountBasis = AmountBasis.ELEMENTAL,
    chemical_form_id: str | None = None,
    quantity_basis: QuantityBasis = QuantityBasis.ABSOLUTE,
) -> ComputedAmount:
    return ComputedAmount(
        subject_kind=SubjectKind.ANALYTE,
        subject_id=subject_id,
        value=Decimal(value),
        unit=unit,
        amount_basis=amount_basis,
        quantity_basis=quantity_basis,
        source_quantity_basis_ids=(),
        source_amount_ids=(f"amount:{subject_id}:{value}",),
        source_ids=(f"source:{subject_id}",),
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
    context_revision: str = "ctx:v1",
) -> SchedulingItem:
    return SchedulingItem(
        item_id=item_id,
        product_id=f"product:{item_id}",
        formulation_id=f"formulation:{item_id}",
        tracked_instance_id=f"instance:{item_id}",
        plan_id=f"plan:{item_id}",
        plan_version="1",
        event_id=event_id or f"event:{item_id}",
        context_revision=context_revision,
        source_kind=source_kind,
        amounts=tuple(amounts),
        confirmed_consumption_units=Decimal(units),
        units_independently_schedulable=schedulable,
        fixed_combination_id=fixed_combination_id,
    )


def _context(
    *items: SchedulingItem,
    meal_slots: tuple[MealSlot, ...] = (),
    instructions: tuple[AdministrationInstruction, ...] = (),
    conflicts: tuple[str, ...] = (),
    preferences: tuple[UserRoutinePreference, ...] = (),
    medication: bool = False,
    special_population: bool = False,
    revision: str = "ctx:v1",
) -> RuleEvaluationContext:
    return RuleEvaluationContext(
        context_revision=revision,
        items=tuple(items),
        meal_slots=meal_slots,
        instructions=instructions,
        instruction_conflict_item_ids=conflicts,
        user_preferences=preferences,
        medication_context_present=medication,
        special_population_context_present=special_population,
    )


def _bound_aggregation(
    aggregation: DailyAggregationResult,
    *,
    revision: str = "ctx:v1",
) -> BoundDailyAggregation:
    return BoundDailyAggregation(
        aggregation=aggregation,
        context_revision=revision,
    )


def _rule_results(result: object, rule_id: SchedulingRuleId) -> list[object]:
    scheduling = result.scheduling_results  # type: ignore[attr-defined]
    return [candidate for candidate in scheduling if candidate.rule_id is rule_id]


def _matched(result: object, rule_id: SchedulingRuleId) -> list[object]:
    return [
        candidate
        for candidate in _rule_results(result, rule_id)
        if candidate.status is RuleStatus.MATCHED_PREFERENCE
    ]


def test_ruleset_contains_exactly_the_five_authorized_automatic_rules() -> None:
    assert RULESET_VERSION == DEFAULT_RULESET.version
    assert {definition.rule_id for definition in DEFAULT_RULESET.definitions} == {
        SchedulingRuleId.VD_WITH_FAT_MEAL_PREFERENCE,
        SchedulingRuleId.CALCIUM_CARBONATE_WITH_MEAL,
        SchedulingRuleId.CALCIUM_IRON_AVOID_SAME_EVENT,
        SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT,
        SchedulingRuleId.CALCIUM_SPLIT_EVENT_PREFERENCE,
    }
    assert all(
        "OMEGA3" not in definition.rule_id.value for definition in DEFAULT_RULESET.definitions
    )


def test_vitamin_d_with_known_fat_slot_is_soft_preference_without_clock_time() -> None:
    vitamin_d = _item(
        "vitamin-d",
        _amount(subject_id=VITAMIN_D_ANALYTE_ID, value="25", unit=Unit.MICROGRAM),
    )
    slot = MealSlot(
        slot_id="meal:lunch",
        context_revision="ctx:v1",
        is_meal_or_snack=True,
        contains_dietary_fat=True,
    )

    result = evaluate_rule_engine(_context(vitamin_d, meal_slots=(slot,)))
    matches = _matched(result, SchedulingRuleId.VD_WITH_FAT_MEAL_PREFERENCE)

    assert len(matches) == 1
    match = matches[0]
    assert match.decision_class is RuleDecisionClass.PREFERENCE
    assert match.meal_context_preference is MealContextPreference.MEAL_OR_SNACK_WITH_SOME_FAT
    assert match.preferred_slot_ids == ("meal:lunch",)
    assert match.clock_time_preference is None
    assert match.medical_necessity_claim_allowed is False
    assert RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY in match.warnings


def test_vitamin_d_unknown_fat_context_fails_closed_without_invented_meal() -> None:
    vitamin_d = _item(
        "vitamin-d",
        _amount(subject_id=VITAMIN_D_ANALYTE_ID, value="25", unit=Unit.MICROGRAM),
    )
    unknown = MealSlot(
        slot_id="meal:unknown",
        context_revision="ctx:v1",
        is_meal_or_snack=True,
        contains_dietary_fat=None,
    )

    result = evaluate_rule_engine(_context(vitamin_d, meal_slots=(unknown,)))
    candidates = _rule_results(result, SchedulingRuleId.VD_WITH_FAT_MEAL_PREFERENCE)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.status is RuleStatus.INSUFFICIENT_EVIDENCE
    assert candidate.reason is RuleReason.MEAL_FAT_CONTEXT_REQUIRED
    assert candidate.preferred_slot_ids == ()
    assert candidate.clock_time_preference is None


def test_calcium_carbonate_matches_but_citrate_and_unknown_form_do_not() -> None:
    carbonate = _item(
        "carbonate",
        _amount(
            subject_id=CALCIUM_ANALYTE_ID,
            value="500",
            chemical_form_id=CALCIUM_CARBONATE_FORM_ID,
        ),
    )
    citrate = _item(
        "citrate",
        _amount(
            subject_id=CALCIUM_ANALYTE_ID,
            value="500",
            chemical_form_id=CALCIUM_CITRATE_FORM_ID,
        ),
    )
    unknown = _item(
        "unknown-calcium",
        _amount(subject_id=CALCIUM_ANALYTE_ID, value="500"),
    )

    result = evaluate_rule_engine(_context(carbonate, citrate, unknown))
    candidates = _rule_results(result, SchedulingRuleId.CALCIUM_CARBONATE_WITH_MEAL)

    by_item = {candidate.item_ids[0]: candidate for candidate in candidates}
    assert by_item["carbonate"].status is RuleStatus.MATCHED_PREFERENCE
    assert by_item["carbonate"].meal_context_preference is MealContextPreference.WITH_MEAL
    assert by_item["citrate"].status is RuleStatus.NO_SUPPORTED_RULE_FOUND
    assert by_item["citrate"].reason is RuleReason.CALCIUM_FORM_NOT_CARBONATE
    assert by_item["unknown-calcium"].status is RuleStatus.INSUFFICIENT_EVIDENCE
    assert by_item["unknown-calcium"].reason is RuleReason.CALCIUM_FORM_REQUIRED


def test_calcium_and_iron_separate_products_prefer_different_event_with_null_gap() -> None:
    calcium = _item(
        "calcium",
        _amount(subject_id=CALCIUM_ANALYTE_ID, value="300"),
    )
    iron = _item(
        "iron",
        _amount(subject_id=IRON_ANALYTE_ID, value="10"),
    )

    result = evaluate_rule_engine(_context(calcium, iron))
    matches = _matched(result, SchedulingRuleId.CALCIUM_IRON_AVOID_SAME_EVENT)

    assert len(matches) == 1
    match = matches[0]
    assert match.event_relation is EventRelation.AVOID_SAME_EVENT
    assert match.minimum_gap_minutes is None
    assert RuleWarning.NULL_GAP_MUST_REMAIN_NULL in match.warnings


def test_fixed_calcium_iron_combination_is_not_logically_split() -> None:
    combo = _item(
        "combo",
        _amount(subject_id=CALCIUM_ANALYTE_ID, value="300"),
        _amount(subject_id=IRON_ANALYTE_ID, value="10"),
        fixed_combination_id="fixed:combo",
    )

    result = evaluate_rule_engine(_context(combo))
    candidates = _rule_results(result, SchedulingRuleId.CALCIUM_IRON_AVOID_SAME_EVENT)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.status is RuleStatus.CANNOT_OPTIMIZE_FIXED_COMBINATION
    assert candidate.reason is RuleReason.FIXED_COMBINATION_CANNOT_SPLIT
    assert candidate.event_relation is None
    assert candidate.minimum_gap_minutes is None
    assert RuleWarning.FIXED_COMBINATION_NOT_SPLITTABLE in candidate.warnings


def test_exact_25_mg_elemental_supplemental_iron_triggers_zinc_preference() -> None:
    iron = _item(
        "iron",
        _amount(subject_id=IRON_ANALYTE_ID, value="25"),
    )
    zinc = _item(
        "zinc",
        _amount(subject_id=ZINC_ANALYTE_ID, value="10"),
    )

    result = evaluate_rule_engine(_context(iron, zinc))
    matches = _matched(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT)

    assert len(matches) == 1
    match = matches[0]
    assert match.event_relation is EventRelation.AVOID_SAME_EVENT
    assert match.minimum_gap_minutes is None
    assert match.personalized_dose_instruction_allowed is False


def test_24_95_mg_iron_does_not_trigger_after_display_rounding() -> None:
    iron = _item(
        "iron",
        _amount(subject_id=IRON_ANALYTE_ID, value="24.95"),
    )
    zinc = _item(
        "zinc",
        _amount(subject_id=ZINC_ANALYTE_ID, value="10"),
    )

    result = evaluate_rule_engine(_context(iron, zinc))
    assert _matched(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT) == []
    candidates = _rule_results(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT)
    assert any(candidate.reason is RuleReason.IRON_THRESHOLD_NOT_MET for candidate in candidates)


def test_25_micrograms_is_not_25_milligrams() -> None:
    iron = _item(
        "iron",
        _amount(subject_id=IRON_ANALYTE_ID, value="25", unit=Unit.MICROGRAM),
    )
    zinc = _item(
        "zinc",
        _amount(subject_id=ZINC_ANALYTE_ID, value="10"),
    )

    result = evaluate_rule_engine(_context(iron, zinc))
    assert _matched(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT) == []


def test_non_elemental_iron_amount_cannot_satisfy_threshold() -> None:
    iron = _item(
        "iron",
        _amount(
            subject_id=IRON_ANALYTE_ID,
            value="125",
            amount_basis=AmountBasis.ANALYTE,
        ),
    )
    zinc = _item(
        "zinc",
        _amount(subject_id=ZINC_ANALYTE_ID, value="10"),
    )

    result = evaluate_rule_engine(_context(iron, zinc))
    candidates = _rule_results(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT)

    assert _matched(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT) == []
    assert any(
        candidate.reason is RuleReason.ELEMENTAL_IRON_AMOUNT_REQUIRED
        and candidate.status is RuleStatus.INSUFFICIENT_EVIDENCE
        for candidate in candidates
    )


def test_fortified_food_iron_cannot_satisfy_supplemental_trigger() -> None:
    iron = _item(
        "fortified-iron",
        _amount(subject_id=IRON_ANALYTE_ID, value="30"),
        source_kind=ItemSourceKind.FORTIFIED_FOOD,
    )
    zinc = _item(
        "zinc",
        _amount(subject_id=ZINC_ANALYTE_ID, value="10"),
    )

    result = evaluate_rule_engine(_context(iron, zinc))
    candidates = _rule_results(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT)

    assert _matched(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT) == []
    assert any(
        candidate.reason is RuleReason.IRON_SOURCE_NOT_SUPPLEMENT for candidate in candidates
    )


def test_two_subthreshold_iron_products_are_not_silently_aggregated() -> None:
    iron_a = _item(
        "iron-a",
        _amount(subject_id=IRON_ANALYTE_ID, value="15"),
        event_id="event:together",
    )
    iron_b = _item(
        "iron-b",
        _amount(subject_id=IRON_ANALYTE_ID, value="15"),
        event_id="event:together",
    )
    zinc = _item(
        "zinc",
        _amount(subject_id=ZINC_ANALYTE_ID, value="10"),
        event_id="event:together",
    )

    result = evaluate_rule_engine(_context(iron_a, iron_b, zinc))
    candidates = _rule_results(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT)

    assert _matched(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT) == []
    assert any(
        candidate.reason is RuleReason.MULTIPLE_SUBTHRESHOLD_IRON_AGGREGATION_NOT_VALIDATED
        and candidate.status is RuleStatus.INSUFFICIENT_EVIDENCE
        for candidate in candidates
    )


def test_fixed_iron_zinc_combination_stays_one_product_event() -> None:
    combo = _item(
        "iron-zinc-combo",
        _amount(subject_id=IRON_ANALYTE_ID, value="25"),
        _amount(subject_id=ZINC_ANALYTE_ID, value="10"),
        fixed_combination_id="fixed:iron-zinc",
    )

    result = evaluate_rule_engine(_context(combo))
    candidates = _rule_results(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT)

    assert len(candidates) == 1
    assert candidates[0].status is RuleStatus.CANNOT_OPTIMIZE_FIXED_COMBINATION
    assert candidates[0].event_relation is None


def test_two_intact_500_mg_calcium_units_can_be_rearranged_without_dose_creation() -> None:
    calcium = _item(
        "calcium",
        _amount(subject_id=CALCIUM_ANALYTE_ID, value="1000"),
        units="2",
        schedulable=True,
    )

    result = evaluate_rule_engine(_context(calcium))
    matches = _matched(result, SchedulingRuleId.CALCIUM_SPLIT_EVENT_PREFERENCE)

    assert len(matches) == 1
    match = matches[0]
    assert match.split_action is SplitAction.DISTRIBUTE_EXISTING_INTACT_UNITS
    assert match.personalized_dose_instruction_allowed is False
    assert RuleWarning.NO_PERSONALIZED_DOSE in match.warnings


def test_one_indivisible_1000_mg_calcium_unit_cannot_become_two_doses() -> None:
    calcium = _item(
        "calcium",
        _amount(subject_id=CALCIUM_ANALYTE_ID, value="1000"),
        units="1",
        schedulable=True,
    )

    result = evaluate_rule_engine(_context(calcium))
    candidates = _rule_results(result, SchedulingRuleId.CALCIUM_SPLIT_EVENT_PREFERENCE)

    assert _matched(result, SchedulingRuleId.CALCIUM_SPLIT_EVENT_PREFERENCE) == []
    assert any(
        candidate.reason is RuleReason.INTACT_UNITS_NOT_REARRANGEABLE for candidate in candidates
    )


def test_product_or_clinician_instruction_blocks_generic_optimization() -> None:
    calcium = _item(
        "calcium",
        _amount(
            subject_id=CALCIUM_ANALYTE_ID,
            value="500",
            chemical_form_id=CALCIUM_CARBONATE_FORM_ID,
        ),
    )
    instruction = AdministrationInstruction(
        instruction_id="product:take-fasting",
        kind=InstructionKind.PRODUCT,
        item_id="calcium",
        context_revision="ctx:v1",
    )

    result = evaluate_rule_engine(_context(calcium, instructions=(instruction,)))
    candidates = _rule_results(result, SchedulingRuleId.CALCIUM_CARBONATE_WITH_MEAL)

    assert len(candidates) == 1
    assert candidates[0].status is RuleStatus.BLOCKED_BY_HIGHER_PRECEDENCE
    assert candidates[0].reason is RuleReason.HIGHER_PRECEDENCE_INSTRUCTION
    assert candidates[0].resolution_path is ResolutionPath.SURFACE_HIGHER_PRECEDENCE_INSTRUCTION


def test_conflicting_higher_precedence_instructions_surface_conflict() -> None:
    calcium = _item(
        "calcium",
        _amount(
            subject_id=CALCIUM_ANALYTE_ID,
            value="500",
            chemical_form_id=CALCIUM_CARBONATE_FORM_ID,
        ),
    )
    instruction = AdministrationInstruction(
        instruction_id="clinician:custom",
        kind=InstructionKind.CLINICIAN,
        item_id="calcium",
        context_revision="ctx:v1",
    )

    result = evaluate_rule_engine(
        _context(
            calcium,
            instructions=(instruction,),
            conflicts=("calcium",),
        )
    )
    candidates = _rule_results(result, SchedulingRuleId.CALCIUM_CARBONATE_WITH_MEAL)

    assert candidates[0].reason is RuleReason.CONFLICTING_HIGHER_PRECEDENCE_INSTRUCTIONS
    assert candidates[0].status is RuleStatus.BLOCKED_BY_HIGHER_PRECEDENCE


@pytest.mark.parametrize(
    ("medication", "special_population", "expected_reason"),
    [
        (True, False, GlobalReason.MEDICATION_CONTEXT_UNVALIDATED),
        (False, True, GlobalReason.SPECIAL_POPULATION_CONTEXT_UNVALIDATED),
    ],
)
def test_high_risk_context_withholds_generic_scheduling(
    medication: bool,
    special_population: bool,
    expected_reason: GlobalReason,
) -> None:
    vitamin_d = _item(
        "vitamin-d",
        _amount(subject_id=VITAMIN_D_ANALYTE_ID, value="25", unit=Unit.MICROGRAM),
    )

    result = evaluate_rule_engine(
        _context(
            vitamin_d,
            medication=medication,
            special_population=special_population,
        )
    )

    assert result.global_status is RuleEngineGlobalStatus.WITHHELD_HIGH_RISK_CONTEXT
    assert expected_reason in result.global_reasons
    assert result.scheduling_results == ()


def test_user_routine_preference_remains_separate_from_scientific_provenance() -> None:
    magnesium = _item(
        "magnesium",
        _amount(subject_id="analyte:magnesium", value="100"),
    )
    preference = UserRoutinePreference(
        preference_id="user:evening",
        item_id="magnesium",
        bucket=RoutineBucket.EVENING,
        context_revision="ctx:v1",
    )

    result = evaluate_rule_engine(_context(magnesium, preferences=(preference,)))

    assert result.user_preferences == (preference,)
    assert result.user_preferences[0].provenance_kind == "user_preference"
    no_rule = result.scheduling_results[0]
    assert no_rule.rule_id is SchedulingRuleId.NO_SUPPORTED_RULE_FOUND
    assert no_rule.clock_time_preference is None
    assert RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE in no_rule.warnings


def test_generic_omega3_ethyl_ester_status_has_no_automatic_rule() -> None:
    omega = _item(
        "omega",
        _amount(
            subject_id="analyte:epa-plus-dha",
            value="1000",
            amount_basis=AmountBasis.ANALYTE,
            chemical_form_id="chemical-form:ethyl-ester",
        ),
    )

    result = evaluate_rule_engine(_context(omega))

    assert len(result.scheduling_results) == 1
    assert result.scheduling_results[0].rule_id is SchedulingRuleId.NO_SUPPORTED_RULE_FOUND
    assert all("OMEGA3" not in candidate.rule_id.value for candidate in result.scheduling_results)


def test_rule_result_retains_rule_source_and_version_provenance() -> None:
    iron = _item(
        "iron",
        _amount(subject_id=IRON_ANALYTE_ID, value="25"),
    )
    zinc = _item(
        "zinc",
        _amount(subject_id=ZINC_ANALYTE_ID, value="10"),
    )

    result = evaluate_rule_engine(_context(iron, zinc))
    match = _matched(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT)[0]

    assert match.ruleset_version == RULESET_VERSION
    assert match.rule_version == "1"
    assert {source.source_key for source in match.source_provenance} == {
        "ODS-IRON",
        "ODS-ZINC",
    }
    assert all(source.version_label for source in match.source_provenance)


def test_rule_result_becomes_stale_on_context_revision_change() -> None:
    calcium = _item(
        "calcium",
        _amount(
            subject_id=CALCIUM_ANALYTE_ID,
            value="500",
            chemical_form_id=CALCIUM_CARBONATE_FORM_ID,
        ),
    )
    result = evaluate_rule_engine(_context(calcium))
    match = _matched(result, SchedulingRuleId.CALCIUM_CARBONATE_WITH_MEAL)[0]

    assert rule_result_is_stale(match, context_revision="ctx:v1") is False
    assert rule_result_is_stale(match, context_revision="ctx:v2") is True


def test_rule_result_becomes_stale_when_source_is_superseded() -> None:
    calcium = _item(
        "calcium",
        _amount(
            subject_id=CALCIUM_ANALYTE_ID,
            value="500",
            chemical_form_id=CALCIUM_CARBONATE_FORM_ID,
        ),
    )
    result = evaluate_rule_engine(_context(calcium))
    match = _matched(result, SchedulingRuleId.CALCIUM_CARBONATE_WITH_MEAL)[0]

    changed_sources = tuple(
        replace(
            source,
            lifecycle=RuleSourceLifecycle.SUPERSEDED,
            superseded_by_source_key="ODS-CALCIUM-NEXT",
        )
        if source.source_key == "ODS-CALCIUM"
        else source
        for source in DEFAULT_RULESET.sources
    )
    changed_ruleset = RuleSet(
        version=DEFAULT_RULESET.version,
        sources=changed_sources,
        definitions=DEFAULT_RULESET.definitions,
    )

    assert (
        rule_result_is_stale(
            match,
            context_revision="ctx:v1",
            ruleset=changed_ruleset,
        )
        is True
    )


def test_context_revision_mismatch_is_rejected_before_evaluation() -> None:
    item = _item(
        "calcium",
        _amount(subject_id=CALCIUM_ANALYTE_ID, value="500"),
        context_revision="ctx:v1",
    )

    with pytest.raises(RuleDataError, match="revision differs"):
        _context(item, revision="ctx:v2")


def test_input_order_does_not_change_scheduling_results() -> None:
    iron = _item(
        "iron",
        _amount(subject_id=IRON_ANALYTE_ID, value="25"),
    )
    zinc = _item(
        "zinc",
        _amount(subject_id=ZINC_ANALYTE_ID, value="10"),
    )
    calcium = _item(
        "calcium",
        _amount(subject_id=CALCIUM_ANALYTE_ID, value="300"),
    )

    first = evaluate_rule_engine(_context(iron, zinc, calcium))
    second = evaluate_rule_engine(_context(calcium, zinc, iron))

    assert first.scheduling_results == second.scheduling_results


def _daily_amount(
    subject_id: str,
    value: str,
    unit: Unit,
) -> ComputedAmount:
    return _amount(
        subject_id=subject_id,
        value=value,
        unit=unit,
        amount_basis=AmountBasis.ANALYTE,
        quantity_basis=QuantityBasis.PER_DAY,
    )


def _daily_aggregate(
    *,
    subject_id: str,
    value: str,
    unit: Unit,
    complete: bool = True,
) -> DailyAggregate:
    original = _daily_amount(subject_id, value, unit)
    contributor = ResolvedContribution(
        contribution_id=f"contribution:{subject_id}",
        confirmation_ref="confirmation:test",
        product_id="product:test",
        formulation_id="formulation:test",
        tracked_instance_id="instance:test",
        plan_id="plan:test",
        plan_version="1",
        normalized_value=Decimal(value),
        normalized_unit=unit,
        original_amount=original,
    )
    return DailyAggregate(
        key=AggregateKey(
            subject_kind=SubjectKind.ANALYTE,
            subject_id=subject_id,
            amount_basis=AmountBasis.ANALYTE,
            equivalence_basis=None,
            dimension=UnitDimension.MASS,
        ),
        known_total=Decimal(value),
        unit=unit,
        is_complete=complete,
        issues=() if complete else (AggregationIssue.UNRESOLVED_CONTRIBUTOR,),
        contributors=(contributor,),
        suppressed_exact_repeat_ids=(),
    )


def test_duplicate_source_flags_remain_informational_not_safety_verdicts() -> None:
    aggregation = DailyAggregationResult(
        aggregates=(),
        unresolved_contributors=(),
        duplicate_flags=(
            DuplicateFlag(
                kind=DuplicateFlagKind.SHARED_SOURCE_LINEAGE,
                contribution_ids=("c2", "c1"),
                shared_source_ids=("label:1",),
            ),
        ),
    )

    result = evaluate_rule_engine(
        _context(),
        aggregation=_bound_aggregation(aggregation),
    )

    assert len(result.duplicate_results) == 1
    duplicate = result.duplicate_results[0]
    assert duplicate.status is DuplicateResultStatus.INFORMATIONAL
    assert duplicate.contribution_ids == ("c1", "c2")
    assert duplicate.context_revision == "ctx:v1"
    assert duplicate.personal_safety_conclusion_withheld is True


def test_complete_daily_aggregate_can_use_kir115_reference_api_without_dose_derivation() -> None:
    aggregate = _daily_aggregate(
        subject_id="analyte:selenium",
        value="200",
        unit=Unit.MICROGRAM,
    )
    aggregation = DailyAggregationResult(
        aggregates=(aggregate,),
        unresolved_contributors=(),
        duplicate_flags=(),
    )
    query = ReferenceQuery(
        substance_key="selenium",
        reference_type=ReferenceType.UL,
        profile=PopulationProfile(
            age_months=360,
            sex=SexApplicability.FEMALE,
            life_stage=LifeStage.GENERAL,
        ),
        exposure=ExposureContext(exposure_basis=ExposureBasis.TOTAL_INTAKE),
        context_revision="ctx:v1",
    )
    request = ReferenceComparisonRequest(
        request_id="selenium-ul",
        aggregate_key=aggregate.key,
        query=query,
    )

    result = evaluate_rule_engine(
        _context(),
        aggregation=_bound_aggregation(aggregation),
        reference_requests=(request,),
    )

    assert len(result.reference_results) == 1
    evaluated = result.reference_results[0]
    assert evaluated.status is ReferenceEvaluationStatus.EVALUATED
    assert evaluated.context_revision == "ctx:v1"
    assert evaluated.comparison is not None
    assert evaluated.comparison.relation is ComparisonRelation.BELOW
    assert evaluated.personal_safety_conclusion_withheld is True
    assert evaluated.personalized_product_unit_dose_derived is False


def test_incomplete_daily_aggregate_is_not_silently_compared_as_confirmed_total() -> None:
    aggregate = _daily_aggregate(
        subject_id="analyte:selenium",
        value="200",
        unit=Unit.MICROGRAM,
        complete=False,
    )
    aggregation = DailyAggregationResult(
        aggregates=(aggregate,),
        unresolved_contributors=(),
        duplicate_flags=(),
    )
    query = ReferenceQuery(
        substance_key="selenium",
        reference_type=ReferenceType.UL,
        profile=PopulationProfile(
            age_months=360,
            sex=SexApplicability.FEMALE,
            life_stage=LifeStage.GENERAL,
        ),
        exposure=ExposureContext(exposure_basis=ExposureBasis.TOTAL_INTAKE),
        context_revision="ctx:v1",
    )
    request = ReferenceComparisonRequest(
        request_id="selenium-ul",
        aggregate_key=aggregate.key,
        query=query,
    )

    result = evaluate_rule_engine(
        _context(),
        aggregation=_bound_aggregation(aggregation),
        reference_requests=(request,),
    )

    evaluated = result.reference_results[0]
    assert evaluated.status is ReferenceEvaluationStatus.AGGREGATE_INCOMPLETE
    assert evaluated.comparison is None
    assert AggregationIssue.UNRESOLVED_CONTRIBUTOR in evaluated.aggregate_issues


def test_reference_query_cannot_be_rebound_to_another_rule_context_revision() -> None:
    aggregate = _daily_aggregate(
        subject_id="analyte:selenium",
        value="200",
        unit=Unit.MICROGRAM,
    )
    aggregation = DailyAggregationResult(
        aggregates=(aggregate,),
        unresolved_contributors=(),
        duplicate_flags=(),
    )
    request = ReferenceComparisonRequest(
        request_id="selenium-ul",
        aggregate_key=aggregate.key,
        query=ReferenceQuery(
            substance_key="selenium",
            reference_type=ReferenceType.UL,
            profile=PopulationProfile(
                age_months=360,
                sex=SexApplicability.FEMALE,
                life_stage=LifeStage.GENERAL,
            ),
            exposure=ExposureContext(exposure_basis=ExposureBasis.TOTAL_INTAKE),
            context_revision="ctx:v2",
        ),
    )

    with pytest.raises(RuleDataError, match="reference query revision"):
        evaluate_rule_engine(
            _context(),
            aggregation=_bound_aggregation(aggregation),
            reference_requests=(request,),
        )


def test_stale_aggregation_cannot_be_rebound_for_reference_comparison() -> None:
    aggregate = _daily_aggregate(
        subject_id="analyte:selenium",
        value="200",
        unit=Unit.MICROGRAM,
    )
    aggregation = DailyAggregationResult(
        aggregates=(aggregate,),
        unresolved_contributors=(),
        duplicate_flags=(),
    )
    request = ReferenceComparisonRequest(
        request_id="selenium-ul-v2",
        aggregate_key=aggregate.key,
        query=ReferenceQuery(
            substance_key="selenium",
            reference_type=ReferenceType.UL,
            profile=PopulationProfile(
                age_months=360,
                sex=SexApplicability.FEMALE,
                life_stage=LifeStage.GENERAL,
            ),
            exposure=ExposureContext(exposure_basis=ExposureBasis.TOTAL_INTAKE),
            context_revision="ctx:v2",
        ),
    )

    with pytest.raises(RuleDataError, match="daily aggregation revision"):
        evaluate_rule_engine(
            _context(revision="ctx:v2"),
            aggregation=_bound_aggregation(aggregation, revision="ctx:v1"),
            reference_requests=(request,),
        )


def test_stale_aggregation_cannot_be_rebound_for_duplicate_source_output() -> None:
    aggregation = DailyAggregationResult(
        aggregates=(),
        unresolved_contributors=(),
        duplicate_flags=(
            DuplicateFlag(
                kind=DuplicateFlagKind.SHARED_SOURCE_LINEAGE,
                contribution_ids=("c1", "c2"),
                shared_source_ids=("label:v1",),
            ),
        ),
    )

    with pytest.raises(RuleDataError, match="daily aggregation revision"):
        evaluate_rule_engine(
            _context(revision="ctx:v2"),
            aggregation=_bound_aggregation(aggregation, revision="ctx:v1"),
        )


def test_structured_scientific_results_cannot_encode_numeric_gap_or_clock_claim() -> None:
    iron = _item(
        "iron",
        _amount(subject_id=IRON_ANALYTE_ID, value="25"),
    )
    zinc = _item(
        "zinc",
        _amount(subject_id=ZINC_ANALYTE_ID, value="10"),
    )

    result = evaluate_rule_engine(_context(iron, zinc))
    match = _matched(result, SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT)[0]

    assert match.minimum_gap_minutes is None
    assert match.clock_time_preference is None
    assert match.medical_necessity_claim_allowed is False
    assert match.personal_safety_conclusion_withheld is True
    assert RuleWarning.LLM_MUST_NOT_STRENGTHEN in match.warnings
