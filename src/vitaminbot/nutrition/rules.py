from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Final

from vitaminbot.domain import (
    AmountBasis,
    QuantityBasis,
    SubjectKind,
    Unit,
)
from vitaminbot.nutrition.aggregation import (
    AggregateKey,
    AggregationIssue,
    DailyAggregate,
    DailyAggregationResult,
    DuplicateFlagKind,
)
from vitaminbot.nutrition.normalization import (
    ComputedAmount,
    DimensionMismatchError,
    convert_mass,
)
from vitaminbot.nutrition.reference_values import (
    EU_EFSA_REFERENCE_DATASET,
    ComparisonResult,
    ReferenceDataset,
    ReferenceQuery,
    compare_amount_to_reference,
    lookup_reference,
)


class RuleDataError(ValueError):
    """Raised when governed rule data or evaluation input is internally inconsistent."""


class SchedulingRuleId(StrEnum):
    VD_WITH_FAT_MEAL_PREFERENCE = "VD_WITH_FAT_MEAL_PREFERENCE"
    CALCIUM_CARBONATE_WITH_MEAL = "CALCIUM_CARBONATE_WITH_MEAL"
    CALCIUM_IRON_AVOID_SAME_EVENT = "CALCIUM_IRON_AVOID_SAME_EVENT"
    IRON25_ZINC_AVOID_SAME_EVENT = "IRON25_ZINC_AVOID_SAME_EVENT"
    CALCIUM_SPLIT_EVENT_PREFERENCE = "CALCIUM_SPLIT_EVENT_PREFERENCE"
    NO_SUPPORTED_RULE_FOUND = "NO_SUPPORTED_RULE_FOUND"


class RuleType(StrEnum):
    MEAL_CONTEXT = "meal_context"
    AVOID_SAME_EVENT = "avoid_same_event"
    SPLIT_EVENT_PREFERENCE = "split_event_preference"
    NO_SUPPORTED_RULE = "no_supported_rule"


class RuleDecisionClass(StrEnum):
    PREFERENCE = "preference"
    INFORMATIONAL = "informational"
    INDETERMINATE = "indeterminate"


class RuleStatus(StrEnum):
    MATCHED_PREFERENCE = "matched_preference"
    NO_SUPPORTED_RULE_FOUND = "no_supported_rule_found"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    BLOCKED_BY_HIGHER_PRECEDENCE = "blocked_by_higher_precedence"
    CANNOT_OPTIMIZE_FIXED_COMBINATION = "cannot_optimize_fixed_combination"


class RuleReason(StrEnum):
    EXACT_APPLICABILITY_MATCH = "exact_applicability_match"
    NO_AUTHORIZED_RULE_MATCHED = "no_authorized_rule_matched"
    MEAL_FAT_CONTEXT_REQUIRED = "meal_fat_context_required"
    CALCIUM_FORM_REQUIRED = "calcium_form_required"
    CALCIUM_FORM_NOT_CARBONATE = "calcium_form_not_carbonate"
    ELEMENTAL_IRON_AMOUNT_REQUIRED = "elemental_iron_amount_required"
    IRON_SOURCE_NOT_SUPPLEMENT = "iron_source_not_supplement"
    IRON_THRESHOLD_NOT_MET = "iron_threshold_not_met"
    MULTIPLE_SUBTHRESHOLD_IRON_AGGREGATION_NOT_VALIDATED = (
        "multiple_subthreshold_iron_aggregation_not_validated"
    )
    FIXED_COMBINATION_CANNOT_SPLIT = "fixed_combination_cannot_split"
    ITEMS_NOT_SEPARATELY_SCHEDULABLE = "items_not_separately_schedulable"
    HIGHER_PRECEDENCE_INSTRUCTION = "higher_precedence_instruction"
    CONFLICTING_HIGHER_PRECEDENCE_INSTRUCTIONS = (
        "conflicting_higher_precedence_instructions"
    )
    CALCIUM_ELEMENTAL_AMOUNT_REQUIRED = "calcium_elemental_amount_required"
    INTACT_UNITS_NOT_REARRANGEABLE = "intact_units_not_rearrangeable"
    SPLIT_EVIDENCE_BOUNDARY_NOT_REACHED = "split_evidence_boundary_not_reached"


class EventRelation(StrEnum):
    AVOID_SAME_EVENT = "avoid_same_event"


class MealContextPreference(StrEnum):
    MEAL_OR_SNACK_WITH_SOME_FAT = "meal_or_snack_with_some_fat"
    WITH_MEAL = "with_meal"


class SplitAction(StrEnum):
    DISTRIBUTE_EXISTING_INTACT_UNITS = "distribute_existing_intact_units"


class ResolutionPath(StrEnum):
    APPLY_PREFERENCE = "apply_preference"
    KEEP_CURRENT_NO_AUTOMATION = "keep_current_no_automation"
    REQUIRE_CONFIRMATION = "require_confirmation"
    SURFACE_HIGHER_PRECEDENCE_INSTRUCTION = "surface_higher_precedence_instruction"
    SURFACE_FIXED_COMBINATION_LIMIT = "surface_fixed_combination_limit"


class RuleWarning(StrEnum):
    PREFERENCE_NOT_MEDICAL_NECESSITY = "preference_not_medical_necessity"
    NO_RULE_NOT_SAFETY_CLEARANCE = "no_rule_not_safety_clearance"
    NULL_GAP_MUST_REMAIN_NULL = "null_gap_must_remain_null"
    NO_PERSONALIZED_DOSE = "no_personalized_dose"
    FIXED_COMBINATION_NOT_SPLITTABLE = "fixed_combination_not_splittable"
    USER_PREFERENCE_NOT_SCIENTIFIC_EVIDENCE = "user_preference_not_scientific_evidence"
    MEDICATION_NO_RESULT_NOT_NO_INTERACTION = "medication_no_result_not_no_interaction"
    LLM_MUST_NOT_STRENGTHEN = "llm_must_not_strengthen"


class RuleFact(StrEnum):
    IDENTITY_CONFIRMED = "identity_confirmed"
    FORM_CONFIRMED = "form_confirmed"
    ELEMENTAL_AMOUNT_CONFIRMED = "elemental_amount_confirmed"
    SUPPLEMENT_SOURCE_CONFIRMED = "supplement_source_confirmed"
    SEPARATELY_SCHEDULABLE = "separately_schedulable"
    MEAL_FAT_CONTEXT_CONFIRMED = "meal_fat_context_confirmed"
    THRESHOLD_MET = "threshold_met"
    THRESHOLD_NOT_MET = "threshold_not_met"
    EXISTING_UNITS_REARRANGEABLE = "existing_units_rearrangeable"
    FIXED_COMBINATION = "fixed_combination"
    HIGHER_PRECEDENCE_INSTRUCTION = "higher_precedence_instruction"


class RuleUnknown(StrEnum):
    MEAL_FAT_CONTEXT = "meal_fat_context"
    CALCIUM_FORM = "calcium_form"
    ELEMENTAL_IRON_AMOUNT = "elemental_iron_amount"
    MULTI_IRON_EVENT_AGGREGATION = "multi_iron_event_aggregation"
    INSTRUCTION_CONFLICT = "instruction_conflict"
    MEDICATION_INTERACTION = "medication_interaction"
    SPECIAL_POPULATION_APPLICABILITY = "special_population_applicability"
    PRODUCT_UNIT_REARRANGEMENT = "product_unit_rearrangement"


class RuleSourceType(StrEnum):
    OFFICIAL_MONOGRAPH = "official_monograph"
    PEER_REVIEWED_TRIAL = "peer_reviewed_trial"


class RuleSourceLifecycle(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class NumericParameterRole(StrEnum):
    TRIGGER_THRESHOLD = "trigger_threshold"
    EVIDENCE_BOUNDARY_NOT_DOSE = "evidence_boundary_not_dose"


class ItemSourceKind(StrEnum):
    SUPPLEMENT = "supplement"
    FORTIFIED_FOOD = "fortified_food"
    OTHER = "other"


class InstructionKind(StrEnum):
    PRODUCT = "product"
    CLINICIAN = "clinician"


class RoutineBucket(StrEnum):
    MORNING = "morning"
    DAY = "day"
    EVENING = "evening"


class RuleEngineGlobalStatus(StrEnum):
    READY = "ready"
    WITHHELD_HIGH_RISK_CONTEXT = "withheld_high_risk_context"


class GlobalReason(StrEnum):
    MEDICATION_CONTEXT_UNVALIDATED = "medication_context_unvalidated"
    SPECIAL_POPULATION_CONTEXT_UNVALIDATED = "special_population_context_unvalidated"


class DuplicateResultStatus(StrEnum):
    INFORMATIONAL = "informational"


class ReferenceEvaluationStatus(StrEnum):
    EVALUATED = "evaluated"
    AGGREGATE_NOT_FOUND = "aggregate_not_found"
    AGGREGATE_INCOMPLETE = "aggregate_incomplete"


CALCIUM_CARBONATE_FORM_ID: Final = "chemical-form:calcium-carbonate"
CALCIUM_CITRATE_FORM_ID: Final = "chemical-form:calcium-citrate"
VITAMIN_D_ANALYTE_ID: Final = "analyte:vitamin-d"
CALCIUM_ANALYTE_ID: Final = "analyte:calcium"
IRON_ANALYTE_ID: Final = "analyte:iron"
ZINC_ANALYTE_ID: Final = "analyte:zinc"
RULESET_VERSION: Final = "kir-119-2026-09-20.v1"
GOVERNANCE_REFS: Final = ("KIR-119", "KIR-143", "KIR-144")


@dataclass(frozen=True, slots=True, kw_only=True)
class RuleSource:
    source_key: str
    authority: str
    title: str
    source_type: RuleSourceType
    jurisdiction_note: str
    stable_identifier: str
    version_label: str
    retrieved_on: date
    source_url: str
    locator: str
    lifecycle: RuleSourceLifecycle = RuleSourceLifecycle.ACTIVE
    superseded_by_source_key: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("source_key", self.source_key),
            ("authority", self.authority),
            ("title", self.title),
            ("jurisdiction_note", self.jurisdiction_note),
            ("stable_identifier", self.stable_identifier),
            ("version_label", self.version_label),
            ("source_url", self.source_url),
            ("locator", self.locator),
        ):
            if not value.strip():
                raise RuleDataError(f"{field_name} must not be blank")
        if self.superseded_by_source_key is not None:
            if not self.superseded_by_source_key.strip():
                raise RuleDataError("superseded_by_source_key must not be blank")
            if self.superseded_by_source_key == self.source_key:
                raise RuleDataError("a rule source cannot supersede itself")


@dataclass(frozen=True, slots=True, kw_only=True)
class NumericRuleParameter:
    name: str
    value: Decimal
    unit: Unit
    amount_basis: AmountBasis
    role: NumericParameterRole
    source_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise RuleDataError("numeric parameter name must not be blank")
        if not self.value.is_finite() or self.value < 0:
            raise RuleDataError("numeric parameter value must be finite and non-negative")
        if not self.source_keys:
            raise RuleDataError("numeric parameter requires source provenance")
        if any(not source_key.strip() for source_key in self.source_keys):
            raise RuleDataError("numeric parameter source keys must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class RuleDefinition:
    rule_id: SchedulingRuleId
    rule_version: str
    rule_type: RuleType
    source_keys: tuple[str, ...]
    numeric_parameters: tuple[NumericRuleParameter, ...] = ()

    def __post_init__(self) -> None:
        if not self.rule_version.strip():
            raise RuleDataError("rule_version must not be blank")
        if not self.source_keys:
            raise RuleDataError("scientific rule definition requires source provenance")
        if any(not source_key.strip() for source_key in self.source_keys):
            raise RuleDataError("rule definition source keys must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class RuleSet:
    version: str
    sources: tuple[RuleSource, ...]
    definitions: tuple[RuleDefinition, ...]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise RuleDataError("ruleset version must not be blank")
        source_keys = tuple(source.source_key for source in self.sources)
        if len(set(source_keys)) != len(source_keys):
            raise RuleDataError("rule source keys must be unique")
        rule_ids = tuple(definition.rule_id for definition in self.definitions)
        if len(set(rule_ids)) != len(rule_ids):
            raise RuleDataError("rule IDs must be unique")
        source_key_set = set(source_keys)
        for definition in self.definitions:
            if any(source_key not in source_key_set for source_key in definition.source_keys):
                raise RuleDataError("rule definition references unknown source")
            for parameter in definition.numeric_parameters:
                if any(source_key not in source_key_set for source_key in parameter.source_keys):
                    raise RuleDataError("numeric parameter references unknown source")

    def get_source(self, source_key: str) -> RuleSource | None:
        return next((source for source in self.sources if source.source_key == source_key), None)

    def get_definition(self, rule_id: SchedulingRuleId) -> RuleDefinition | None:
        return next(
            (definition for definition in self.definitions if definition.rule_id is rule_id),
            None,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AdministrationInstruction:
    instruction_id: str
    kind: InstructionKind
    item_id: str
    context_revision: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("instruction_id", self.instruction_id),
            ("item_id", self.item_id),
            ("context_revision", self.context_revision),
        ):
            if not value.strip():
                raise RuleDataError(f"{field_name} must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class UserRoutinePreference:
    preference_id: str
    item_id: str
    bucket: RoutineBucket
    context_revision: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("preference_id", self.preference_id),
            ("item_id", self.item_id),
            ("context_revision", self.context_revision),
        ):
            if not value.strip():
                raise RuleDataError(f"{field_name} must not be blank")

    @property
    def provenance_kind(self) -> str:
        return "user_preference"


@dataclass(frozen=True, slots=True, kw_only=True)
class MealSlot:
    slot_id: str
    context_revision: str
    is_meal_or_snack: bool
    contains_dietary_fat: bool | None = None

    def __post_init__(self) -> None:
        if not self.slot_id.strip():
            raise RuleDataError("slot_id must not be blank")
        if not self.context_revision.strip():
            raise RuleDataError("meal slot context_revision must not be blank")
        if not self.is_meal_or_snack and self.contains_dietary_fat is True:
            raise RuleDataError("non-meal slot cannot assert dietary-fat meal context")


@dataclass(frozen=True, slots=True, kw_only=True)
class SchedulingItem:
    item_id: str
    product_id: str
    formulation_id: str
    tracked_instance_id: str
    plan_id: str
    plan_version: str
    event_id: str
    context_revision: str
    source_kind: ItemSourceKind
    amounts: tuple[ComputedAmount, ...]
    confirmed_consumption_units: Decimal
    units_independently_schedulable: bool
    fixed_combination_id: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("item_id", self.item_id),
            ("product_id", self.product_id),
            ("formulation_id", self.formulation_id),
            ("tracked_instance_id", self.tracked_instance_id),
            ("plan_id", self.plan_id),
            ("plan_version", self.plan_version),
            ("event_id", self.event_id),
            ("context_revision", self.context_revision),
        ):
            if not value.strip():
                raise RuleDataError(f"{field_name} must not be blank")
        if not self.amounts:
            raise RuleDataError("scheduling item requires at least one canonical amount")
        if any(amount.quantity_basis is not QuantityBasis.ABSOLUTE for amount in self.amounts):
            raise RuleDataError(
                "scheduling item amounts must be ABSOLUTE planned-event snapshots"
            )
        if (
            not self.confirmed_consumption_units.is_finite()
            or self.confirmed_consumption_units <= 0
        ):
            raise RuleDataError(
                "confirmed_consumption_units must be finite and greater than zero"
            )
        if self.fixed_combination_id is not None and not self.fixed_combination_id.strip():
            raise RuleDataError("fixed_combination_id must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class RuleEvaluationContext:
    context_revision: str
    items: tuple[SchedulingItem, ...]
    meal_slots: tuple[MealSlot, ...] = ()
    instructions: tuple[AdministrationInstruction, ...] = ()
    instruction_conflict_item_ids: tuple[str, ...] = ()
    user_preferences: tuple[UserRoutinePreference, ...] = ()
    medication_context_present: bool = False
    special_population_context_present: bool = False

    def __post_init__(self) -> None:
        if not self.context_revision.strip():
            raise RuleDataError("context_revision must not be blank")
        item_ids = tuple(item.item_id for item in self.items)
        if len(set(item_ids)) != len(item_ids):
            raise RuleDataError("scheduling item IDs must be unique")
        item_id_set = set(item_ids)
        for item in self.items:
            if item.context_revision != self.context_revision:
                raise RuleDataError(
                    "scheduling item revision differs from evaluation context revision"
                )
        slot_ids = tuple(slot.slot_id for slot in self.meal_slots)
        if len(set(slot_ids)) != len(slot_ids):
            raise RuleDataError("meal slot IDs must be unique")
        for slot in self.meal_slots:
            if slot.context_revision != self.context_revision:
                raise RuleDataError(
                    "meal slot revision differs from evaluation context revision"
                )
        instruction_ids = tuple(instruction.instruction_id for instruction in self.instructions)
        if len(set(instruction_ids)) != len(instruction_ids):
            raise RuleDataError("administration instruction IDs must be unique")
        for instruction in self.instructions:
            if instruction.item_id not in item_id_set:
                raise RuleDataError("administration instruction references unknown item")
            if instruction.context_revision != self.context_revision:
                raise RuleDataError(
                    "instruction revision differs from evaluation context revision"
                )
        for item_id in self.instruction_conflict_item_ids:
            if item_id not in item_id_set:
                raise RuleDataError("instruction conflict references unknown item")
        preference_ids = tuple(preference.preference_id for preference in self.user_preferences)
        if len(set(preference_ids)) != len(preference_ids):
            raise RuleDataError("user preference IDs must be unique")
        for preference in self.user_preferences:
            if preference.item_id not in item_id_set:
                raise RuleDataError("user preference references unknown item")
            if preference.context_revision != self.context_revision:
                raise RuleDataError(
                    "user preference revision differs from evaluation context revision"
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class SchedulingRuleResult:
    result_id: str
    ruleset_version: str
    rule_id: SchedulingRuleId
    rule_version: str | None
    rule_type: RuleType
    status: RuleStatus
    decision_class: RuleDecisionClass
    reason: RuleReason
    context_revision: str
    item_ids: tuple[str, ...]
    source_provenance: tuple[RuleSource, ...]
    known_facts: tuple[RuleFact, ...] = ()
    unknown_facts: tuple[RuleUnknown, ...] = ()
    event_relation: EventRelation | None = None
    meal_context_preference: MealContextPreference | None = None
    preferred_slot_ids: tuple[str, ...] = ()
    split_action: SplitAction | None = None
    minimum_gap_minutes: int | None = None
    clock_time_preference: RoutineBucket | None = None
    resolution_path: ResolutionPath = ResolutionPath.KEEP_CURRENT_NO_AUTOMATION
    warnings: tuple[RuleWarning, ...] = ()
    governance_refs: tuple[str, ...] = GOVERNANCE_REFS

    def __post_init__(self) -> None:
        if not self.result_id.strip():
            raise RuleDataError("result_id must not be blank")
        if not self.ruleset_version.strip():
            raise RuleDataError("ruleset_version must not be blank")
        if not self.context_revision.strip():
            raise RuleDataError("result context_revision must not be blank")
        if not self.item_ids:
            raise RuleDataError("rule result requires at least one item")
        if any(not item_id.strip() for item_id in self.item_ids):
            raise RuleDataError("rule result item IDs must not be blank")
        if self.minimum_gap_minutes is not None:
            raise RuleDataError("KIR-119 does not authorize a generic numeric separation gap")
        if self.clock_time_preference is not None:
            raise RuleDataError(
                "KIR-119 has no authorized scientific Morning/Day/Evening preference"
            )
        if self.status is RuleStatus.MATCHED_PREFERENCE:
            if self.decision_class is not RuleDecisionClass.PREFERENCE:
                raise RuleDataError("matched scheduling output must remain a preference")
            if self.rule_version is None or not self.rule_version.strip():
                raise RuleDataError("matched scientific rule requires rule version")
            if not self.source_provenance:
                raise RuleDataError("matched scientific rule requires source provenance")
        if self.rule_id is SchedulingRuleId.NO_SUPPORTED_RULE_FOUND:
            if self.status is not RuleStatus.NO_SUPPORTED_RULE_FOUND:
                raise RuleDataError("NO_SUPPORTED_RULE_FOUND meta rule requires no-rule status")
            if RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE not in self.warnings:
                raise RuleDataError("no-rule result must retain no-safety-clearance warning")

    @property
    def personal_safety_conclusion_withheld(self) -> bool:
        return True

    @property
    def personalized_dose_instruction_allowed(self) -> bool:
        return False

    @property
    def medical_necessity_claim_allowed(self) -> bool:
        return False


@dataclass(frozen=True, slots=True, kw_only=True)
class DuplicateSourceResult:
    status: DuplicateResultStatus
    duplicate_kind: DuplicateFlagKind
    contribution_ids: tuple[str, ...]
    counted_contribution_id: str | None
    shared_source_amount_ids: tuple[str, ...]
    shared_source_ids: tuple[str, ...]
    context_revision: str

    @property
    def personal_safety_conclusion_withheld(self) -> bool:
        return True


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceComparisonRequest:
    request_id: str
    aggregate_key: AggregateKey
    query: ReferenceQuery

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise RuleDataError("reference comparison request_id must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceRuleResult:
    request_id: str
    status: ReferenceEvaluationStatus
    context_revision: str
    aggregate_key: AggregateKey
    comparison: ComparisonResult | None
    aggregate_issues: tuple[AggregationIssue, ...] = ()

    @property
    def personal_safety_conclusion_withheld(self) -> bool:
        return True

    @property
    def personalized_product_unit_dose_derived(self) -> bool:
        return False


@dataclass(frozen=True, slots=True, kw_only=True)
class RuleEngineResult:
    ruleset_version: str
    context_revision: str
    global_status: RuleEngineGlobalStatus
    global_reasons: tuple[GlobalReason, ...]
    scheduling_results: tuple[SchedulingRuleResult, ...]
    duplicate_results: tuple[DuplicateSourceResult, ...]
    reference_results: tuple[ReferenceRuleResult, ...]
    user_preferences: tuple[UserRoutinePreference, ...]


_SOURCES: Final = (
    RuleSource(
        source_key="ODS-IRON",
        authority="NIH Office of Dietary Supplements",
        title="Iron — Health Professional Fact Sheet",
        source_type=RuleSourceType.OFFICIAL_MONOGRAPH,
        jurisdiction_note="U.S. public-health monograph; biological administration evidence",
        stable_identifier="https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/",
        version_label="updated-2025-09-04/retrieved-2026-09-20",
        retrieved_on=date(2026, 9, 20),
        source_url="https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/",
        locator="Interactions and administration sections used by KIR-143/KIR-144",
    ),
    RuleSource(
        source_key="ODS-ZINC",
        authority="NIH Office of Dietary Supplements",
        title="Zinc — Health Professional Fact Sheet",
        source_type=RuleSourceType.OFFICIAL_MONOGRAPH,
        jurisdiction_note="U.S. public-health monograph; biological administration evidence",
        stable_identifier="https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/",
        version_label="retrieved-2026-09-20",
        retrieved_on=date(2026, 9, 20),
        source_url="https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/",
        locator="Iron interaction section used by KIR-143/KIR-144",
    ),
    RuleSource(
        source_key="ODS-CALCIUM",
        authority="NIH Office of Dietary Supplements",
        title="Calcium — Health Professional Fact Sheet",
        source_type=RuleSourceType.OFFICIAL_MONOGRAPH,
        jurisdiction_note="U.S. public-health monograph; biological administration evidence",
        stable_identifier="https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/",
        version_label="retrieved-2026-09-20",
        retrieved_on=date(2026, 9, 20),
        source_url="https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/",
        locator="Absorption/form sections used by KIR-143/KIR-144",
    ),
    RuleSource(
        source_key="ODS-VD",
        authority="NIH Office of Dietary Supplements",
        title="Vitamin D — Health Professional Fact Sheet",
        source_type=RuleSourceType.OFFICIAL_MONOGRAPH,
        jurisdiction_note="U.S. public-health monograph; biological administration evidence",
        stable_identifier="https://ods.od.nih.gov/factsheets/VITAMIND/HealthProfessional/",
        version_label="retrieved-2026-09-20",
        retrieved_on=date(2026, 9, 20),
        source_url="https://ods.od.nih.gov/factsheets/VITAMIND/HealthProfessional/",
        locator="Absorption section used by KIR-143/KIR-144",
    ),
    RuleSource(
        source_key="VD-RCT-2015",
        authority="Dawson-Hughes et al.",
        title="Dietary fat increases vitamin D-3 absorption",
        source_type=RuleSourceType.PEER_REVIEWED_TRIAL,
        jurisdiction_note="Healthy older adults; absorption trial",
        stable_identifier="10.1016/j.jand.2014.09.014",
        version_label="J Acad Nutr Diet 2015;115(2):225-230",
        retrieved_on=date(2026, 9, 20),
        source_url="https://pubmed.ncbi.nlm.nih.gov/25441954/",
        locator="PMID 25441954",
    ),
)

_IRON_THRESHOLD: Final = NumericRuleParameter(
    name="elemental_iron_same_event_threshold",
    value=Decimal("25"),
    unit=Unit.MILLIGRAM,
    amount_basis=AmountBasis.ELEMENTAL,
    role=NumericParameterRole.TRIGGER_THRESHOLD,
    source_keys=("ODS-IRON", "ODS-ZINC"),
)

_CALCIUM_EVIDENCE_BOUNDARY: Final = NumericRuleParameter(
    name="calcium_absorption_evidence_boundary",
    value=Decimal("500"),
    unit=Unit.MILLIGRAM,
    amount_basis=AmountBasis.ELEMENTAL,
    role=NumericParameterRole.EVIDENCE_BOUNDARY_NOT_DOSE,
    source_keys=("ODS-CALCIUM",),
)

_DEFINITIONS: Final = (
    RuleDefinition(
        rule_id=SchedulingRuleId.VD_WITH_FAT_MEAL_PREFERENCE,
        rule_version="1",
        rule_type=RuleType.MEAL_CONTEXT,
        source_keys=("ODS-VD", "VD-RCT-2015"),
    ),
    RuleDefinition(
        rule_id=SchedulingRuleId.CALCIUM_CARBONATE_WITH_MEAL,
        rule_version="1",
        rule_type=RuleType.MEAL_CONTEXT,
        source_keys=("ODS-CALCIUM",),
    ),
    RuleDefinition(
        rule_id=SchedulingRuleId.CALCIUM_IRON_AVOID_SAME_EVENT,
        rule_version="1",
        rule_type=RuleType.AVOID_SAME_EVENT,
        source_keys=("ODS-IRON",),
    ),
    RuleDefinition(
        rule_id=SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT,
        rule_version="1",
        rule_type=RuleType.AVOID_SAME_EVENT,
        source_keys=("ODS-IRON", "ODS-ZINC"),
        numeric_parameters=(_IRON_THRESHOLD,),
    ),
    RuleDefinition(
        rule_id=SchedulingRuleId.CALCIUM_SPLIT_EVENT_PREFERENCE,
        rule_version="1",
        rule_type=RuleType.SPLIT_EVENT_PREFERENCE,
        source_keys=("ODS-CALCIUM",),
        numeric_parameters=(_CALCIUM_EVIDENCE_BOUNDARY,),
    ),
)

DEFAULT_RULESET: Final = RuleSet(
    version=RULESET_VERSION,
    sources=_SOURCES,
    definitions=_DEFINITIONS,
)


def _require_definition(ruleset: RuleSet, rule_id: SchedulingRuleId) -> RuleDefinition:
    definition = ruleset.get_definition(rule_id)
    if definition is None:
        raise RuleDataError(f"ruleset lacks required definition: {rule_id.value}")
    return definition


def _parameter(definition: RuleDefinition, name: str) -> NumericRuleParameter:
    parameter = next(
        (candidate for candidate in definition.numeric_parameters if candidate.name == name),
        None,
    )
    if parameter is None:
        raise RuleDataError(f"rule {definition.rule_id.value} lacks parameter {name}")
    return parameter


def _provenance(ruleset: RuleSet, definition: RuleDefinition) -> tuple[RuleSource, ...]:
    sources: list[RuleSource] = []
    for source_key in definition.source_keys:
        source = ruleset.get_source(source_key)
        if source is None:
            raise RuleDataError("validated ruleset lost source provenance")
        sources.append(source)
    return tuple(sources)


def _amounts(item: SchedulingItem, subject_id: str) -> tuple[ComputedAmount, ...]:
    return tuple(amount for amount in item.amounts if amount.subject_id == subject_id)


def _has_subject(item: SchedulingItem, subject_id: str) -> bool:
    return bool(_amounts(item, subject_id))


def _elemental_mass_mg(item: SchedulingItem, subject_id: str) -> Decimal | None:
    candidates = tuple(
        amount
        for amount in _amounts(item, subject_id)
        if amount.subject_kind is SubjectKind.ANALYTE
        and amount.amount_basis is AmountBasis.ELEMENTAL
    )
    if len(candidates) != 1:
        return None
    amount = candidates[0]
    try:
        return convert_mass(amount.value, amount.unit, Unit.MILLIGRAM)
    except DimensionMismatchError:
        return None


def _exact_decimal_from_fraction(value: Fraction) -> Decimal:
    denominator = value.denominator
    twos = 0
    fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise RuleDataError("exact rule arithmetic unexpectedly produced non-terminating Decimal")
    scale = max(twos, fives)
    scaled_numerator = (
        value.numerator * (5 ** (scale - twos)) * (2 ** (scale - fives))
    )
    return Decimal(scaled_numerator).scaleb(-scale)


def _exact_sum(values: tuple[Decimal, ...]) -> Decimal:
    total = sum((Fraction(value) for value in values), start=Fraction(0))
    return _exact_decimal_from_fraction(total)


def _instruction_state(
    context: RuleEvaluationContext,
    item_ids: tuple[str, ...],
) -> tuple[RuleReason | None, tuple[RuleFact, ...], tuple[RuleUnknown, ...]]:
    item_id_set = set(item_ids)
    instructions = tuple(
        instruction
        for instruction in context.instructions
        if instruction.item_id in item_id_set
    )
    conflict = any(item_id in context.instruction_conflict_item_ids for item_id in item_ids)
    if conflict:
        return (
            RuleReason.CONFLICTING_HIGHER_PRECEDENCE_INSTRUCTIONS,
            (RuleFact.HIGHER_PRECEDENCE_INSTRUCTION,),
            (RuleUnknown.INSTRUCTION_CONFLICT,),
        )
    if instructions:
        return (
            RuleReason.HIGHER_PRECEDENCE_INSTRUCTION,
            (RuleFact.HIGHER_PRECEDENCE_INSTRUCTION,),
            (),
        )
    return None, (), ()


def _result_id(
    rule_id: SchedulingRuleId,
    status: RuleStatus,
    item_ids: tuple[str, ...],
    context_revision: str,
    *,
    suffix: str = "",
) -> str:
    parts = ["kir119", rule_id.value, status.value, *sorted(item_ids), context_revision]
    if suffix:
        parts.append(suffix)
    return ":".join(parts)


def _scientific_result(
    *,
    ruleset: RuleSet,
    definition: RuleDefinition,
    status: RuleStatus,
    decision_class: RuleDecisionClass,
    reason: RuleReason,
    context_revision: str,
    item_ids: tuple[str, ...],
    known_facts: tuple[RuleFact, ...] = (),
    unknown_facts: tuple[RuleUnknown, ...] = (),
    event_relation: EventRelation | None = None,
    meal_context_preference: MealContextPreference | None = None,
    preferred_slot_ids: tuple[str, ...] = (),
    split_action: SplitAction | None = None,
    resolution_path: ResolutionPath = ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
    warnings: tuple[RuleWarning, ...] = (),
    suffix: str = "",
) -> SchedulingRuleResult:
    return SchedulingRuleResult(
        result_id=_result_id(
            definition.rule_id,
            status,
            item_ids,
            context_revision,
            suffix=suffix,
        ),
        ruleset_version=ruleset.version,
        rule_id=definition.rule_id,
        rule_version=definition.rule_version,
        rule_type=definition.rule_type,
        status=status,
        decision_class=decision_class,
        reason=reason,
        context_revision=context_revision,
        item_ids=tuple(sorted(item_ids)),
        source_provenance=_provenance(ruleset, definition),
        known_facts=tuple(sorted(set(known_facts), key=lambda fact: fact.value)),
        unknown_facts=tuple(sorted(set(unknown_facts), key=lambda fact: fact.value)),
        event_relation=event_relation,
        meal_context_preference=meal_context_preference,
        preferred_slot_ids=tuple(sorted(set(preferred_slot_ids))),
        split_action=split_action,
        minimum_gap_minutes=None,
        clock_time_preference=None,
        resolution_path=resolution_path,
        warnings=tuple(sorted(set(warnings), key=lambda warning: warning.value)),
    )


def _blocked_by_instruction(
    *,
    context: RuleEvaluationContext,
    ruleset: RuleSet,
    definition: RuleDefinition,
    item_ids: tuple[str, ...],
) -> SchedulingRuleResult | None:
    reason, known_facts, unknown_facts = _instruction_state(context, item_ids)
    if reason is None:
        return None
    return _scientific_result(
        ruleset=ruleset,
        definition=definition,
        status=RuleStatus.BLOCKED_BY_HIGHER_PRECEDENCE,
        decision_class=RuleDecisionClass.INDETERMINATE,
        reason=reason,
        context_revision=context.context_revision,
        item_ids=item_ids,
        known_facts=known_facts,
        unknown_facts=unknown_facts,
        resolution_path=ResolutionPath.SURFACE_HIGHER_PRECEDENCE_INSTRUCTION,
        warnings=(
            RuleWarning.NO_PERSONALIZED_DOSE,
            RuleWarning.LLM_MUST_NOT_STRENGTHEN,
        ),
    )


def _fixed_combination(
    first: SchedulingItem,
    second: SchedulingItem,
) -> bool:
    if first.item_id == second.item_id:
        return True
    return (
        first.fixed_combination_id is not None
        and first.fixed_combination_id == second.fixed_combination_id
    )


def _evaluate_vitamin_d(
    context: RuleEvaluationContext,
    ruleset: RuleSet,
) -> list[SchedulingRuleResult]:
    definition = _require_definition(
        ruleset,
        SchedulingRuleId.VD_WITH_FAT_MEAL_PREFERENCE,
    )
    fat_slots = tuple(
        slot.slot_id
        for slot in context.meal_slots
        if slot.is_meal_or_snack and slot.contains_dietary_fat is True
    )
    results: list[SchedulingRuleResult] = []
    for item in sorted(context.items, key=lambda candidate: candidate.item_id):
        if not _has_subject(item, VITAMIN_D_ANALYTE_ID):
            continue
        blocked = _blocked_by_instruction(
            context=context,
            ruleset=ruleset,
            definition=definition,
            item_ids=(item.item_id,),
        )
        if blocked is not None:
            results.append(blocked)
            continue
        if not fat_slots:
            results.append(
                _scientific_result(
                    ruleset=ruleset,
                    definition=definition,
                    status=RuleStatus.INSUFFICIENT_EVIDENCE,
                    decision_class=RuleDecisionClass.INDETERMINATE,
                    reason=RuleReason.MEAL_FAT_CONTEXT_REQUIRED,
                    context_revision=context.context_revision,
                    item_ids=(item.item_id,),
                    known_facts=(RuleFact.IDENTITY_CONFIRMED,),
                    unknown_facts=(RuleUnknown.MEAL_FAT_CONTEXT,),
                    resolution_path=ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
                    warnings=(
                        RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY,
                        RuleWarning.NO_PERSONALIZED_DOSE,
                        RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                    ),
                )
            )
            continue
        results.append(
            _scientific_result(
                ruleset=ruleset,
                definition=definition,
                status=RuleStatus.MATCHED_PREFERENCE,
                decision_class=RuleDecisionClass.PREFERENCE,
                reason=RuleReason.EXACT_APPLICABILITY_MATCH,
                context_revision=context.context_revision,
                item_ids=(item.item_id,),
                known_facts=(
                    RuleFact.IDENTITY_CONFIRMED,
                    RuleFact.MEAL_FAT_CONTEXT_CONFIRMED,
                ),
                meal_context_preference=MealContextPreference.MEAL_OR_SNACK_WITH_SOME_FAT,
                preferred_slot_ids=fat_slots,
                resolution_path=ResolutionPath.APPLY_PREFERENCE,
                warnings=(
                    RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY,
                    RuleWarning.NO_PERSONALIZED_DOSE,
                    RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                ),
            )
        )
    return results


def _evaluate_calcium_carbonate(
    context: RuleEvaluationContext,
    ruleset: RuleSet,
) -> list[SchedulingRuleResult]:
    definition = _require_definition(
        ruleset,
        SchedulingRuleId.CALCIUM_CARBONATE_WITH_MEAL,
    )
    meal_slots = tuple(
        slot.slot_id for slot in context.meal_slots if slot.is_meal_or_snack
    )
    results: list[SchedulingRuleResult] = []
    for item in sorted(context.items, key=lambda candidate: candidate.item_id):
        calcium_amounts = _amounts(item, CALCIUM_ANALYTE_ID)
        if not calcium_amounts:
            continue
        form_ids = tuple(
            amount.chemical_form_id
            for amount in calcium_amounts
            if amount.chemical_form_id is not None
        )
        if not form_ids:
            results.append(
                _scientific_result(
                    ruleset=ruleset,
                    definition=definition,
                    status=RuleStatus.INSUFFICIENT_EVIDENCE,
                    decision_class=RuleDecisionClass.INDETERMINATE,
                    reason=RuleReason.CALCIUM_FORM_REQUIRED,
                    context_revision=context.context_revision,
                    item_ids=(item.item_id,),
                    known_facts=(RuleFact.IDENTITY_CONFIRMED,),
                    unknown_facts=(RuleUnknown.CALCIUM_FORM,),
                    resolution_path=ResolutionPath.REQUIRE_CONFIRMATION,
                    warnings=(
                        RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY,
                        RuleWarning.NO_PERSONALIZED_DOSE,
                        RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                    ),
                )
            )
            continue
        if CALCIUM_CARBONATE_FORM_ID not in form_ids:
            results.append(
                _scientific_result(
                    ruleset=ruleset,
                    definition=definition,
                    status=RuleStatus.NO_SUPPORTED_RULE_FOUND,
                    decision_class=RuleDecisionClass.INFORMATIONAL,
                    reason=RuleReason.CALCIUM_FORM_NOT_CARBONATE,
                    context_revision=context.context_revision,
                    item_ids=(item.item_id,),
                    known_facts=(RuleFact.IDENTITY_CONFIRMED, RuleFact.FORM_CONFIRMED),
                    resolution_path=ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
                    warnings=(
                        RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE,
                        RuleWarning.NO_PERSONALIZED_DOSE,
                        RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                    ),
                )
            )
            continue
        blocked = _blocked_by_instruction(
            context=context,
            ruleset=ruleset,
            definition=definition,
            item_ids=(item.item_id,),
        )
        if blocked is not None:
            results.append(blocked)
            continue
        results.append(
            _scientific_result(
                ruleset=ruleset,
                definition=definition,
                status=RuleStatus.MATCHED_PREFERENCE,
                decision_class=RuleDecisionClass.PREFERENCE,
                reason=RuleReason.EXACT_APPLICABILITY_MATCH,
                context_revision=context.context_revision,
                item_ids=(item.item_id,),
                known_facts=(RuleFact.IDENTITY_CONFIRMED, RuleFact.FORM_CONFIRMED),
                meal_context_preference=MealContextPreference.WITH_MEAL,
                preferred_slot_ids=meal_slots,
                resolution_path=ResolutionPath.APPLY_PREFERENCE,
                warnings=(
                    RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY,
                    RuleWarning.NO_PERSONALIZED_DOSE,
                    RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                ),
            )
        )
    return results


def _pair_candidates(
    context: RuleEvaluationContext,
    first_subject: str,
    second_subject: str,
) -> tuple[tuple[SchedulingItem, SchedulingItem], ...]:
    first_items = tuple(
        item
        for item in context.items
        if item.source_kind is ItemSourceKind.SUPPLEMENT
        and _has_subject(item, first_subject)
    )
    second_items = tuple(
        item
        for item in context.items
        if item.source_kind is ItemSourceKind.SUPPLEMENT
        and _has_subject(item, second_subject)
    )
    pairs: dict[tuple[str, str], tuple[SchedulingItem, SchedulingItem]] = {}
    for first in first_items:
        for second in second_items:
            key = (
                (first.item_id, second.item_id)
                if first.item_id <= second.item_id
                else (second.item_id, first.item_id)
            )
            pairs[key] = (first, second)
    return tuple(pairs[key] for key in sorted(pairs))


def _evaluate_calcium_iron(
    context: RuleEvaluationContext,
    ruleset: RuleSet,
) -> list[SchedulingRuleResult]:
    definition = _require_definition(
        ruleset,
        SchedulingRuleId.CALCIUM_IRON_AVOID_SAME_EVENT,
    )
    results: list[SchedulingRuleResult] = []
    for calcium, iron in _pair_candidates(
        context,
        CALCIUM_ANALYTE_ID,
        IRON_ANALYTE_ID,
    ):
        item_ids = tuple(sorted((calcium.item_id, iron.item_id)))
        if _fixed_combination(calcium, iron):
            results.append(
                _scientific_result(
                    ruleset=ruleset,
                    definition=definition,
                    status=RuleStatus.CANNOT_OPTIMIZE_FIXED_COMBINATION,
                    decision_class=RuleDecisionClass.INFORMATIONAL,
                    reason=RuleReason.FIXED_COMBINATION_CANNOT_SPLIT,
                    context_revision=context.context_revision,
                    item_ids=item_ids,
                    known_facts=(RuleFact.FIXED_COMBINATION,),
                    resolution_path=ResolutionPath.SURFACE_FIXED_COMBINATION_LIMIT,
                    warnings=(
                        RuleWarning.FIXED_COMBINATION_NOT_SPLITTABLE,
                        RuleWarning.NULL_GAP_MUST_REMAIN_NULL,
                        RuleWarning.NO_PERSONALIZED_DOSE,
                    ),
                )
            )
            continue
        if not (
            calcium.units_independently_schedulable
            and iron.units_independently_schedulable
        ):
            results.append(
                _scientific_result(
                    ruleset=ruleset,
                    definition=definition,
                    status=RuleStatus.INSUFFICIENT_EVIDENCE,
                    decision_class=RuleDecisionClass.INDETERMINATE,
                    reason=RuleReason.ITEMS_NOT_SEPARATELY_SCHEDULABLE,
                    context_revision=context.context_revision,
                    item_ids=item_ids,
                    unknown_facts=(RuleUnknown.PRODUCT_UNIT_REARRANGEMENT,),
                    resolution_path=ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
                    warnings=(
                        RuleWarning.FIXED_COMBINATION_NOT_SPLITTABLE,
                        RuleWarning.NULL_GAP_MUST_REMAIN_NULL,
                    ),
                )
            )
            continue
        blocked = _blocked_by_instruction(
            context=context,
            ruleset=ruleset,
            definition=definition,
            item_ids=item_ids,
        )
        if blocked is not None:
            results.append(blocked)
            continue
        results.append(
            _scientific_result(
                ruleset=ruleset,
                definition=definition,
                status=RuleStatus.MATCHED_PREFERENCE,
                decision_class=RuleDecisionClass.PREFERENCE,
                reason=RuleReason.EXACT_APPLICABILITY_MATCH,
                context_revision=context.context_revision,
                item_ids=item_ids,
                known_facts=(
                    RuleFact.IDENTITY_CONFIRMED,
                    RuleFact.SEPARATELY_SCHEDULABLE,
                ),
                event_relation=EventRelation.AVOID_SAME_EVENT,
                resolution_path=ResolutionPath.APPLY_PREFERENCE,
                warnings=(
                    RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY,
                    RuleWarning.NULL_GAP_MUST_REMAIN_NULL,
                    RuleWarning.NO_PERSONALIZED_DOSE,
                    RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                ),
            )
        )
    return results


def _iron_threshold_mg(ruleset: RuleSet) -> Decimal:
    definition = _require_definition(
        ruleset,
        SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT,
    )
    parameter = _parameter(definition, "elemental_iron_same_event_threshold")
    return convert_mass(parameter.value, parameter.unit, Unit.MILLIGRAM)


def _evaluate_multi_iron_unknown(
    context: RuleEvaluationContext,
    ruleset: RuleSet,
) -> list[SchedulingRuleResult]:
    definition = _require_definition(
        ruleset,
        SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT,
    )
    threshold = _iron_threshold_mg(ruleset)
    results: list[SchedulingRuleResult] = []
    event_ids = tuple(sorted({item.event_id for item in context.items}))
    for event_id in event_ids:
        zinc_items = tuple(
            item
            for item in context.items
            if item.event_id == event_id
            and item.source_kind is ItemSourceKind.SUPPLEMENT
            and _has_subject(item, ZINC_ANALYTE_ID)
        )
        if not zinc_items:
            continue
        iron_values: list[tuple[SchedulingItem, Decimal]] = []
        for item in context.items:
            if item.event_id != event_id or item.source_kind is not ItemSourceKind.SUPPLEMENT:
                continue
            value = _elemental_mass_mg(item, IRON_ANALYTE_ID)
            if value is not None and value < threshold:
                iron_values.append((item, value))
        if len(iron_values) < 2:
            continue
        total = _exact_sum(tuple(value for _, value in iron_values))
        if total < threshold:
            continue
        item_ids = tuple(
            sorted(
                {
                    *(item.item_id for item, _ in iron_values),
                    *(item.item_id for item in zinc_items),
                }
            )
        )
        results.append(
            _scientific_result(
                ruleset=ruleset,
                definition=definition,
                status=RuleStatus.INSUFFICIENT_EVIDENCE,
                decision_class=RuleDecisionClass.INDETERMINATE,
                reason=RuleReason.MULTIPLE_SUBTHRESHOLD_IRON_AGGREGATION_NOT_VALIDATED,
                context_revision=context.context_revision,
                item_ids=item_ids,
                known_facts=(RuleFact.SUPPLEMENT_SOURCE_CONFIRMED,),
                unknown_facts=(RuleUnknown.MULTI_IRON_EVENT_AGGREGATION,),
                resolution_path=ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
                warnings=(
                    RuleWarning.NULL_GAP_MUST_REMAIN_NULL,
                    RuleWarning.NO_PERSONALIZED_DOSE,
                    RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                ),
                suffix=event_id,
            )
        )
    return results


def _evaluate_iron_zinc(
    context: RuleEvaluationContext,
    ruleset: RuleSet,
) -> list[SchedulingRuleResult]:
    definition = _require_definition(
        ruleset,
        SchedulingRuleId.IRON25_ZINC_AVOID_SAME_EVENT,
    )
    threshold = _iron_threshold_mg(ruleset)
    results = _evaluate_multi_iron_unknown(context, ruleset)

    zinc_items = tuple(
        item
        for item in context.items
        if item.source_kind is ItemSourceKind.SUPPLEMENT
        and _has_subject(item, ZINC_ANALYTE_ID)
    )
    for iron in sorted(context.items, key=lambda candidate: candidate.item_id):
        if not _has_subject(iron, IRON_ANALYTE_ID):
            continue
        for zinc in sorted(zinc_items, key=lambda candidate: candidate.item_id):
            item_ids = tuple(sorted((iron.item_id, zinc.item_id)))
            if iron.source_kind is not ItemSourceKind.SUPPLEMENT:
                results.append(
                    _scientific_result(
                        ruleset=ruleset,
                        definition=definition,
                        status=RuleStatus.NO_SUPPORTED_RULE_FOUND,
                        decision_class=RuleDecisionClass.INFORMATIONAL,
                        reason=RuleReason.IRON_SOURCE_NOT_SUPPLEMENT,
                        context_revision=context.context_revision,
                        item_ids=item_ids,
                        known_facts=(RuleFact.IDENTITY_CONFIRMED,),
                        resolution_path=ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
                        warnings=(
                            RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE,
                            RuleWarning.NO_PERSONALIZED_DOSE,
                        ),
                    )
                )
                continue
            iron_value = _elemental_mass_mg(iron, IRON_ANALYTE_ID)
            if iron_value is None:
                results.append(
                    _scientific_result(
                        ruleset=ruleset,
                        definition=definition,
                        status=RuleStatus.INSUFFICIENT_EVIDENCE,
                        decision_class=RuleDecisionClass.INDETERMINATE,
                        reason=RuleReason.ELEMENTAL_IRON_AMOUNT_REQUIRED,
                        context_revision=context.context_revision,
                        item_ids=item_ids,
                        known_facts=(
                            RuleFact.IDENTITY_CONFIRMED,
                            RuleFact.SUPPLEMENT_SOURCE_CONFIRMED,
                        ),
                        unknown_facts=(RuleUnknown.ELEMENTAL_IRON_AMOUNT,),
                        resolution_path=ResolutionPath.REQUIRE_CONFIRMATION,
                        warnings=(
                            RuleWarning.NULL_GAP_MUST_REMAIN_NULL,
                            RuleWarning.NO_PERSONALIZED_DOSE,
                            RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                        ),
                    )
                )
                continue
            if iron_value < threshold:
                results.append(
                    _scientific_result(
                        ruleset=ruleset,
                        definition=definition,
                        status=RuleStatus.NO_SUPPORTED_RULE_FOUND,
                        decision_class=RuleDecisionClass.INFORMATIONAL,
                        reason=RuleReason.IRON_THRESHOLD_NOT_MET,
                        context_revision=context.context_revision,
                        item_ids=item_ids,
                        known_facts=(
                            RuleFact.ELEMENTAL_AMOUNT_CONFIRMED,
                            RuleFact.SUPPLEMENT_SOURCE_CONFIRMED,
                            RuleFact.THRESHOLD_NOT_MET,
                        ),
                        resolution_path=ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
                        warnings=(
                            RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE,
                            RuleWarning.NULL_GAP_MUST_REMAIN_NULL,
                            RuleWarning.NO_PERSONALIZED_DOSE,
                        ),
                    )
                )
                continue
            if _fixed_combination(iron, zinc):
                results.append(
                    _scientific_result(
                        ruleset=ruleset,
                        definition=definition,
                        status=RuleStatus.CANNOT_OPTIMIZE_FIXED_COMBINATION,
                        decision_class=RuleDecisionClass.INFORMATIONAL,
                        reason=RuleReason.FIXED_COMBINATION_CANNOT_SPLIT,
                        context_revision=context.context_revision,
                        item_ids=item_ids,
                        known_facts=(
                            RuleFact.ELEMENTAL_AMOUNT_CONFIRMED,
                            RuleFact.FIXED_COMBINATION,
                            RuleFact.THRESHOLD_MET,
                        ),
                        resolution_path=ResolutionPath.SURFACE_FIXED_COMBINATION_LIMIT,
                        warnings=(
                            RuleWarning.FIXED_COMBINATION_NOT_SPLITTABLE,
                            RuleWarning.NULL_GAP_MUST_REMAIN_NULL,
                            RuleWarning.NO_PERSONALIZED_DOSE,
                        ),
                    )
                )
                continue
            if not (
                iron.units_independently_schedulable
                and zinc.units_independently_schedulable
            ):
                results.append(
                    _scientific_result(
                        ruleset=ruleset,
                        definition=definition,
                        status=RuleStatus.INSUFFICIENT_EVIDENCE,
                        decision_class=RuleDecisionClass.INDETERMINATE,
                        reason=RuleReason.ITEMS_NOT_SEPARATELY_SCHEDULABLE,
                        context_revision=context.context_revision,
                        item_ids=item_ids,
                        known_facts=(
                            RuleFact.ELEMENTAL_AMOUNT_CONFIRMED,
                            RuleFact.THRESHOLD_MET,
                        ),
                        unknown_facts=(RuleUnknown.PRODUCT_UNIT_REARRANGEMENT,),
                        resolution_path=ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
                        warnings=(
                            RuleWarning.NULL_GAP_MUST_REMAIN_NULL,
                            RuleWarning.NO_PERSONALIZED_DOSE,
                        ),
                    )
                )
                continue
            blocked = _blocked_by_instruction(
                context=context,
                ruleset=ruleset,
                definition=definition,
                item_ids=item_ids,
            )
            if blocked is not None:
                results.append(blocked)
                continue
            results.append(
                _scientific_result(
                    ruleset=ruleset,
                    definition=definition,
                    status=RuleStatus.MATCHED_PREFERENCE,
                    decision_class=RuleDecisionClass.PREFERENCE,
                    reason=RuleReason.EXACT_APPLICABILITY_MATCH,
                    context_revision=context.context_revision,
                    item_ids=item_ids,
                    known_facts=(
                        RuleFact.ELEMENTAL_AMOUNT_CONFIRMED,
                        RuleFact.SUPPLEMENT_SOURCE_CONFIRMED,
                        RuleFact.SEPARATELY_SCHEDULABLE,
                        RuleFact.THRESHOLD_MET,
                    ),
                    event_relation=EventRelation.AVOID_SAME_EVENT,
                    resolution_path=ResolutionPath.APPLY_PREFERENCE,
                    warnings=(
                        RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY,
                        RuleWarning.NULL_GAP_MUST_REMAIN_NULL,
                        RuleWarning.NO_PERSONALIZED_DOSE,
                        RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                    ),
                )
            )
    return results


def _calcium_boundary_mg(ruleset: RuleSet) -> Decimal:
    definition = _require_definition(
        ruleset,
        SchedulingRuleId.CALCIUM_SPLIT_EVENT_PREFERENCE,
    )
    parameter = _parameter(definition, "calcium_absorption_evidence_boundary")
    return convert_mass(parameter.value, parameter.unit, Unit.MILLIGRAM)


def _is_integral(value: Decimal) -> bool:
    return value == value.to_integral_value()


def _evaluate_calcium_split(
    context: RuleEvaluationContext,
    ruleset: RuleSet,
) -> list[SchedulingRuleResult]:
    definition = _require_definition(
        ruleset,
        SchedulingRuleId.CALCIUM_SPLIT_EVENT_PREFERENCE,
    )
    boundary = _calcium_boundary_mg(ruleset)
    results: list[SchedulingRuleResult] = []
    for item in sorted(context.items, key=lambda candidate: candidate.item_id):
        if not _has_subject(item, CALCIUM_ANALYTE_ID):
            continue
        calcium_value = _elemental_mass_mg(item, CALCIUM_ANALYTE_ID)
        if calcium_value is None:
            results.append(
                _scientific_result(
                    ruleset=ruleset,
                    definition=definition,
                    status=RuleStatus.INSUFFICIENT_EVIDENCE,
                    decision_class=RuleDecisionClass.INDETERMINATE,
                    reason=RuleReason.CALCIUM_ELEMENTAL_AMOUNT_REQUIRED,
                    context_revision=context.context_revision,
                    item_ids=(item.item_id,),
                    unknown_facts=(RuleUnknown.PRODUCT_UNIT_REARRANGEMENT,),
                    resolution_path=ResolutionPath.REQUIRE_CONFIRMATION,
                    warnings=(
                        RuleWarning.NO_PERSONALIZED_DOSE,
                        RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                    ),
                )
            )
            continue
        units = item.confirmed_consumption_units
        if calcium_value <= boundary:
            results.append(
                _scientific_result(
                    ruleset=ruleset,
                    definition=definition,
                    status=RuleStatus.NO_SUPPORTED_RULE_FOUND,
                    decision_class=RuleDecisionClass.INFORMATIONAL,
                    reason=RuleReason.SPLIT_EVIDENCE_BOUNDARY_NOT_REACHED,
                    context_revision=context.context_revision,
                    item_ids=(item.item_id,),
                    known_facts=(RuleFact.ELEMENTAL_AMOUNT_CONFIRMED,),
                    resolution_path=ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
                    warnings=(
                        RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE,
                        RuleWarning.NO_PERSONALIZED_DOSE,
                    ),
                )
            )
            continue
        rearrangeable = (
            item.units_independently_schedulable
            and item.fixed_combination_id is None
            and _is_integral(units)
            and units >= Decimal(2)
            and calcium_value <= boundary * units
        )
        if not rearrangeable:
            results.append(
                _scientific_result(
                    ruleset=ruleset,
                    definition=definition,
                    status=RuleStatus.INSUFFICIENT_EVIDENCE,
                    decision_class=RuleDecisionClass.INDETERMINATE,
                    reason=RuleReason.INTACT_UNITS_NOT_REARRANGEABLE,
                    context_revision=context.context_revision,
                    item_ids=(item.item_id,),
                    known_facts=(RuleFact.ELEMENTAL_AMOUNT_CONFIRMED,),
                    unknown_facts=(RuleUnknown.PRODUCT_UNIT_REARRANGEMENT,),
                    resolution_path=ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
                    warnings=(
                        RuleWarning.NO_PERSONALIZED_DOSE,
                        RuleWarning.FIXED_COMBINATION_NOT_SPLITTABLE,
                        RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                    ),
                )
            )
            continue
        blocked = _blocked_by_instruction(
            context=context,
            ruleset=ruleset,
            definition=definition,
            item_ids=(item.item_id,),
        )
        if blocked is not None:
            results.append(blocked)
            continue
        results.append(
            _scientific_result(
                ruleset=ruleset,
                definition=definition,
                status=RuleStatus.MATCHED_PREFERENCE,
                decision_class=RuleDecisionClass.PREFERENCE,
                reason=RuleReason.EXACT_APPLICABILITY_MATCH,
                context_revision=context.context_revision,
                item_ids=(item.item_id,),
                known_facts=(
                    RuleFact.ELEMENTAL_AMOUNT_CONFIRMED,
                    RuleFact.EXISTING_UNITS_REARRANGEABLE,
                ),
                split_action=SplitAction.DISTRIBUTE_EXISTING_INTACT_UNITS,
                resolution_path=ResolutionPath.APPLY_PREFERENCE,
                warnings=(
                    RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY,
                    RuleWarning.NO_PERSONALIZED_DOSE,
                    RuleWarning.LLM_MUST_NOT_STRENGTHEN,
                ),
            )
        )
    return results


def _generic_no_rule(
    context: RuleEvaluationContext,
    item: SchedulingItem,
    ruleset: RuleSet,
) -> SchedulingRuleResult:
    return SchedulingRuleResult(
        result_id=_result_id(
            SchedulingRuleId.NO_SUPPORTED_RULE_FOUND,
            RuleStatus.NO_SUPPORTED_RULE_FOUND,
            (item.item_id,),
            context.context_revision,
        ),
        ruleset_version=ruleset.version,
        rule_id=SchedulingRuleId.NO_SUPPORTED_RULE_FOUND,
        rule_version=None,
        rule_type=RuleType.NO_SUPPORTED_RULE,
        status=RuleStatus.NO_SUPPORTED_RULE_FOUND,
        decision_class=RuleDecisionClass.INFORMATIONAL,
        reason=RuleReason.NO_AUTHORIZED_RULE_MATCHED,
        context_revision=context.context_revision,
        item_ids=(item.item_id,),
        source_provenance=(),
        resolution_path=ResolutionPath.KEEP_CURRENT_NO_AUTOMATION,
        warnings=(
            RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE,
            RuleWarning.NO_PERSONALIZED_DOSE,
            RuleWarning.LLM_MUST_NOT_STRENGTHEN,
        ),
    )


def _evaluate_scheduling(
    context: RuleEvaluationContext,
    ruleset: RuleSet,
) -> tuple[SchedulingRuleResult, ...]:
    results = [
        *_evaluate_vitamin_d(context, ruleset),
        *_evaluate_calcium_carbonate(context, ruleset),
        *_evaluate_calcium_iron(context, ruleset),
        *_evaluate_iron_zinc(context, ruleset),
        *_evaluate_calcium_split(context, ruleset),
    ]
    touched = {item_id for result in results for item_id in result.item_ids}
    for item in context.items:
        if item.item_id not in touched:
            results.append(_generic_no_rule(context, item, ruleset))
    return tuple(
        sorted(
            results,
            key=lambda result: (
                result.rule_id.value,
                result.item_ids,
                result.status.value,
                result.result_id,
            ),
        )
    )


def _duplicate_results(
    aggregation: DailyAggregationResult | None,
    context_revision: str,
) -> tuple[DuplicateSourceResult, ...]:
    if aggregation is None:
        return ()
    results = tuple(
        DuplicateSourceResult(
            status=DuplicateResultStatus.INFORMATIONAL,
            duplicate_kind=flag.kind,
            contribution_ids=tuple(sorted(flag.contribution_ids)),
            counted_contribution_id=flag.counted_contribution_id,
            shared_source_amount_ids=tuple(sorted(flag.shared_source_amount_ids)),
            shared_source_ids=tuple(sorted(flag.shared_source_ids)),
            context_revision=context_revision,
        )
        for flag in aggregation.duplicate_flags
    )
    return tuple(
        sorted(
            results,
            key=lambda result: (
                result.duplicate_kind.value,
                result.contribution_ids,
            ),
        )
    )


def _aggregate_amount(aggregate: DailyAggregate) -> ComputedAmount:
    if (
        not aggregate.is_complete
        or aggregate.known_total is None
        or aggregate.unit is None
        or not aggregate.contributors
    ):
        raise RuleDataError("cannot build reference input from incomplete daily aggregate")

    contributors = tuple(
        sorted(aggregate.contributors, key=lambda contributor: contributor.contribution_id)
    )
    source_quantity_basis_ids = tuple(
        sorted(
            {
                basis_id
                for contributor in contributors
                for basis_id in contributor.original_amount.source_quantity_basis_ids
            }
        )
    )
    source_amount_ids = tuple(
        sorted(
            {
                amount_id
                for contributor in contributors
                for amount_id in contributor.original_amount.source_amount_ids
            }
        )
    )
    source_ids = tuple(
        sorted(
            {
                source_id
                for contributor in contributors
                for source_id in contributor.original_amount.source_ids
            }
        )
    )
    traces = tuple(
        trace
        for contributor in contributors
        for trace in contributor.original_amount.traces
    )

    return ComputedAmount(
        subject_kind=aggregate.key.subject_kind,
        subject_id=aggregate.key.subject_id,
        value=aggregate.known_total,
        unit=aggregate.unit,
        amount_basis=aggregate.key.amount_basis,
        quantity_basis=QuantityBasis.PER_DAY,
        source_quantity_basis_ids=source_quantity_basis_ids,
        source_amount_ids=source_amount_ids,
        source_ids=source_ids,
        traces=traces,
        equivalence_basis=aggregate.key.equivalence_basis,
    )


def _reference_results(
    *,
    aggregation: DailyAggregationResult | None,
    requests: tuple[ReferenceComparisonRequest, ...],
    dataset: ReferenceDataset,
    context_revision: str,
) -> tuple[ReferenceRuleResult, ...]:
    if not requests:
        return ()
    if aggregation is None:
        raise RuleDataError("reference requests require a DailyAggregationResult")

    results: list[ReferenceRuleResult] = []
    for request in sorted(requests, key=lambda candidate: candidate.request_id):
        if request.query.context_revision != context_revision:
            raise RuleDataError(
                "reference query revision must match immutable rule evaluation context"
            )
        matches = tuple(
            aggregate
            for aggregate in aggregation.aggregates
            if aggregate.key == request.aggregate_key
        )
        if not matches:
            results.append(
                ReferenceRuleResult(
                    request_id=request.request_id,
                    status=ReferenceEvaluationStatus.AGGREGATE_NOT_FOUND,
                    context_revision=context_revision,
                    aggregate_key=request.aggregate_key,
                    comparison=None,
                )
            )
            continue
        if len(matches) != 1:
            raise RuleDataError("daily aggregation contains duplicate aggregate keys")
        aggregate = matches[0]
        if (
            not aggregate.is_complete
            or aggregate.known_total is None
            or aggregate.unit is None
            or not aggregate.contributors
        ):
            results.append(
                ReferenceRuleResult(
                    request_id=request.request_id,
                    status=ReferenceEvaluationStatus.AGGREGATE_INCOMPLETE,
                    context_revision=context_revision,
                    aggregate_key=request.aggregate_key,
                    comparison=None,
                    aggregate_issues=aggregate.issues,
                )
            )
            continue
        amount = _aggregate_amount(aggregate)
        lookup = lookup_reference(dataset, request.query)
        comparison = compare_amount_to_reference(amount, lookup)
        results.append(
            ReferenceRuleResult(
                request_id=request.request_id,
                status=ReferenceEvaluationStatus.EVALUATED,
                context_revision=context_revision,
                aggregate_key=request.aggregate_key,
                comparison=comparison,
                aggregate_issues=aggregate.issues,
            )
        )
    return tuple(results)


def evaluate_rule_engine(
    context: RuleEvaluationContext,
    *,
    aggregation: DailyAggregationResult | None = None,
    reference_requests: tuple[ReferenceComparisonRequest, ...] = (),
    reference_dataset: ReferenceDataset = EU_EFSA_REFERENCE_DATASET,
    ruleset: RuleSet = DEFAULT_RULESET,
) -> RuleEngineResult:
    global_reasons: list[GlobalReason] = []
    if context.medication_context_present:
        global_reasons.append(GlobalReason.MEDICATION_CONTEXT_UNVALIDATED)
    if context.special_population_context_present:
        global_reasons.append(GlobalReason.SPECIAL_POPULATION_CONTEXT_UNVALIDATED)

    scheduling_results: tuple[SchedulingRuleResult, ...]
    if global_reasons:
        scheduling_results = ()
        global_status = RuleEngineGlobalStatus.WITHHELD_HIGH_RISK_CONTEXT
    else:
        scheduling_results = _evaluate_scheduling(context, ruleset)
        global_status = RuleEngineGlobalStatus.READY

    return RuleEngineResult(
        ruleset_version=ruleset.version,
        context_revision=context.context_revision,
        global_status=global_status,
        global_reasons=tuple(sorted(global_reasons, key=lambda reason: reason.value)),
        scheduling_results=scheduling_results,
        duplicate_results=_duplicate_results(aggregation, context.context_revision),
        reference_results=_reference_results(
            aggregation=aggregation,
            requests=reference_requests,
            dataset=reference_dataset,
            context_revision=context.context_revision,
        ),
        user_preferences=tuple(
            sorted(context.user_preferences, key=lambda preference: preference.preference_id)
        ),
    )


def rule_result_is_stale(
    result: SchedulingRuleResult,
    *,
    context_revision: str,
    ruleset: RuleSet = DEFAULT_RULESET,
) -> bool:
    if result.context_revision != context_revision:
        return True
    if result.ruleset_version != ruleset.version:
        return True
    if result.rule_id is SchedulingRuleId.NO_SUPPORTED_RULE_FOUND:
        return False

    definition = ruleset.get_definition(result.rule_id)
    if definition is None or definition.rule_version != result.rule_version:
        return True

    current_sources = {source.source_key: source for source in ruleset.sources}
    for snapshot in result.source_provenance:
        current = current_sources.get(snapshot.source_key)
        if current is None:
            return True
        if current.lifecycle is not RuleSourceLifecycle.ACTIVE:
            return True
        if current.version_label != snapshot.version_label:
            return True
        if current.stable_identifier != snapshot.stable_identifier:
            return True
    return False
