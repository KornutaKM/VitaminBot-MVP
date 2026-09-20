from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from vitaminbot.domain import (
    AmountBasis,
    QuantityBasis,
    ResolutionStatus,
    SubjectKind,
    Unit,
    UnitDimension,
    unit_dimension,
)
from vitaminbot.nutrition.normalization import (
    ComputationTrace,
    ComputedAmount,
    NormalizationOutcome,
    UnresolvedReason,
    convert_mass,
)


class AggregationError(ValueError):
    """Raised when a KIR-114 input violates the aggregation contract."""


class DuplicateFlagKind(StrEnum):
    EXACT_REPEAT_SUPPRESSED = "exact_repeat_suppressed"
    CONFLICTING_REPEAT = "conflicting_repeat"
    SHARED_SOURCE_LINEAGE = "shared_source_lineage"


class AggregationIssue(StrEnum):
    UNRESOLVED_CONTRIBUTOR = "unresolved_contributor"
    CONFLICTING_LOGICAL_CONTRIBUTION = "conflicting_logical_contribution"
    INCOMPATIBLE_NON_MASS_UNITS = "incompatible_non_mass_units"


@dataclass(frozen=True, slots=True, kw_only=True)
class AggregateKey:
    subject_kind: SubjectKind
    subject_id: str
    amount_basis: AmountBasis
    equivalence_basis: str | None
    dimension: UnitDimension

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise AggregationError("subject_id must not be blank")
        if self.amount_basis is AmountBasis.EQUIVALENT:
            if self.equivalence_basis is None or not self.equivalence_basis.strip():
                raise AggregationError(
                    "equivalent aggregate key requires explicit equivalence_basis"
                )
        elif self.equivalence_basis is not None:
            raise AggregationError("equivalence_basis is only valid for equivalent aggregate keys")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfirmedPlannedContribution:
    contribution_id: str
    confirmation_ref: str
    product_id: str
    formulation_id: str
    tracked_instance_id: str
    plan_id: str
    plan_version: str
    expected_subject_kind: SubjectKind
    expected_subject_id: str
    expected_amount_basis: AmountBasis
    expected_equivalence_basis: str | None
    outcome: NormalizationOutcome
    expected_unit: Unit | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("contribution_id", self.contribution_id),
            ("confirmation_ref", self.confirmation_ref),
            ("product_id", self.product_id),
            ("formulation_id", self.formulation_id),
            ("tracked_instance_id", self.tracked_instance_id),
            ("plan_id", self.plan_id),
            ("plan_version", self.plan_version),
            ("expected_subject_id", self.expected_subject_id),
        ):
            if not value.strip():
                raise AggregationError(f"{field_name} must not be blank")

        if self.expected_amount_basis is AmountBasis.EQUIVALENT:
            if (
                self.expected_equivalence_basis is None
                or not self.expected_equivalence_basis.strip()
            ):
                raise AggregationError(
                    "equivalent expected amount requires explicit equivalence basis"
                )
        elif self.expected_equivalence_basis is not None:
            raise AggregationError(
                "expected_equivalence_basis is only valid for equivalent amounts"
            )

        if self.outcome.status is ResolutionStatus.RESOLVED:
            amount = self.outcome.amount
            if amount is None:
                raise AggregationError("resolved outcome must contain an amount")
            self._validate_resolved_amount(amount)

    def _validate_resolved_amount(self, amount: ComputedAmount) -> None:
        if amount.quantity_basis is not QuantityBasis.PER_DAY:
            raise AggregationError("KIR-114 accepts resolved numeric inputs only on PER_DAY basis")
        if amount.subject_kind is not self.expected_subject_kind:
            raise AggregationError("resolved subject_kind does not match expected metadata")
        if amount.subject_id != self.expected_subject_id:
            raise AggregationError("resolved subject_id does not match expected metadata")
        if amount.amount_basis is not self.expected_amount_basis:
            raise AggregationError("resolved amount_basis does not match expected metadata")
        if amount.equivalence_basis != self.expected_equivalence_basis:
            raise AggregationError("resolved equivalence_basis does not match expected metadata")
        if self.expected_unit is not None and amount.unit is not self.expected_unit:
            raise AggregationError("resolved unit does not match expected metadata")

        daily_trace = _last_planned_daily_trace(amount)
        if daily_trace is None:
            raise AggregationError(
                "resolved daily contribution requires planned-daily computation trace"
            )
        if daily_trace.plan_id != self.plan_id:
            raise AggregationError("planned-daily trace plan_id does not match contribution")
        if daily_trace.plan_version != self.plan_version:
            raise AggregationError("planned-daily trace plan_version does not match contribution")


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedContribution:
    contribution_id: str
    confirmation_ref: str
    product_id: str
    formulation_id: str
    tracked_instance_id: str
    plan_id: str
    plan_version: str
    normalized_value: Decimal
    normalized_unit: Unit
    original_amount: ComputedAmount


@dataclass(frozen=True, slots=True, kw_only=True)
class UnresolvedContribution:
    contribution_id: str
    confirmation_ref: str
    product_id: str
    formulation_id: str
    tracked_instance_id: str
    plan_id: str
    plan_version: str
    expected_subject_kind: SubjectKind
    expected_subject_id: str
    expected_amount_basis: AmountBasis
    expected_equivalence_basis: str | None
    expected_unit: Unit | None
    normalization_status: ResolutionStatus
    source_reason: UnresolvedReason | None
    aggregation_reason: AggregationIssue | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DuplicateFlag:
    kind: DuplicateFlagKind
    contribution_ids: tuple[str, ...]
    counted_contribution_id: str | None = None
    shared_source_amount_ids: tuple[str, ...] = ()
    shared_source_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class DailyAggregate:
    key: AggregateKey
    known_total: Decimal | None
    unit: Unit | None
    is_complete: bool
    issues: tuple[AggregationIssue, ...]
    contributors: tuple[ResolvedContribution, ...]
    suppressed_exact_repeat_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class DailyAggregationResult:
    aggregates: tuple[DailyAggregate, ...]
    unresolved_contributors: tuple[UnresolvedContribution, ...]
    duplicate_flags: tuple[DuplicateFlag, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class _LogicalContributionKey:
    tracked_instance_id: str
    formulation_id: str
    plan_id: str
    plan_version: str
    aggregate_key: AggregateKey
    source_amount_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    source_quantity_basis_ids: tuple[str, ...]
    planned_daily_trace_identity: tuple[str, str, str, str]


@dataclass(frozen=True, slots=True, kw_only=True)
class _PreparedContribution:
    source: ConfirmedPlannedContribution
    resolved: ResolvedContribution
    aggregate_key: AggregateKey
    logical_key: _LogicalContributionKey


def _last_planned_daily_trace(
    amount: ComputedAmount,
) -> ComputationTrace | None:
    for trace in reversed(amount.traces):
        if trace.operation == "planned_daily_normalization":
            return trace
    return None


def _canonical_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


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
        raise AggregationError(
            "sum of finite Decimal inputs unexpectedly produced non-terminating Decimal"
        )

    scale = max(twos, fives)

    scaled_numerator = value.numerator * (2 ** (scale - twos)) * (5 ** (scale - fives))

    sign = 1 if scaled_numerator < 0 else 0
    digits = tuple(int(digit) for digit in str(abs(scaled_numerator)))

    return Decimal((sign, digits, -scale))


def _aggregate_key(amount: ComputedAmount) -> AggregateKey:
    return AggregateKey(
        subject_kind=amount.subject_kind,
        subject_id=amount.subject_id,
        amount_basis=amount.amount_basis,
        equivalence_basis=amount.equivalence_basis,
        dimension=unit_dimension(amount.unit),
    )


def _normalized_value_and_unit(
    amount: ComputedAmount,
) -> tuple[Decimal, Unit]:
    if unit_dimension(amount.unit) is UnitDimension.MASS:
        return (
            convert_mass(
                amount.value,
                amount.unit,
                Unit.MICROGRAM,
            ),
            Unit.MICROGRAM,
        )

    return amount.value, amount.unit


def _prepare_resolved(
    contribution: ConfirmedPlannedContribution,
) -> _PreparedContribution:
    amount = contribution.outcome.amount

    if amount is None:
        raise AggregationError("resolved contribution unexpectedly has no amount")

    normalized_value, normalized_unit = _normalized_value_and_unit(amount)

    resolved = ResolvedContribution(
        contribution_id=contribution.contribution_id,
        confirmation_ref=contribution.confirmation_ref,
        product_id=contribution.product_id,
        formulation_id=contribution.formulation_id,
        tracked_instance_id=contribution.tracked_instance_id,
        plan_id=contribution.plan_id,
        plan_version=contribution.plan_version,
        normalized_value=normalized_value,
        normalized_unit=normalized_unit,
        original_amount=amount,
    )

    key = _aggregate_key(amount)

    daily_trace = _last_planned_daily_trace(amount)

    if daily_trace is None:
        raise AggregationError("daily trace disappeared after contribution validation")

    logical_key = _LogicalContributionKey(
        tracked_instance_id=contribution.tracked_instance_id,
        formulation_id=contribution.formulation_id,
        plan_id=contribution.plan_id,
        plan_version=contribution.plan_version,
        aggregate_key=key,
        source_amount_ids=_canonical_ids(amount.source_amount_ids),
        source_ids=_canonical_ids(amount.source_ids),
        source_quantity_basis_ids=_canonical_ids(amount.source_quantity_basis_ids),
        planned_daily_trace_identity=(
            daily_trace.rule_id,
            daily_trace.rule_version,
            contribution.plan_id,
            contribution.plan_version,
        ),
    )

    return _PreparedContribution(
        source=contribution,
        resolved=resolved,
        aggregate_key=key,
        logical_key=logical_key,
    )


def _unresolved_from_input(
    contribution: ConfirmedPlannedContribution,
) -> UnresolvedContribution:
    return UnresolvedContribution(
        contribution_id=contribution.contribution_id,
        confirmation_ref=contribution.confirmation_ref,
        product_id=contribution.product_id,
        formulation_id=contribution.formulation_id,
        tracked_instance_id=contribution.tracked_instance_id,
        plan_id=contribution.plan_id,
        plan_version=contribution.plan_version,
        expected_subject_kind=contribution.expected_subject_kind,
        expected_subject_id=contribution.expected_subject_id,
        expected_amount_basis=contribution.expected_amount_basis,
        expected_equivalence_basis=(contribution.expected_equivalence_basis),
        expected_unit=contribution.expected_unit,
        normalization_status=contribution.outcome.status,
        source_reason=contribution.outcome.reason,
    )


def _unresolved_from_conflict(
    prepared: _PreparedContribution,
) -> UnresolvedContribution:
    source = prepared.source

    return UnresolvedContribution(
        contribution_id=source.contribution_id,
        confirmation_ref=source.confirmation_ref,
        product_id=source.product_id,
        formulation_id=source.formulation_id,
        tracked_instance_id=source.tracked_instance_id,
        plan_id=source.plan_id,
        plan_version=source.plan_version,
        expected_subject_kind=source.expected_subject_kind,
        expected_subject_id=source.expected_subject_id,
        expected_amount_basis=source.expected_amount_basis,
        expected_equivalence_basis=source.expected_equivalence_basis,
        expected_unit=source.expected_unit,
        normalization_status=ResolutionStatus.RESOLVED,
        source_reason=None,
        aggregation_reason=(AggregationIssue.CONFLICTING_LOGICAL_CONTRIBUTION),
    )


def _prepared_fingerprint(
    prepared: _PreparedContribution,
) -> tuple[object, ...]:
    amount = prepared.resolved.original_amount

    return (
        prepared.resolved.normalized_value,
        prepared.resolved.normalized_unit,
        amount.chemical_form_id,
        _canonical_ids(amount.source_amount_ids),
        _canonical_ids(amount.source_ids),
        _canonical_ids(amount.source_quantity_basis_ids),
        amount.traces,
    )


def _key_sort(
    key: AggregateKey,
) -> tuple[str, str, str, str, str]:
    return (
        key.subject_kind.value,
        key.subject_id,
        key.amount_basis.value,
        key.equivalence_basis or "",
        key.dimension.value,
    )


def _resolved_sort(
    contribution: ResolvedContribution,
) -> tuple[str, ...]:
    return (
        contribution.product_id,
        contribution.formulation_id,
        contribution.tracked_instance_id,
        contribution.plan_id,
        contribution.plan_version,
        contribution.contribution_id,
    )


def _logical_sort(
    key: _LogicalContributionKey,
) -> tuple[object, ...]:
    return (
        key.tracked_instance_id,
        key.formulation_id,
        key.plan_id,
        key.plan_version,
        _key_sort(key.aggregate_key),
        key.source_amount_ids,
        key.source_ids,
        key.source_quantity_basis_ids,
        key.planned_daily_trace_identity,
    )


def _unresolved_sort(
    contribution: UnresolvedContribution,
) -> tuple[str, ...]:
    return (
        contribution.expected_subject_kind.value,
        contribution.expected_subject_id,
        contribution.expected_amount_basis.value,
        contribution.expected_equivalence_basis or "",
        contribution.product_id,
        contribution.formulation_id,
        contribution.tracked_instance_id,
        contribution.plan_id,
        contribution.plan_version,
        contribution.contribution_id,
    )


def _flag_sort(
    flag: DuplicateFlag,
) -> tuple[object, ...]:
    return (
        flag.kind.value,
        flag.contribution_ids,
        flag.counted_contribution_id or "",
        flag.shared_source_amount_ids,
        flag.shared_source_ids,
    )


def _matches_unresolved_key(
    unresolved: UnresolvedContribution,
    key: AggregateKey,
) -> bool:
    if unresolved.expected_subject_kind is not key.subject_kind:
        return False

    if unresolved.expected_subject_id != key.subject_id:
        return False

    if unresolved.expected_amount_basis is not key.amount_basis:
        return False

    if unresolved.expected_equivalence_basis != key.equivalence_basis:
        return False

    if unresolved.expected_unit is None:
        return True

    return unit_dimension(unresolved.expected_unit) is key.dimension


def _shared_lineage_flags(
    prepared: tuple[_PreparedContribution, ...],
) -> list[DuplicateFlag]:
    flags: list[DuplicateFlag] = []

    by_source_amount: dict[
        str,
        list[_PreparedContribution],
    ] = defaultdict(list)

    by_source: dict[
        str,
        list[_PreparedContribution],
    ] = defaultdict(list)

    for item in prepared:
        for amount_id in set(item.resolved.original_amount.source_amount_ids):
            by_source_amount[amount_id].append(item)

        for source_id in set(item.resolved.original_amount.source_ids):
            by_source[source_id].append(item)

    for amount_id, items in sorted(by_source_amount.items()):
        if len({item.logical_key for item in items}) > 1:
            flags.append(
                DuplicateFlag(
                    kind=(DuplicateFlagKind.SHARED_SOURCE_LINEAGE),
                    contribution_ids=tuple(sorted(item.source.contribution_id for item in items)),
                    shared_source_amount_ids=(amount_id,),
                )
            )

    for source_id, items in sorted(by_source.items()):
        if len({item.logical_key for item in items}) > 1:
            flags.append(
                DuplicateFlag(
                    kind=(DuplicateFlagKind.SHARED_SOURCE_LINEAGE),
                    contribution_ids=tuple(sorted(item.source.contribution_id for item in items)),
                    shared_source_ids=(source_id,),
                )
            )

    return flags


def aggregate_daily_contributions(
    contributions: Iterable[ConfirmedPlannedContribution],
) -> DailyAggregationResult:
    prepared: list[_PreparedContribution] = []

    unresolved: list[UnresolvedContribution] = []

    for contribution in contributions:
        if contribution.outcome.status is ResolutionStatus.RESOLVED:
            prepared.append(_prepare_resolved(contribution))
        else:
            unresolved.append(_unresolved_from_input(contribution))

    observed_keys = {item.aggregate_key for item in prepared}

    by_logical_key: dict[
        _LogicalContributionKey,
        list[_PreparedContribution],
    ] = defaultdict(list)

    for item in prepared:
        by_logical_key[item.logical_key].append(item)

    counted: list[_PreparedContribution] = []

    duplicate_flags: list[DuplicateFlag] = []

    suppressed_by_key: dict[
        AggregateKey,
        list[str],
    ] = defaultdict(list)

    conflict_keys: set[AggregateKey] = set()

    for logical_key in sorted(
        by_logical_key,
        key=_logical_sort,
    ):
        items = sorted(
            by_logical_key[logical_key],
            key=lambda item: _resolved_sort(item.resolved),
        )

        if len(items) == 1:
            counted.append(items[0])
            continue

        first_fingerprint = _prepared_fingerprint(items[0])

        if all(_prepared_fingerprint(item) == first_fingerprint for item in items[1:]):
            counted.append(items[0])

            suppressed_ids = tuple(item.source.contribution_id for item in items[1:])

            suppressed_by_key[logical_key.aggregate_key].extend(suppressed_ids)

            duplicate_flags.append(
                DuplicateFlag(
                    kind=(DuplicateFlagKind.EXACT_REPEAT_SUPPRESSED),
                    contribution_ids=tuple(item.source.contribution_id for item in items),
                    counted_contribution_id=(items[0].source.contribution_id),
                )
            )

            continue

        conflict_keys.add(logical_key.aggregate_key)

        unresolved.extend(_unresolved_from_conflict(item) for item in items)

        duplicate_flags.append(
            DuplicateFlag(
                kind=(DuplicateFlagKind.CONFLICTING_REPEAT),
                contribution_ids=tuple(item.source.contribution_id for item in items),
            )
        )

    duplicate_flags.extend(_shared_lineage_flags(tuple(counted)))

    by_aggregate_key: dict[
        AggregateKey,
        list[_PreparedContribution],
    ] = defaultdict(list)

    for item in counted:
        by_aggregate_key[item.aggregate_key].append(item)

    aggregates: list[DailyAggregate] = []

    for key in sorted(
        observed_keys,
        key=_key_sort,
    ):
        items = sorted(
            by_aggregate_key.get(
                key,
                [],
            ),
            key=lambda item: _resolved_sort(item.resolved),
        )

        issues: set[AggregationIssue] = set()

        if key in conflict_keys:
            issues.add(AggregationIssue.CONFLICTING_LOGICAL_CONTRIBUTION)

        if any(
            _matches_unresolved_key(
                item,
                key,
            )
            for item in unresolved
        ):
            issues.add(AggregationIssue.UNRESOLVED_CONTRIBUTOR)

        units = {item.resolved.normalized_unit for item in items}

        known_total: Decimal | None
        output_unit: Unit | None

        if key in conflict_keys:
            known_total = None
            output_unit = Unit.MICROGRAM if key.dimension is UnitDimension.MASS else None

        elif key.dimension is not UnitDimension.MASS and len(units) > 1:
            issues.add(AggregationIssue.INCOMPATIBLE_NON_MASS_UNITS)

            known_total = None
            output_unit = None

            for item in items:
                unresolved.append(
                    UnresolvedContribution(
                        contribution_id=(item.source.contribution_id),
                        confirmation_ref=(item.source.confirmation_ref),
                        product_id=(item.source.product_id),
                        formulation_id=(item.source.formulation_id),
                        tracked_instance_id=(item.source.tracked_instance_id),
                        plan_id=(item.source.plan_id),
                        plan_version=(item.source.plan_version),
                        expected_subject_kind=(item.source.expected_subject_kind),
                        expected_subject_id=(item.source.expected_subject_id),
                        expected_amount_basis=(item.source.expected_amount_basis),
                        expected_equivalence_basis=(item.source.expected_equivalence_basis),
                        expected_unit=(item.source.expected_unit),
                        normalization_status=(ResolutionStatus.RESOLVED),
                        source_reason=None,
                        aggregation_reason=(AggregationIssue.INCOMPATIBLE_NON_MASS_UNITS),
                    )
                )

        elif not items:
            known_total = None
            output_unit = Unit.MICROGRAM if key.dimension is UnitDimension.MASS else None

        else:
            exact_sum = sum(
                (Fraction(item.resolved.normalized_value) for item in items),
                start=Fraction(
                    0,
                    1,
                ),
            )

            known_total = _exact_decimal_from_fraction(exact_sum)

            output_unit = next(iter(units))

        aggregates.append(
            DailyAggregate(
                key=key,
                known_total=known_total,
                unit=output_unit,
                is_complete=not issues,
                issues=tuple(
                    sorted(
                        issues,
                        key=lambda issue: issue.value,
                    )
                ),
                contributors=tuple(item.resolved for item in items),
                suppressed_exact_repeat_ids=tuple(
                    sorted(
                        suppressed_by_key.get(
                            key,
                            [],
                        )
                    )
                ),
            )
        )

    return DailyAggregationResult(
        aggregates=tuple(aggregates),
        unresolved_contributors=tuple(
            sorted(
                unresolved,
                key=_unresolved_sort,
            )
        ),
        duplicate_flags=tuple(
            sorted(
                duplicate_flags,
                key=_flag_sort,
            )
        ),
    )
