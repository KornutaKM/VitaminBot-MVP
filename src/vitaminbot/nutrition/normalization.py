from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from vitaminbot.domain import (
    AmountBasis,
    AmountRecord,
    IntakePlan,
    QuantityBasis,
    ResolutionStatus,
    ServingDefinition,
    SubjectKind,
    Unit,
    UnitDimension,
    unit_dimension,
)


class NormalizationError(ValueError):
    """Base error for deterministic normalization contract violations."""


class DimensionMismatchError(NormalizationError):
    """Raised when a generic conversion crosses incompatible dimensions."""


class RuleValidationError(NormalizationError):
    """Raised when a scientific conversion rule is internally invalid."""


class RuleApplicationError(NormalizationError):
    """Raised when a valid rule is applied to an incompatible amount."""


class BasisMismatchError(NormalizationError):
    """Raised when source serving/basis wiring is inconsistent."""


class RoundingRequiredError(NormalizationError):
    """Raised when an exact finite Decimal result is impossible without policy."""


class RoundingMode(StrEnum):
    HALF_EVEN = "half_even"
    HALF_UP = "half_up"


class UnresolvedReason(StrEnum):
    INPUT_UNRESOLVED = "input_unresolved"
    CHEMICAL_FORM_REQUIRED = "chemical_form_required"
    CHEMICAL_FORM_NOT_APPLICABLE = "chemical_form_not_applicable"
    EVENT_UNIT_MISMATCH = "event_unit_mismatch"


@dataclass(frozen=True, slots=True, kw_only=True)
class RoundingPolicy:
    quantum: Decimal
    mode: RoundingMode

    def __post_init__(self) -> None:
        if not self.quantum.is_finite() or self.quantum <= 0:
            raise NormalizationError("rounding quantum must be finite and greater than zero")


@dataclass(frozen=True, slots=True, kw_only=True)
class RoundingTrace:
    quantum: Decimal
    mode: RoundingMode
    unrounded_numerator: int
    unrounded_denominator: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ComputationTrace:
    operation: str
    rule_id: str
    rule_version: str
    rounding: RoundingTrace | None = None
    authority_source_id: str | None = None
    source_version: str | None = None
    source_locator: str | None = None
    plan_id: str | None = None
    plan_version: str | None = None

    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise NormalizationError("operation must not be blank")
        if not self.rule_id.strip():
            raise NormalizationError("rule_id must not be blank")
        if not self.rule_version.strip():
            raise NormalizationError("rule_version must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class ComputedAmount:
    subject_kind: SubjectKind
    subject_id: str
    value: Decimal
    unit: Unit
    amount_basis: AmountBasis
    quantity_basis: QuantityBasis
    source_quantity_basis_ids: tuple[str, ...]
    source_amount_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    traces: tuple[ComputationTrace, ...]
    consumption_unit_id: str | None = None
    chemical_form_id: str | None = None
    equivalence_basis: str | None = None

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise NormalizationError("subject_id must not be blank")
        if not self.value.is_finite() or self.value < 0:
            raise NormalizationError("computed value must be finite and non-negative")
        for basis_id in self.source_quantity_basis_ids:
            if not basis_id.strip():
                raise NormalizationError("source quantity basis IDs must not be blank")
        if not self.source_amount_ids:
            raise NormalizationError("computed amount requires source amount lineage")
        if any(not amount_id.strip() for amount_id in self.source_amount_ids):
            raise NormalizationError("source amount IDs must not be blank")
        if not self.source_ids:
            raise NormalizationError("computed amount requires source provenance")
        if any(not source_id.strip() for source_id in self.source_ids):
            raise NormalizationError("source IDs must not be blank")
        if not self.traces:
            raise NormalizationError("computed amount requires computation trace")
        if self.consumption_unit_id is not None and not self.consumption_unit_id.strip():
            raise NormalizationError("consumption_unit_id must not be blank")
        if (
            self.quantity_basis is not QuantityBasis.PER_CONSUMPTION_UNIT
            and self.consumption_unit_id is not None
        ):
            raise NormalizationError(
                "consumption_unit_id is only valid for per-consumption-unit amounts"
            )

        if self.amount_basis is AmountBasis.EQUIVALENT:
            if self.equivalence_basis is None or not self.equivalence_basis.strip():
                raise NormalizationError(
                    "equivalent computed amount requires explicit equivalence_basis"
                )
        elif self.equivalence_basis is not None:
            raise NormalizationError(
                "equivalence_basis is only valid for equivalent computed amounts"
            )

        if self.amount_basis in (
            AmountBasis.ANALYTE,
            AmountBasis.ELEMENTAL,
            AmountBasis.EQUIVALENT,
        ):
            if self.subject_kind is not SubjectKind.ANALYTE:
                raise NormalizationError(
                    "analyte/elemental/equivalent computed amounts require analyte subject"
                )
        elif self.amount_basis in (
            AmountBasis.INGREDIENT_COMPOUND,
            AmountBasis.MATERIAL,
        ):
            if self.subject_kind is not SubjectKind.INGREDIENT:
                raise NormalizationError(
                    "compound/material computed amounts require ingredient subject"
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class _ResolvedQuantity:
    subject_kind: SubjectKind
    subject_id: str
    value: Decimal
    unit: Unit
    amount_basis: AmountBasis
    quantity_basis: QuantityBasis
    source_quantity_basis_ids: tuple[str, ...]
    source_amount_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    traces: tuple[ComputationTrace, ...]
    consumption_unit_id: str | None
    chemical_form_id: str | None
    equivalence_basis: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizationOutcome:
    status: ResolutionStatus
    amount: ComputedAmount | None = None
    reason: UnresolvedReason | None = None

    def __post_init__(self) -> None:
        if self.status is ResolutionStatus.RESOLVED:
            if self.amount is None or self.reason is not None:
                raise NormalizationError(
                    "resolved outcome requires amount and must not carry unresolved reason"
                )
        elif self.amount is not None or self.reason is None:
            raise NormalizationError(
                "unresolved outcome requires reason and must not carry computed amount"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class ScientificConversionRule:
    rule_id: str
    rule_version: str
    analyte_id: str
    from_unit: Unit
    to_unit: Unit
    factor_numerator: int
    factor_denominator: int
    allowed_chemical_form_ids: tuple[str, ...]
    equivalence_basis: str
    authority_source_id: str
    source_version: str
    source_locator: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("rule_id", self.rule_id),
            ("rule_version", self.rule_version),
            ("analyte_id", self.analyte_id),
            ("equivalence_basis", self.equivalence_basis),
            ("authority_source_id", self.authority_source_id),
            ("source_version", self.source_version),
            ("source_locator", self.source_locator),
        ):
            if not value.strip():
                raise RuleValidationError(f"{field_name} must not be blank")

        if self.factor_numerator <= 0 or self.factor_denominator <= 0:
            raise RuleValidationError(
                "scientific conversion factor numerator and denominator must be positive"
            )
        if self.from_unit is self.to_unit:
            raise RuleValidationError("scientific conversion must change units")
        if unit_dimension(self.from_unit) is unit_dimension(self.to_unit):
            raise RuleValidationError(
                "same-dimension conversion belongs to the generic unit converter"
            )
        if not self.allowed_chemical_form_ids:
            raise RuleValidationError(
                "scientific conversion rule requires explicit chemical-form applicability"
            )
        if any(not form_id.strip() for form_id in self.allowed_chemical_form_ids):
            raise RuleValidationError("chemical-form IDs must not be blank")

    @property
    def factor(self) -> Fraction:
        return Fraction(self.factor_numerator, self.factor_denominator)

    @property
    def reciprocal_factor(self) -> Fraction:
        return Fraction(self.factor_denominator, self.factor_numerator)


VITAMIN_D_ANALYTE_ID = "analyte:vitamin-d"
VITAMIN_D_D2_FORM_ID = "chemical-form:ergocalciferol"
VITAMIN_D_D3_FORM_ID = "chemical-form:cholecalciferol"

VITAMIN_D_D2_D3_RULE = ScientificConversionRule(
    rule_id="efsa-vitamin-d-d2-d3-iu-vde",
    rule_version="2023.8145-v1",
    analyte_id=VITAMIN_D_ANALYTE_ID,
    from_unit=Unit.INTERNATIONAL_UNIT,
    to_unit=Unit.MICROGRAM,
    factor_numerator=1,
    factor_denominator=40,
    allowed_chemical_form_ids=(VITAMIN_D_D2_FORM_ID, VITAMIN_D_D3_FORM_ID),
    equivalence_basis="EFSA 2023 vitamin D equivalent (VDE), D2/D3 only",
    authority_source_id="doi:10.2903/j.efsa.2023.8145",
    source_version="EFSA Journal 2023;21(8):8145",
    source_locator="VDE definition: 1 ug D2/D3 = 40 IU",
)


_MASS_TO_MICROGRAM: dict[Unit, Fraction] = {
    Unit.GRAM: Fraction(1_000_000, 1),
    Unit.MILLIGRAM: Fraction(1_000, 1),
    Unit.MICROGRAM: Fraction(1, 1),
}


def _require_finite_nonnegative(value: Decimal, field_name: str) -> None:
    if not value.is_finite() or value < 0:
        raise NormalizationError(f"{field_name} must be finite and non-negative")


def _terminating_decimal(value: Fraction) -> Decimal | None:
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
        return None

    scale = max(twos, fives)
    scaled_numerator = (
        value.numerator
        * (2 ** (scale - twos))
        * (5 ** (scale - fives))
    )
    sign = 1 if scaled_numerator < 0 else 0
    digits = tuple(int(digit) for digit in str(abs(scaled_numerator)))
    return Decimal((sign, digits, -scale))


def _round_positive_fraction_to_integer(
    value: Fraction,
    mode: RoundingMode,
) -> int:
    if value < 0:
        raise NormalizationError("negative rounding input is unsupported")

    whole, remainder = divmod(value.numerator, value.denominator)
    doubled_remainder = remainder * 2

    if doubled_remainder < value.denominator:
        return whole
    if doubled_remainder > value.denominator:
        return whole + 1

    if mode is RoundingMode.HALF_UP:
        return whole + 1
    if mode is RoundingMode.HALF_EVEN:
        return whole if whole % 2 == 0 else whole + 1

    raise NormalizationError(f"unsupported rounding mode: {mode}")


def _resolve_fraction(
    value: Fraction,
    policy: RoundingPolicy | None,
) -> tuple[Decimal, RoundingTrace | None]:
    exact = _terminating_decimal(value)
    if exact is not None:
        return exact, None

    if policy is None:
        raise RoundingRequiredError(
            "result has no finite exact Decimal representation; explicit rounding is required"
        )

    quantum_fraction = Fraction(policy.quantum)
    rounded_units = _round_positive_fraction_to_integer(
        value / quantum_fraction,
        policy.mode,
    )
    rounded_fraction = quantum_fraction * rounded_units
    rounded_decimal = _terminating_decimal(rounded_fraction)
    if rounded_decimal is None:
        raise NormalizationError("finite Decimal quantum produced non-terminating result")

    return (
        rounded_decimal,
        RoundingTrace(
            quantum=policy.quantum,
            mode=policy.mode,
            unrounded_numerator=value.numerator,
            unrounded_denominator=value.denominator,
        ),
    )


def convert_mass(
    value: Decimal,
    from_unit: Unit,
    to_unit: Unit,
) -> Decimal:
    _require_finite_nonnegative(value, "value")

    if unit_dimension(from_unit) is not UnitDimension.MASS:
        raise DimensionMismatchError(f"{from_unit.value} is not a mass unit")
    if unit_dimension(to_unit) is not UnitDimension.MASS:
        raise DimensionMismatchError(f"{to_unit.value} is not a mass unit")
    if from_unit not in _MASS_TO_MICROGRAM or to_unit not in _MASS_TO_MICROGRAM:
        raise DimensionMismatchError("unsupported mass unit for KIR-113 MVP")

    converted = (
        Fraction(value)
        * _MASS_TO_MICROGRAM[from_unit]
        / _MASS_TO_MICROGRAM[to_unit]
    )
    resolved, rounding = _resolve_fraction(converted, None)
    if rounding is not None:
        raise AssertionError("metric mass conversion must always be exact")
    return resolved


def _unresolved_input_outcome(amount: AmountRecord) -> NormalizationOutcome:
    status = amount.resolution_status
    if status is ResolutionStatus.RESOLVED:
        status = ResolutionStatus.AMBIGUOUS
    return NormalizationOutcome(
        status=status,
        reason=UnresolvedReason.INPUT_UNRESOLVED,
    )


def _append_unique(items: tuple[str, ...], value: str) -> tuple[str, ...]:
    return items if value in items else (*items, value)


def _resolve_input(
    amount: AmountRecord | ComputedAmount,
) -> _ResolvedQuantity | NormalizationOutcome:
    if isinstance(amount, ComputedAmount):
        return _ResolvedQuantity(
            subject_kind=amount.subject_kind,
            subject_id=amount.subject_id,
            value=amount.value,
            unit=amount.unit,
            amount_basis=amount.amount_basis,
            quantity_basis=amount.quantity_basis,
            source_quantity_basis_ids=amount.source_quantity_basis_ids,
            source_amount_ids=amount.source_amount_ids,
            source_ids=amount.source_ids,
            traces=amount.traces,
            consumption_unit_id=amount.consumption_unit_id,
            chemical_form_id=amount.chemical_form_id,
            equivalence_basis=amount.equivalence_basis,
        )

    if not amount.deterministically_usable:
        return _unresolved_input_outcome(amount)
    if amount.value is None or amount.unit is None:
        return _unresolved_input_outcome(amount)
    if amount.amount_basis is None or amount.quantity_basis is None:
        return _unresolved_input_outcome(amount)

    _require_finite_nonnegative(amount.value, "amount.value")
    source_basis_ids = (
        (amount.quantity_basis_id,) if amount.quantity_basis_id is not None else ()
    )
    return _ResolvedQuantity(
        subject_kind=amount.subject_kind,
        subject_id=amount.subject_id,
        value=amount.value,
        unit=amount.unit,
        amount_basis=amount.amount_basis,
        quantity_basis=amount.quantity_basis,
        source_quantity_basis_ids=source_basis_ids,
        source_amount_ids=(amount.amount_id,),
        source_ids=(amount.source_id,),
        traces=(),
        consumption_unit_id=None,
        chemical_form_id=None,
        equivalence_basis=amount.equivalence_basis,
    )


def apply_scientific_conversion(
    amount: AmountRecord | ComputedAmount,
    rule: ScientificConversionRule,
    *,
    chemical_form_id: str | None,
    rounding_policy: RoundingPolicy | None = None,
) -> NormalizationOutcome:
    resolved = _resolve_input(amount)
    if isinstance(resolved, NormalizationOutcome):
        return resolved

    if resolved.subject_kind is not SubjectKind.ANALYTE:
        raise RuleApplicationError("scientific conversion requires an analyte amount")
    if resolved.subject_id != rule.analyte_id:
        raise RuleApplicationError("scientific conversion rule analyte does not match amount")

    if resolved.amount_basis is AmountBasis.EQUIVALENT:
        if resolved.equivalence_basis != rule.equivalence_basis:
            raise RuleApplicationError(
                "equivalent input basis does not match scientific conversion rule"
            )
    elif resolved.amount_basis is not AmountBasis.ANALYTE:
        raise RuleApplicationError(
            "scientific conversion requires analyte or matching equivalent amount basis"
        )

    if (
        resolved.chemical_form_id is not None
        and chemical_form_id is not None
        and resolved.chemical_form_id != chemical_form_id
    ):
        raise RuleApplicationError(
            "chemical form cannot change across normalization stages"
        )
    effective_form_id = chemical_form_id or resolved.chemical_form_id

    if effective_form_id is None:
        return NormalizationOutcome(
            status=ResolutionStatus.UNRESOLVED_IDENTITY,
            reason=UnresolvedReason.CHEMICAL_FORM_REQUIRED,
        )
    if effective_form_id not in rule.allowed_chemical_form_ids:
        return NormalizationOutcome(
            status=ResolutionStatus.UNRESOLVED_IDENTITY,
            reason=UnresolvedReason.CHEMICAL_FORM_NOT_APPLICABLE,
        )

    if resolved.unit is rule.from_unit:
        target_unit = rule.to_unit
        factor = rule.factor
    elif resolved.unit is rule.to_unit:
        target_unit = rule.from_unit
        factor = rule.reciprocal_factor
    else:
        raise RuleApplicationError("amount unit does not match either direction of rule")

    raw_result = Fraction(resolved.value) * factor
    result, rounding = _resolve_fraction(raw_result, rounding_policy)

    return NormalizationOutcome(
        status=ResolutionStatus.RESOLVED,
        amount=ComputedAmount(
            subject_kind=resolved.subject_kind,
            subject_id=resolved.subject_id,
            value=result,
            unit=target_unit,
            amount_basis=AmountBasis.EQUIVALENT,
            quantity_basis=resolved.quantity_basis,
            source_quantity_basis_ids=resolved.source_quantity_basis_ids,
            source_amount_ids=resolved.source_amount_ids,
            source_ids=resolved.source_ids,
            consumption_unit_id=resolved.consumption_unit_id,
            chemical_form_id=effective_form_id,
            equivalence_basis=rule.equivalence_basis,
            traces=resolved.traces
            + (
                ComputationTrace(
                    operation="scientific_conversion",
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    authority_source_id=rule.authority_source_id,
                    source_version=rule.source_version,
                    source_locator=rule.source_locator,
                    rounding=rounding,
                ),
            ),
        ),
    )


def normalize_per_consumption_unit(
    amount: AmountRecord | ComputedAmount,
    serving: ServingDefinition,
    *,
    rounding_policy: RoundingPolicy | None = None,
) -> NormalizationOutcome:
    resolved = _resolve_input(amount)
    if isinstance(resolved, NormalizationOutcome):
        return resolved

    if resolved.quantity_basis is not serving.basis_type:
        raise BasisMismatchError("amount quantity basis does not match serving basis type")
    if serving.basis_id not in resolved.source_quantity_basis_ids:
        raise BasisMismatchError(
            "source quantity basis lineage does not include serving basis ID"
        )
    if serving.basis_quantity is None or serving.basis_unit is None:
        raise BasisMismatchError("serving quantity and unit must be explicit")
    if serving.basis_unit is not Unit.COUNT:
        raise BasisMismatchError("per-consumption-unit normalization requires count basis")
    if serving.consumption_unit_id is None:
        raise BasisMismatchError("consumption unit identity is required")

    raw_result = Fraction(resolved.value) / Fraction(serving.basis_quantity)
    result, rounding = _resolve_fraction(raw_result, rounding_policy)

    return NormalizationOutcome(
        status=ResolutionStatus.RESOLVED,
        amount=ComputedAmount(
            subject_kind=resolved.subject_kind,
            subject_id=resolved.subject_id,
            value=result,
            unit=resolved.unit,
            amount_basis=resolved.amount_basis,
            quantity_basis=QuantityBasis.PER_CONSUMPTION_UNIT,
            source_quantity_basis_ids=_append_unique(
                resolved.source_quantity_basis_ids,
                serving.basis_id,
            ),
            source_amount_ids=resolved.source_amount_ids,
            source_ids=_append_unique(resolved.source_ids, serving.source_id),
            consumption_unit_id=serving.consumption_unit_id,
            chemical_form_id=resolved.chemical_form_id,
            equivalence_basis=resolved.equivalence_basis,
            traces=resolved.traces
            + (
                ComputationTrace(
                    operation="serving_normalization",
                    rule_id="kir-113-serving-normalization",
                    rule_version="1",
                    rounding=rounding,
                ),
            ),
        ),
    )


def normalize_planned_daily_amount(
    per_unit_amount: ComputedAmount,
    plan: IntakePlan,
    *,
    rounding_policy: RoundingPolicy | None = None,
) -> NormalizationOutcome:
    if per_unit_amount.quantity_basis is not QuantityBasis.PER_CONSUMPTION_UNIT:
        raise BasisMismatchError("daily normalization requires per-consumption-unit amount")
    if per_unit_amount.consumption_unit_id is None:
        raise BasisMismatchError(
            "per-consumption-unit amount requires explicit consumption unit identity"
        )

    for event in plan.events:
        if event.consumption_unit_id != per_unit_amount.consumption_unit_id:
            return NormalizationOutcome(
                status=ResolutionStatus.AMBIGUOUS,
                reason=UnresolvedReason.EVENT_UNIT_MISMATCH,
            )

    total_units = sum(
        (Fraction(event.consumption_units) for event in plan.events),
        start=Fraction(0, 1),
    )
    raw_result = Fraction(per_unit_amount.value) * total_units
    result, rounding = _resolve_fraction(raw_result, rounding_policy)

    return NormalizationOutcome(
        status=ResolutionStatus.RESOLVED,
        amount=ComputedAmount(
            subject_kind=per_unit_amount.subject_kind,
            subject_id=per_unit_amount.subject_id,
            value=result,
            unit=per_unit_amount.unit,
            amount_basis=per_unit_amount.amount_basis,
            quantity_basis=QuantityBasis.PER_DAY,
            source_quantity_basis_ids=per_unit_amount.source_quantity_basis_ids,
            source_amount_ids=per_unit_amount.source_amount_ids,
            source_ids=per_unit_amount.source_ids,
            chemical_form_id=per_unit_amount.chemical_form_id,
            equivalence_basis=per_unit_amount.equivalence_basis,
            traces=per_unit_amount.traces
            + (
                ComputationTrace(
                    operation="planned_daily_normalization",
                    rule_id="kir-113-planned-daily-normalization",
                    rule_version="1",
                    plan_id=plan.plan_id,
                    plan_version=plan.version,
                    rounding=rounding,
                ),
            ),
        ),
    )