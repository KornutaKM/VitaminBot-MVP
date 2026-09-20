from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from vitaminbot.domain import (
    AmountBasis,
    QuantityBasis,
    ResolutionStatus,
    SubjectKind,
    Unit,
)
from vitaminbot.nutrition import (
    AggregationError,
    AggregationIssue,
    ComputationTrace,
    ComputedAmount,
    ConfirmedPlannedContribution,
    DuplicateFlagKind,
    NormalizationOutcome,
    UnresolvedReason,
    aggregate_daily_contributions,
)


def _daily_amount(
    *,
    subject_kind: SubjectKind = SubjectKind.ANALYTE,
    subject_id: str = "analyte:magnesium",
    amount_basis: AmountBasis = AmountBasis.ELEMENTAL,
    equivalence_basis: str | None = None,
    value: str = "100",
    unit: Unit = Unit.MILLIGRAM,
    source_amount_ids: tuple[str, ...] = ("amount:mg",),
    source_ids: tuple[str, ...] = ("source:label",),
    source_basis_ids: tuple[str, ...] = ("basis:serving",),
    plan_id: str = "plan:1",
    plan_version: str = "1",
) -> ComputedAmount:
    return ComputedAmount(
        subject_kind=subject_kind,
        subject_id=subject_id,
        value=Decimal(value),
        unit=unit,
        amount_basis=amount_basis,
        quantity_basis=QuantityBasis.PER_DAY,
        source_quantity_basis_ids=source_basis_ids,
        source_amount_ids=source_amount_ids,
        source_ids=source_ids,
        traces=(
            ComputationTrace(
                operation="planned_daily_normalization",
                rule_id="kir-113-planned-daily-normalization",
                rule_version="1",
                plan_id=plan_id,
                plan_version=plan_version,
            ),
        ),
        equivalence_basis=equivalence_basis,
    )


def _resolved_contribution(
    *,
    contribution_id: str,
    tracked_instance_id: str,
    product_id: str = "product:1",
    formulation_id: str = "formulation:1",
    plan_id: str = "plan:1",
    plan_version: str = "1",
    subject_kind: SubjectKind = SubjectKind.ANALYTE,
    subject_id: str = "analyte:magnesium",
    amount_basis: AmountBasis = AmountBasis.ELEMENTAL,
    equivalence_basis: str | None = None,
    value: str = "100",
    unit: Unit = Unit.MILLIGRAM,
    source_amount_ids: tuple[str, ...] = ("amount:mg",),
    source_ids: tuple[str, ...] = ("source:label",),
    source_basis_ids: tuple[str, ...] = ("basis:serving",),
) -> ConfirmedPlannedContribution:
    amount = _daily_amount(
        subject_kind=subject_kind,
        subject_id=subject_id,
        amount_basis=amount_basis,
        equivalence_basis=equivalence_basis,
        value=value,
        unit=unit,
        source_amount_ids=source_amount_ids,
        source_ids=source_ids,
        source_basis_ids=source_basis_ids,
        plan_id=plan_id,
        plan_version=plan_version,
    )

    return ConfirmedPlannedContribution(
        contribution_id=contribution_id,
        confirmation_ref=f"confirmation:{contribution_id}",
        product_id=product_id,
        formulation_id=formulation_id,
        tracked_instance_id=tracked_instance_id,
        plan_id=plan_id,
        plan_version=plan_version,
        expected_subject_kind=subject_kind,
        expected_subject_id=subject_id,
        expected_amount_basis=amount_basis,
        expected_equivalence_basis=equivalence_basis,
        expected_unit=unit,
        outcome=NormalizationOutcome(
            status=ResolutionStatus.RESOLVED,
            amount=amount,
        ),
    )


def _unresolved_contribution(
    *,
    contribution_id: str,
    tracked_instance_id: str,
) -> ConfirmedPlannedContribution:
    return ConfirmedPlannedContribution(
        contribution_id=contribution_id,
        confirmation_ref=f"confirmation:{contribution_id}",
        product_id=f"product:{tracked_instance_id}",
        formulation_id=f"formulation:{tracked_instance_id}",
        tracked_instance_id=tracked_instance_id,
        plan_id=f"plan:{tracked_instance_id}",
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


def test_single_product_mass_total_is_canonical_micrograms() -> None:
    result = aggregate_daily_contributions(
        [
            _resolved_contribution(
                contribution_id="c1",
                tracked_instance_id="instance:1",
            )
        ]
    )

    assert result.aggregates[0].known_total == Decimal("100000")
    assert result.aggregates[0].unit is Unit.MICROGRAM
    assert result.aggregates[0].is_complete is True


def test_multiple_products_mixed_mass_units_sum_exactly() -> None:
    result = aggregate_daily_contributions(
        [
            _resolved_contribution(
                contribution_id="c1",
                tracked_instance_id="instance:1",
                value="100",
                unit=Unit.MILLIGRAM,
                source_amount_ids=("amount:one",),
            ),
            _resolved_contribution(
                contribution_id="c2",
                tracked_instance_id="instance:2",
                product_id="product:2",
                formulation_id="formulation:2",
                plan_id="plan:2",
                value="0.2",
                unit=Unit.GRAM,
                source_amount_ids=("amount:two",),
            ),
        ]
    )

    assert result.aggregates[0].known_total == Decimal("300000")
    assert len(result.aggregates[0].contributors) == 2


def test_input_order_does_not_change_result() -> None:
    first = _resolved_contribution(
        contribution_id="a",
        tracked_instance_id="instance:a",
        source_amount_ids=("amount:a",),
    )

    second = _resolved_contribution(
        contribution_id="b",
        tracked_instance_id="instance:b",
        product_id="product:b",
        formulation_id="formulation:b",
        plan_id="plan:b",
        source_amount_ids=("amount:b",),
    )

    assert aggregate_daily_contributions([first, second]) == aggregate_daily_contributions(
        [second, first]
    )


def test_ambient_decimal_context_does_not_change_total() -> None:
    contributions = [
        _resolved_contribution(
            contribution_id="a",
            tracked_instance_id="instance:a",
            value="123456789.123456789",
            source_amount_ids=("amount:a",),
        ),
        _resolved_contribution(
            contribution_id="b",
            tracked_instance_id="instance:b",
            product_id="product:b",
            formulation_id="formulation:b",
            plan_id="plan:b",
            value="0.000000001",
            source_amount_ids=("amount:b",),
        ),
    ]

    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        low_precision = aggregate_daily_contributions(contributions)

    with localcontext() as context:
        context.prec = 50
        high_precision = aggregate_daily_contributions(contributions)

    assert low_precision == high_precision


def test_exact_repeat_counts_once_and_is_flagged() -> None:
    first = _resolved_contribution(
        contribution_id="repeat:a",
        tracked_instance_id="instance:1",
    )

    second = _resolved_contribution(
        contribution_id="repeat:b",
        tracked_instance_id="instance:1",
    )

    result = aggregate_daily_contributions([first, second])

    assert result.aggregates[0].known_total == Decimal("100000")
    assert len(result.aggregates[0].contributors) == 1
    assert result.aggregates[0].suppressed_exact_repeat_ids == ("repeat:b",)

    assert result.duplicate_flags[0].kind is DuplicateFlagKind.EXACT_REPEAT_SUPPRESSED


def test_shared_source_lineage_distinct_instances_counts_both() -> None:
    first = _resolved_contribution(
        contribution_id="c1",
        tracked_instance_id="instance:1",
    )

    second = _resolved_contribution(
        contribution_id="c2",
        tracked_instance_id="instance:2",
        product_id="product:2",
        formulation_id="formulation:2",
        plan_id="plan:2",
    )

    result = aggregate_daily_contributions([first, second])

    assert result.aggregates[0].known_total == Decimal("200000")

    assert any(
        flag.kind is DuplicateFlagKind.SHARED_SOURCE_LINEAGE for flag in result.duplicate_flags
    )


def test_conflicting_same_logical_contribution_withholds_total() -> None:
    first = _resolved_contribution(
        contribution_id="conflict:a",
        tracked_instance_id="instance:1",
        value="100",
    )

    second = _resolved_contribution(
        contribution_id="conflict:b",
        tracked_instance_id="instance:1",
        value="101",
    )

    result = aggregate_daily_contributions([first, second])
    aggregate = result.aggregates[0]

    assert aggregate.known_total is None
    assert aggregate.is_complete is False

    assert AggregationIssue.CONFLICTING_LOGICAL_CONTRIBUTION in aggregate.issues

    assert any(flag.kind is DuplicateFlagKind.CONFLICTING_REPEAT for flag in result.duplicate_flags)


def test_unresolved_input_is_not_zero_and_marks_subtotal_incomplete() -> None:
    known = _resolved_contribution(
        contribution_id="known",
        tracked_instance_id="instance:known",
    )

    unknown = _unresolved_contribution(
        contribution_id="unknown",
        tracked_instance_id="instance:unknown",
    )

    result = aggregate_daily_contributions([known, unknown])
    aggregate = result.aggregates[0]

    assert aggregate.known_total == Decimal("100000")
    assert aggregate.is_complete is False

    assert AggregationIssue.UNRESOLVED_CONTRIBUTOR in aggregate.issues

    assert len(result.unresolved_contributors) == 1


def test_elemental_and_compound_magnesium_never_combine() -> None:
    elemental = _resolved_contribution(
        contribution_id="elemental",
        tracked_instance_id="instance:elemental",
    )

    compound = _resolved_contribution(
        contribution_id="compound",
        tracked_instance_id="instance:compound",
        product_id="product:compound",
        formulation_id="formulation:compound",
        plan_id="plan:compound",
        subject_kind=SubjectKind.INGREDIENT,
        subject_id="ingredient:magnesium-citrate",
        amount_basis=AmountBasis.INGREDIENT_COMPOUND,
        source_amount_ids=("amount:compound",),
    )

    result = aggregate_daily_contributions([elemental, compound])

    assert len(result.aggregates) == 2


def test_fish_oil_epa_and_dha_are_separate_groups() -> None:
    fish_oil = _resolved_contribution(
        contribution_id="fish-oil",
        tracked_instance_id="instance:fish-oil",
        subject_kind=SubjectKind.INGREDIENT,
        subject_id="ingredient:fish-oil",
        amount_basis=AmountBasis.MATERIAL,
        source_amount_ids=("amount:fish-oil",),
    )

    epa = _resolved_contribution(
        contribution_id="epa",
        tracked_instance_id="instance:epa",
        product_id="product:epa",
        formulation_id="formulation:epa",
        plan_id="plan:epa",
        subject_id="analyte:epa",
        amount_basis=AmountBasis.ANALYTE,
        source_amount_ids=("amount:epa",),
    )

    dha = _resolved_contribution(
        contribution_id="dha",
        tracked_instance_id="instance:dha",
        product_id="product:dha",
        formulation_id="formulation:dha",
        plan_id="plan:dha",
        subject_id="analyte:dha",
        amount_basis=AmountBasis.ANALYTE,
        source_amount_ids=("amount:dha",),
    )

    result = aggregate_daily_contributions([fish_oil, epa, dha])

    assert len(result.aggregates) == 3


def test_different_equivalence_bases_stay_separate() -> None:
    first = _resolved_contribution(
        contribution_id="eq:a",
        tracked_instance_id="instance:a",
        subject_id="analyte:test",
        amount_basis=AmountBasis.EQUIVALENT,
        equivalence_basis="basis:a",
    )

    second = _resolved_contribution(
        contribution_id="eq:b",
        tracked_instance_id="instance:b",
        product_id="product:b",
        formulation_id="formulation:b",
        plan_id="plan:b",
        subject_id="analyte:test",
        amount_basis=AmountBasis.EQUIVALENT,
        equivalence_basis="basis:b",
        source_amount_ids=("amount:b",),
    )

    result = aggregate_daily_contributions([first, second])

    assert len(result.aggregates) == 2


def test_incompatible_non_mass_units_withhold_total() -> None:
    liters = _resolved_contribution(
        contribution_id="liters",
        tracked_instance_id="instance:l",
        subject_kind=SubjectKind.INGREDIENT,
        subject_id="ingredient:test-liquid",
        amount_basis=AmountBasis.MATERIAL,
        value="1",
        unit=Unit.LITER,
        source_amount_ids=("amount:l",),
    )

    milliliters = _resolved_contribution(
        contribution_id="milliliters",
        tracked_instance_id="instance:ml",
        product_id="product:ml",
        formulation_id="formulation:ml",
        plan_id="plan:ml",
        subject_kind=SubjectKind.INGREDIENT,
        subject_id="ingredient:test-liquid",
        amount_basis=AmountBasis.MATERIAL,
        value="1000",
        unit=Unit.MILLILITER,
        source_amount_ids=("amount:ml",),
    )

    result = aggregate_daily_contributions([liters, milliliters])

    aggregate = result.aggregates[0]

    assert aggregate.known_total is None

    assert AggregationIssue.INCOMPATIBLE_NON_MASS_UNITS in aggregate.issues


def test_traceability_is_preserved() -> None:
    contribution = _resolved_contribution(
        contribution_id="trace",
        tracked_instance_id="instance:trace",
        product_id="product:trace",
        formulation_id="formulation:trace",
        plan_id="plan:trace",
        plan_version="7",
        source_amount_ids=("amount:trace",),
        source_ids=("source:trace",),
        source_basis_ids=("basis:trace",),
    )

    resolved = aggregate_daily_contributions([contribution]).aggregates[0].contributors[0]

    assert resolved.product_id == "product:trace"
    assert resolved.formulation_id == "formulation:trace"
    assert resolved.tracked_instance_id == "instance:trace"
    assert resolved.plan_id == "plan:trace"
    assert resolved.plan_version == "7"

    assert resolved.original_amount.source_amount_ids == ("amount:trace",)

    assert resolved.original_amount.source_ids == ("source:trace",)

    assert resolved.original_amount.source_quantity_basis_ids == ("basis:trace",)


def test_resolved_contribution_requires_daily_basis() -> None:
    amount = ComputedAmount(
        subject_kind=SubjectKind.ANALYTE,
        subject_id="analyte:test",
        value=Decimal("1"),
        unit=Unit.MILLIGRAM,
        amount_basis=AmountBasis.ANALYTE,
        quantity_basis=QuantityBasis.PER_CONSUMPTION_UNIT,
        source_quantity_basis_ids=("basis:test",),
        source_amount_ids=("amount:test",),
        source_ids=("source:test",),
        traces=(
            ComputationTrace(
                operation="serving_normalization",
                rule_id="serving",
                rule_version="1",
            ),
        ),
        consumption_unit_id="unit:capsule",
    )

    with pytest.raises(AggregationError):
        ConfirmedPlannedContribution(
            contribution_id="bad",
            confirmation_ref="confirmation:bad",
            product_id="product:bad",
            formulation_id="formulation:bad",
            tracked_instance_id="instance:bad",
            plan_id="plan:bad",
            plan_version="1",
            expected_subject_kind=SubjectKind.ANALYTE,
            expected_subject_id="analyte:test",
            expected_amount_basis=AmountBasis.ANALYTE,
            expected_equivalence_basis=None,
            expected_unit=Unit.MILLIGRAM,
            outcome=NormalizationOutcome(
                status=ResolutionStatus.RESOLVED,
                amount=amount,
            ),
        )


def test_plan_trace_metadata_must_match_wrapper() -> None:
    amount = _daily_amount(plan_id="plan:trace")

    with pytest.raises(AggregationError):
        ConfirmedPlannedContribution(
            contribution_id="bad-plan",
            confirmation_ref="confirmation:bad-plan",
            product_id="product:1",
            formulation_id="formulation:1",
            tracked_instance_id="instance:1",
            plan_id="plan:wrapper",
            plan_version="1",
            expected_subject_kind=SubjectKind.ANALYTE,
            expected_subject_id="analyte:magnesium",
            expected_amount_basis=AmountBasis.ELEMENTAL,
            expected_equivalence_basis=None,
            expected_unit=Unit.MILLIGRAM,
            outcome=NormalizationOutcome(
                status=ResolutionStatus.RESOLVED,
                amount=amount,
            ),
        )
