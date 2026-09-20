from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from vitaminbot.domain import (
    AmountBasis,
    AmountRecord,
    EvidenceStatus,
    IntakePlan,
    PlannedIntakeEvent,
    QuantityBasis,
    ResolutionStatus,
    ServingDefinition,
    SubjectKind,
    Unit,
)
from vitaminbot.nutrition import (
    VITAMIN_D_ANALYTE_ID,
    VITAMIN_D_D2_D3_RULE,
    VITAMIN_D_D2_FORM_ID,
    VITAMIN_D_D3_FORM_ID,
    BasisMismatchError,
    ComputationTrace,
    ComputedAmount,
    DimensionMismatchError,
    NormalizationError,
    RoundingMode,
    RoundingPolicy,
    RoundingRequiredError,
    RuleApplicationError,
    RuleValidationError,
    ScientificConversionRule,
    UnresolvedReason,
    apply_scientific_conversion,
    convert_mass,
    normalize_per_consumption_unit,
    normalize_planned_daily_amount,
)

SOURCE_ID = "label:example:v1"
CAPSULE_ID = "consumption-unit:capsule"
PORTION_ID = "basis:portion"


@pytest.mark.parametrize(
    ("value", "source", "target", "expected"),
    [
        (Decimal("1"), Unit.GRAM, Unit.MILLIGRAM, Decimal("1000")),
        (Decimal("1"), Unit.GRAM, Unit.MICROGRAM, Decimal("1000000")),
        (Decimal("1.25"), Unit.MILLIGRAM, Unit.MICROGRAM, Decimal("1250")),
        (Decimal("15000"), Unit.MICROGRAM, Unit.MILLIGRAM, Decimal("15")),
        (Decimal("0"), Unit.MILLIGRAM, Unit.MICROGRAM, Decimal("0")),
    ],
)
def test_mass_conversion_is_exact(
    value: Decimal,
    source: Unit,
    target: Unit,
    expected: Decimal,
) -> None:
    assert convert_mass(value, source, target) == expected


@pytest.mark.parametrize(
    "value",
    [Decimal("0"), Decimal("0.001"), Decimal("1"), Decimal("15.25"), Decimal("1000000")],
)
def test_mass_round_trip_is_exact(value: Decimal) -> None:
    micrograms = convert_mass(value, Unit.GRAM, Unit.MICROGRAM)
    assert convert_mass(micrograms, Unit.MICROGRAM, Unit.GRAM) == value


def test_mass_conversion_is_transitive() -> None:
    value = Decimal("0.123456")
    direct = convert_mass(value, Unit.GRAM, Unit.MICROGRAM)
    via_mg = convert_mass(
        convert_mass(value, Unit.GRAM, Unit.MILLIGRAM),
        Unit.MILLIGRAM,
        Unit.MICROGRAM,
    )
    assert direct == via_mg


def test_negative_mass_rejected() -> None:
    with pytest.raises(ValueError):
        convert_mass(Decimal("-1"), Unit.MILLIGRAM, Unit.MICROGRAM)

def test_infinite_resolved_source_amount_is_rejected_before_fraction() -> None:
    amount = AmountRecord(
        amount_id="amount:infinite",
        subject_kind=SubjectKind.ANALYTE,
        subject_id="analyte:magnesium",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal("Infinity"),
        unit=Unit.MILLIGRAM,
        amount_basis=AmountBasis.ELEMENTAL,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
    )

    with pytest.raises(ValueError):
        normalize_per_consumption_unit(amount, _serving("2"))

def test_computed_amount_rejects_subject_amount_basis_mismatch() -> None:
    with pytest.raises(NormalizationError):
        ComputedAmount(
            subject_kind=SubjectKind.INGREDIENT,
            subject_id="ingredient:invalid-elemental",
            value=Decimal("1"),
            unit=Unit.MILLIGRAM,
            amount_basis=AmountBasis.ELEMENTAL,
            quantity_basis=QuantityBasis.PER_DAY,
            source_quantity_basis_ids=(),
            source_amount_ids=("amount:source",),
            source_ids=("source:test",),
            traces=(
                ComputationTrace(
                    operation="test",
                    rule_id="test-rule",
                    rule_version="1",
                ),
            ),
        )


@pytest.mark.parametrize("unit", [Unit.INTERNATIONAL_UNIT, Unit.MILLILITER, Unit.COUNT])
def test_generic_mass_converter_rejects_non_mass_units(unit: Unit) -> None:
    with pytest.raises(DimensionMismatchError):
        convert_mass(Decimal("1"), unit, Unit.MICROGRAM)


def test_scientific_rule_rejects_zero_factor() -> None:
    with pytest.raises(RuleValidationError):
        ScientificConversionRule(
            rule_id="rule",
            rule_version="1",
            analyte_id="analyte:test",
            from_unit=Unit.INTERNATIONAL_UNIT,
            to_unit=Unit.MICROGRAM,
            factor_numerator=0,
            factor_denominator=1,
            allowed_chemical_form_ids=("chemical-form:test",),
            equivalence_basis="test",
            authority_source_id="source:test",
            source_version="1",
            source_locator="test locator",
        )


def test_scientific_rule_rejects_negative_factor() -> None:
    with pytest.raises(RuleValidationError):
        ScientificConversionRule(
            rule_id="rule",
            rule_version="1",
            analyte_id="analyte:test",
            from_unit=Unit.INTERNATIONAL_UNIT,
            to_unit=Unit.MICROGRAM,
            factor_numerator=1,
            factor_denominator=-40,
            allowed_chemical_form_ids=("chemical-form:test",),
            equivalence_basis="test",
            authority_source_id="source:test",
            source_version="1",
            source_locator="test locator",
        )


def test_scientific_rule_has_no_independent_reverse_factor_api() -> None:
    payload: dict[str, object] = {
        "rule_id": "rule",
        "rule_version": "1",
        "analyte_id": "analyte:test",
        "from_unit": Unit.INTERNATIONAL_UNIT,
        "to_unit": Unit.MICROGRAM,
        "factor_numerator": 1,
        "factor_denominator": 40,
        "reverse_factor_numerator": 41,
        "reverse_factor_denominator": 1,
        "allowed_chemical_form_ids": ("chemical-form:test",),
        "equivalence_basis": "test",
        "authority_source_id": "source:test",
        "source_version": "1",
        "source_locator": "test locator",
    }

    with pytest.raises(TypeError):
        ScientificConversionRule(**payload)  # type: ignore[arg-type]


def _vitamin_d_amount(value: str, unit: Unit) -> AmountRecord:
    return AmountRecord(
        amount_id=f"amount:vitamin-d:{value}:{unit.value}",
        subject_kind=SubjectKind.ANALYTE,
        subject_id=VITAMIN_D_ANALYTE_ID,
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal(value),
        unit=unit,
        amount_basis=AmountBasis.ANALYTE,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
    )


@pytest.mark.parametrize(
    "chemical_form_id",
    [VITAMIN_D_D2_FORM_ID, VITAMIN_D_D3_FORM_ID],
)
def test_vitamin_d_1000_iu_to_25_ug(chemical_form_id: str) -> None:
    outcome = apply_scientific_conversion(
        _vitamin_d_amount("1000", Unit.INTERNATIONAL_UNIT),
        VITAMIN_D_D2_D3_RULE,
        chemical_form_id=chemical_form_id,
    )

    assert outcome.status is ResolutionStatus.RESOLVED
    assert outcome.amount is not None
    assert outcome.amount.value == Decimal("25")
    assert outcome.amount.unit is Unit.MICROGRAM
    assert outcome.amount.equivalence_basis is not None
    trace = outcome.amount.traces[-1]
    assert trace.rule_id == VITAMIN_D_D2_D3_RULE.rule_id
    assert trace.authority_source_id == "doi:10.2903/j.efsa.2023.8145"

def test_vitamin_d_1_iu_to_exact_0_025_ug() -> None:
    outcome = apply_scientific_conversion(
        _vitamin_d_amount("1", Unit.INTERNATIONAL_UNIT),
        VITAMIN_D_D2_D3_RULE,
        chemical_form_id=VITAMIN_D_D3_FORM_ID,
    )

    assert outcome.status is ResolutionStatus.RESOLVED
    assert outcome.amount is not None
    assert outcome.amount.value == Decimal("0.025")
    assert outcome.amount.amount_basis is AmountBasis.EQUIVALENT
    assert outcome.amount.equivalence_basis == VITAMIN_D_D2_D3_RULE.equivalence_basis


@pytest.mark.parametrize(
    "chemical_form_id",
    [VITAMIN_D_D2_FORM_ID, VITAMIN_D_D3_FORM_ID],
)
def test_vitamin_d_reverse_is_exact_reciprocal(chemical_form_id: str) -> None:
    outcome = apply_scientific_conversion(
        _vitamin_d_amount("25", Unit.MICROGRAM),
        VITAMIN_D_D2_D3_RULE,
        chemical_form_id=chemical_form_id,
    )

    assert outcome.status is ResolutionStatus.RESOLVED
    assert outcome.amount is not None
    assert outcome.amount.value == Decimal("1000")
    assert outcome.amount.unit is Unit.INTERNATIONAL_UNIT
    assert VITAMIN_D_D2_D3_RULE.reciprocal_factor == 40

def test_scientific_and_serving_normalization_compose_with_lineage() -> None:
    converted = apply_scientific_conversion(
        _vitamin_d_amount("1000", Unit.INTERNATIONAL_UNIT),
        VITAMIN_D_D2_D3_RULE,
        chemical_form_id=VITAMIN_D_D3_FORM_ID,
    )
    assert converted.amount is not None

    per_capsule = normalize_per_consumption_unit(
        converted.amount,
        _serving("2"),
    )

    assert per_capsule.status is ResolutionStatus.RESOLVED
    assert per_capsule.amount is not None
    assert per_capsule.amount.value == Decimal("12.5")
    assert per_capsule.amount.unit is Unit.MICROGRAM
    assert per_capsule.amount.amount_basis is AmountBasis.EQUIVALENT
    assert per_capsule.amount.consumption_unit_id == CAPSULE_ID
    assert PORTION_ID in per_capsule.amount.source_quantity_basis_ids
    assert [trace.operation for trace in per_capsule.amount.traces] == [
        "scientific_conversion",
        "serving_normalization",
    ]

def test_scientific_conversion_cannot_change_resolved_chemical_form() -> None:
    converted = apply_scientific_conversion(
        _vitamin_d_amount("1000", Unit.INTERNATIONAL_UNIT),
        VITAMIN_D_D2_D3_RULE,
        chemical_form_id=VITAMIN_D_D3_FORM_ID,
    )
    assert converted.amount is not None

    with pytest.raises(RuleApplicationError):
        apply_scientific_conversion(
            converted.amount,
            VITAMIN_D_D2_D3_RULE,
            chemical_form_id=VITAMIN_D_D2_FORM_ID,
        )


def test_vitamin_d_unknown_form_fails_closed() -> None:
    outcome = apply_scientific_conversion(
        _vitamin_d_amount("1000", Unit.INTERNATIONAL_UNIT),
        VITAMIN_D_D2_D3_RULE,
        chemical_form_id=None,
    )

    assert outcome.status is ResolutionStatus.UNRESOLVED_IDENTITY
    assert outcome.amount is None
    assert outcome.reason is UnresolvedReason.CHEMICAL_FORM_REQUIRED


def test_vitamin_d_calcidiol_is_not_generalized() -> None:
    outcome = apply_scientific_conversion(
        _vitamin_d_amount("1000", Unit.INTERNATIONAL_UNIT),
        VITAMIN_D_D2_D3_RULE,
        chemical_form_id="chemical-form:calcidiol-monohydrate",
    )

    assert outcome.status is ResolutionStatus.UNRESOLVED_IDENTITY
    assert outcome.reason is UnresolvedReason.CHEMICAL_FORM_NOT_APPLICABLE


def test_scientific_rule_rejects_wrong_analyte() -> None:
    amount = AmountRecord(
        amount_id="amount:not-vitamin-d",
        subject_kind=SubjectKind.ANALYTE,
        subject_id="analyte:vitamin-a",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal("1000"),
        unit=Unit.INTERNATIONAL_UNIT,
        amount_basis=AmountBasis.ANALYTE,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
    )

    with pytest.raises(RuleApplicationError):
        apply_scientific_conversion(
            amount,
            VITAMIN_D_D2_D3_RULE,
            chemical_form_id=VITAMIN_D_D3_FORM_ID,
        )


def _serving(quantity: str) -> ServingDefinition:
    return ServingDefinition(
        basis_id=PORTION_ID,
        basis_type=QuantityBasis.PER_LABEL_PORTION,
        label_text=f"serving: {quantity} capsules",
        source_id=SOURCE_ID,
        basis_quantity=Decimal(quantity),
        basis_unit=Unit.COUNT,
        consumption_unit_id=CAPSULE_ID,
    )


def _elemental_magnesium(value: str) -> AmountRecord:
    return AmountRecord(
        amount_id=f"amount:magnesium:{value}",
        subject_kind=SubjectKind.ANALYTE,
        subject_id="analyte:magnesium",
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal(value),
        unit=Unit.MILLIGRAM,
        amount_basis=AmountBasis.ELEMENTAL,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
    )


def test_magnesium_per_serving_to_per_capsule() -> None:
    outcome = normalize_per_consumption_unit(
        _elemental_magnesium("200"),
        _serving("2"),
    )

    assert outcome.status is ResolutionStatus.RESOLVED
    assert outcome.amount is not None
    assert outcome.amount.value == Decimal("100")
    assert outcome.amount.amount_basis is AmountBasis.ELEMENTAL
    assert outcome.amount.quantity_basis is QuantityBasis.PER_CONSUMPTION_UNIT
    assert outcome.amount.consumption_unit_id == CAPSULE_ID
    assert PORTION_ID in outcome.amount.source_quantity_basis_ids

def test_finite_decimal_serving_fraction_with_unequal_two_five_powers_is_exact() -> None:
    outcome = normalize_per_consumption_unit(
        _elemental_magnesium("1"),
        _serving("8"),
    )

    assert outcome.status is ResolutionStatus.RESOLVED
    assert outcome.amount is not None
    assert outcome.amount.value == Decimal("0.125")
    assert outcome.amount.traces[-1].rounding is None


def test_magnesium_plan_to_daily_amount() -> None:
    per_capsule = normalize_per_consumption_unit(
        _elemental_magnesium("200"),
        _serving("2"),
    )
    assert per_capsule.amount is not None

    plan = IntakePlan(
        plan_id="plan:magnesium",
        tracked_instance_id="instance:magnesium",
        version="1",
        events=(
            PlannedIntakeEvent(
                event_id="morning",
                consumption_unit_id=CAPSULE_ID,
                consumption_units=Decimal("1"),
            ),
            PlannedIntakeEvent(
                event_id="evening",
                consumption_unit_id=CAPSULE_ID,
                consumption_units=Decimal("2"),
            ),
        ),
    )
    daily = normalize_planned_daily_amount(per_capsule.amount, plan)

    assert daily.status is ResolutionStatus.RESOLVED
    assert daily.amount is not None
    assert daily.amount.value == Decimal("300")
    assert daily.amount.quantity_basis is QuantityBasis.PER_DAY
    assert daily.amount.consumption_unit_id is None
    assert daily.amount.traces[-1].plan_id == "plan:magnesium"


def test_compound_magnesium_stays_compound() -> None:
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

    outcome = normalize_per_consumption_unit(compound, _serving("2"))

    assert outcome.amount is not None
    assert outcome.amount.value == Decimal("250")
    assert outcome.amount.subject_kind is SubjectKind.INGREDIENT
    assert outcome.amount.subject_id == "ingredient:magnesium-citrate"
    assert outcome.amount.amount_basis is AmountBasis.INGREDIENT_COMPOUND


def test_nonterminating_serving_division_requires_rounding_policy() -> None:
    with pytest.raises(RoundingRequiredError):
        normalize_per_consumption_unit(
            _elemental_magnesium("100"),
            _serving("3"),
        )


def test_explicit_rounding_policy_is_deterministic() -> None:
    policy = RoundingPolicy(
        quantum=Decimal("0.01"),
        mode=RoundingMode.HALF_UP,
    )
    outcome = normalize_per_consumption_unit(
        _elemental_magnesium("100"),
        _serving("3"),
        rounding_policy=policy,
    )

    assert outcome.amount is not None
    assert outcome.amount.value == Decimal("33.33")
    assert outcome.amount.traces[-1].rounding is not None


def test_ambient_decimal_context_does_not_change_result() -> None:
    policy = RoundingPolicy(
        quantum=Decimal("0.01"),
        mode=RoundingMode.HALF_UP,
    )

    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        first = normalize_per_consumption_unit(
            _elemental_magnesium("100"),
            _serving("3"),
            rounding_policy=policy,
        )

    with localcontext() as context:
        context.prec = 50
        second = normalize_per_consumption_unit(
            _elemental_magnesium("100"),
            _serving("3"),
            rounding_policy=policy,
        )

    assert first.amount is not None
    assert second.amount is not None
    assert first.amount.value == second.amount.value == Decimal("33.33")


def test_basis_mismatch_is_rejected() -> None:
    amount = _elemental_magnesium("200")
    mismatched = ServingDefinition(
        basis_id="basis:other",
        basis_type=QuantityBasis.PER_LABEL_PORTION,
        label_text="other",
        source_id=SOURCE_ID,
        basis_quantity=Decimal("2"),
        basis_unit=Unit.COUNT,
        consumption_unit_id=CAPSULE_ID,
    )

    with pytest.raises(BasisMismatchError):
        normalize_per_consumption_unit(amount, mismatched)


def _per_capsule_analyte(
    *,
    amount_id: str,
    analyte_id: str,
    value: str,
    unit: Unit,
) -> AmountRecord:
    return AmountRecord(
        amount_id=amount_id,
        subject_kind=SubjectKind.ANALYTE,
        subject_id=analyte_id,
        source_id=SOURCE_ID,
        resolution_status=ResolutionStatus.RESOLVED,
        evidence_status=EvidenceStatus.DECLARED,
        value=Decimal(value),
        unit=unit,
        amount_basis=AmountBasis.ANALYTE,
        quantity_basis=QuantityBasis.PER_LABEL_PORTION,
        quantity_basis_id=PORTION_ID,
    )


def _two_capsules_daily() -> IntakePlan:
    return IntakePlan(
        plan_id="plan:two-per-day",
        tracked_instance_id="instance:example",
        version="1",
        events=(
            PlannedIntakeEvent(
                event_id="event:one",
                consumption_unit_id=CAPSULE_ID,
                consumption_units=Decimal("1"),
            ),
            PlannedIntakeEvent(
                event_id="event:two",
                consumption_unit_id=CAPSULE_ID,
                consumption_units=Decimal("1"),
            ),
        ),
    )


def test_selenium_golden_daily_amount() -> None:
    per_capsule = normalize_per_consumption_unit(
        _per_capsule_analyte(
            amount_id="amount:selenium",
            analyte_id="analyte:selenium",
            value="55",
            unit=Unit.MICROGRAM,
        ),
        _serving("1"),
    )
    assert per_capsule.amount is not None

    daily = normalize_planned_daily_amount(
        per_capsule.amount,
        _two_capsules_daily(),
    )
    assert daily.amount is not None
    assert daily.amount.value == Decimal("110")
    assert daily.amount.unit is Unit.MICROGRAM


def test_zinc_golden_mass_conversion() -> None:
    assert convert_mass(Decimal("15"), Unit.MILLIGRAM, Unit.MICROGRAM) == Decimal("15000")
    assert convert_mass(Decimal("15000"), Unit.MICROGRAM, Unit.MILLIGRAM) == Decimal("15")


@pytest.mark.parametrize(
    ("analyte_id", "per_capsule_value", "expected_daily"),
    [
        ("analyte:epa", "180", Decimal("360")),
        ("analyte:dha", "120", Decimal("240")),
    ],
)
def test_epa_dha_are_normalized_independently(
    analyte_id: str,
    per_capsule_value: str,
    expected_daily: Decimal,
) -> None:
    per_capsule = normalize_per_consumption_unit(
        _per_capsule_analyte(
            amount_id=f"amount:{analyte_id}",
            analyte_id=analyte_id,
            value=per_capsule_value,
            unit=Unit.MILLIGRAM,
        ),
        _serving("1"),
    )
    assert per_capsule.amount is not None

    daily = normalize_planned_daily_amount(
        per_capsule.amount,
        _two_capsules_daily(),
    )
    assert daily.amount is not None
    assert daily.amount.subject_id == analyte_id
    assert daily.amount.value == expected_daily


def test_fish_oil_material_never_becomes_epa_or_dha() -> None:
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

    per_capsule = normalize_per_consumption_unit(fish_oil, _serving("1"))

    assert per_capsule.amount is not None
    assert per_capsule.amount.subject_kind is SubjectKind.INGREDIENT
    assert per_capsule.amount.subject_id == "ingredient:fish-oil"
    assert per_capsule.amount.amount_basis is AmountBasis.MATERIAL