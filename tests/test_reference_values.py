from decimal import Decimal

import pytest

from vitaminbot.domain import (
    AmountBasis,
    LifeStage,
    QuantityBasis,
    SexApplicability,
    SubjectKind,
    Unit,
)
from vitaminbot.nutrition import (
    EU_EFSA_REFERENCE_DATASET,
    ApplicabilityReason,
    ComparisonRelation,
    ComparisonStatus,
    ComputationTrace,
    ComputedAmount,
    DHAForm,
    ExposureBasis,
    ExposureContext,
    ExposureCoverage,
    LookupStatus,
    PhysiologicalCondition,
    PopulationProfile,
    ReferenceDataError,
    ReferenceQuery,
    ReferenceStatus,
    ReferenceType,
    SourceClass,
    compare_amount_to_reference,
    comparison_is_stale,
    lookup_reference,
)


def _profile(
    *,
    age_months: int | None = 360,
    sex: SexApplicability | None = SexApplicability.FEMALE,
    life_stage: LifeStage | None = LifeStage.GENERAL,
    physiological_condition: PhysiologicalCondition | None = None,
) -> PopulationProfile:
    return PopulationProfile(
        age_months=age_months,
        sex=sex,
        life_stage=life_stage,
        physiological_condition=physiological_condition,
    )


def _query(
    substance_key: str,
    reference_type: ReferenceType,
    *,
    profile: PopulationProfile | None = None,
    exposure: ExposureContext | None = None,
    phytate: str | None = None,
    minimal_cutaneous_synthesis: bool | None = None,
    exact_record_id: str | None = None,
    context_revision: str | None = None,
) -> ReferenceQuery:
    return ReferenceQuery(
        substance_key=substance_key,
        reference_type=reference_type,
        profile=profile or _profile(),
        exposure=exposure or ExposureContext(),
        dietary_phytate_mg_per_day=Decimal(phytate) if phytate is not None else None,
        minimal_cutaneous_synthesis=minimal_cutaneous_synthesis,
        exact_record_id=exact_record_id,
        context_revision=context_revision,
    )


def _amount(
    *,
    subject_kind: SubjectKind = SubjectKind.ANALYTE,
    subject_id: str,
    amount_basis: AmountBasis = AmountBasis.ANALYTE,
    equivalence_basis: str | None = None,
    value: str,
    unit: Unit,
) -> ComputedAmount:
    return ComputedAmount(
        subject_kind=subject_kind,
        subject_id=subject_id,
        value=Decimal(value),
        unit=unit,
        amount_basis=amount_basis,
        quantity_basis=QuantityBasis.PER_DAY,
        source_quantity_basis_ids=(),
        source_amount_ids=("amount:test",),
        source_ids=("source:test",),
        traces=(
            ComputationTrace(
                operation="test_fixture",
                rule_id="test",
                rule_version="1",
            ),
        ),
        equivalence_basis=equivalence_basis,
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
    form: DHAForm | None = DHAForm.TRIACYLGLYCEROL,
    coverage: ExposureCoverage | None = ExposureCoverage.COMPLETE_QUALIFYING,
    includes_background: bool | None = False,
) -> ExposureContext:
    return ExposureContext(
        exposure_basis=ExposureBasis.SUPPLEMENTAL_OR_ADDED_DHA,
        source_class=source_class,
        dha_form=form,
        epa_mg_per_day=Decimal(epa) if epa is not None else None,
        dha_mg_per_day=Decimal(dha) if dha is not None else None,
        coverage=coverage,
        amount_includes_background_dietary_dha=includes_background,
    )


def test_dataset_has_stable_source_provenance_for_every_record() -> None:
    dataset = EU_EFSA_REFERENCE_DATASET

    assert dataset.version.startswith("eu-efsa-mvp-")
    assert dataset.records
    assert dataset.sources

    for record in dataset.records:
        source = dataset.get_source(record.source_key)
        assert source is not None
        assert source.stable_id
        assert source.version_label
        assert source.source_url
        assert record.source_locator


def test_ul_and_safe_level_are_distinct_types() -> None:
    assert ReferenceType.UL is not ReferenceType.SAFE_LEVEL
    assert ReferenceType.UL.value != ReferenceType.SAFE_LEVEL.value


def test_adult_b6_ul_is_final_12_mg_not_intermediate_12_5() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "vitamin_b6",
            ReferenceType.UL,
            exposure=_total_exposure(),
        ),
    )

    assert result.status is LookupStatus.MATCHED
    assert result.match is not None
    assert result.match.record.value == Decimal("12")
    assert result.match.record.unit is Unit.MILLIGRAM

    assert not any(
        record.substance_key == "vitamin_b6"
        and record.reference_type is ReferenceType.UL
        and record.value == Decimal("12.5")
        for record in EU_EFSA_REFERENCE_DATASET.records
    )


def test_adult_selenium_current_ul_is_255_micrograms() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "selenium",
            ReferenceType.UL,
            exposure=_total_exposure(),
        ),
    )

    assert result.status is LookupStatus.MATCHED
    assert result.match is not None
    assert result.match.record.value == Decimal("255")
    assert result.match.record.source_key == "SE-UL"


def test_pediatric_calcium_does_not_fall_back_to_adult_ul() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "calcium",
            ReferenceType.UL,
            profile=_profile(age_months=120),
            exposure=_total_exposure(),
        ),
    )

    assert result.status is LookupStatus.MATCHED
    assert result.match is not None
    assert result.match.record.value is None
    assert result.match.record.status is ReferenceStatus.NO_UL_INSUFFICIENT_DATA
    assert result.match.record.record_id == "calcium-ul-pediatric-no-ul"


def test_missing_age_is_indeterminate_not_adult_fallback() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "calcium",
            ReferenceType.UL,
            profile=_profile(age_months=None),
            exposure=_total_exposure(),
        ),
    )

    assert result.status is LookupStatus.INDETERMINATE
    assert ApplicabilityReason.MISSING_AGE in result.reasons


def test_adult_calcium_ul_is_2500_mg_total_intake() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "calcium",
            ReferenceType.UL,
            exposure=_total_exposure(),
        ),
    )

    assert result.status is LookupStatus.MATCHED
    assert result.match is not None
    assert result.match.record.value == Decimal("2500")
    assert result.match.record.exposure_basis is ExposureBasis.TOTAL_INTAKE


def test_vitamin_c_no_ul_is_explicit_non_numeric_data() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query("vitamin_c", ReferenceType.UL),
    )

    assert result.status is LookupStatus.MATCHED
    assert result.match is not None
    assert result.match.record.value is None
    assert result.match.record.status is ReferenceStatus.NO_UL_INSUFFICIENT_DATA


def test_b12_no_numeric_ul_does_not_become_infinity() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query("vitamin_b12", ReferenceType.UL),
    )

    assert result.status is LookupStatus.MATCHED
    assert result.match is not None
    assert result.match.record.value is None
    assert result.match.record.status is ReferenceStatus.NO_NUMERIC_UL_NO_DEFINED_ADVERSE_EFFECTS


def test_iron_no_ul_and_numeric_safe_level_coexist_without_aliasing() -> None:
    no_ul = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query("iron", ReferenceType.UL),
    )
    safe_level = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "iron",
            ReferenceType.SAFE_LEVEL,
            exposure=ExposureContext(
                exposure_basis=ExposureBasis.TOTAL_INTAKE,
                under_medical_supervision=False,
            ),
        ),
    )

    assert no_ul.status is LookupStatus.MATCHED
    assert no_ul.match is not None
    assert no_ul.match.record.value is None
    assert no_ul.match.record.status is ReferenceStatus.NO_UL_SAFE_LEVEL_IDENTIFIED

    assert safe_level.status is LookupStatus.MATCHED
    assert safe_level.match is not None
    assert safe_level.match.record.reference_type is ReferenceType.SAFE_LEVEL
    assert safe_level.match.record.value == Decimal("40")


def test_iron_safe_level_requires_medical_supervision_applicability() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "iron",
            ReferenceType.SAFE_LEVEL,
            exposure=ExposureContext(exposure_basis=ExposureBasis.TOTAL_INTAKE),
        ),
    )

    assert result.status is LookupStatus.INDETERMINATE
    assert ApplicabilityReason.MISSING_MEDICAL_SUPERVISION_STATUS in result.reasons


def test_iron_safe_level_above_relation_is_not_toxicity_verdict() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "iron",
            ReferenceType.SAFE_LEVEL,
            exposure=ExposureContext(
                exposure_basis=ExposureBasis.TOTAL_INTAKE,
                under_medical_supervision=False,
            ),
        ),
    )
    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:iron",
            value="45",
            unit=Unit.MILLIGRAM,
        ),
        lookup,
    )

    assert comparison.status is ComparisonStatus.COMPARABLE
    assert comparison.relation is ComparisonRelation.ABOVE
    assert comparison.personal_safety_conclusion_withheld is True


def test_folate_dfe_and_supplemental_folate_are_distinct_semantics() -> None:
    drv = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "folate_dfe",
            ReferenceType.PRI,
            exposure=_dietary_exposure(),
        ),
    )
    ul = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "supplemental_folate",
            ReferenceType.UL,
            exposure=ExposureContext(
                exposure_basis=ExposureBasis.FORTIFIED_AND_SUPPLEMENTAL_FOLATE
            ),
        ),
    )

    assert drv.status is LookupStatus.MATCHED
    assert drv.match is not None
    assert drv.match.record.amount_basis is AmountBasis.EQUIVALENT
    assert drv.match.record.equivalence_basis == "dietary_folate_equivalent"

    assert ul.status is LookupStatus.MATCHED
    assert ul.match is not None
    assert ul.match.record.amount_basis is AmountBasis.ANALYTE
    assert ul.match.record.equivalence_basis is None
    assert drv.match.record.subject_id != ul.match.record.subject_id


def test_adult_zinc_drv_requires_explicit_dietary_phytate() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "zinc",
            ReferenceType.PRI,
            profile=_profile(
                sex=SexApplicability.MALE,
                life_stage=LifeStage.GENERAL,
            ),
            exposure=_dietary_exposure(),
        ),
    )

    assert result.status is LookupStatus.INDETERMINATE
    assert ApplicabilityReason.MISSING_PHYTATE in result.reasons


def test_adult_zinc_600_mg_phytate_male_pri_is_11_7_mg() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "zinc",
            ReferenceType.PRI,
            profile=_profile(
                sex=SexApplicability.MALE,
                life_stage=LifeStage.GENERAL,
            ),
            exposure=_dietary_exposure(),
            phytate="600",
        ),
    )

    assert result.status is LookupStatus.MATCHED
    assert result.match is not None
    assert result.match.record.value == Decimal("11.7")
    assert result.match.record.status is ReferenceStatus.CONDITIONAL_NUMERIC


def test_vitamin_d_ai_requires_minimal_cutaneous_synthesis_condition() -> None:
    missing = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "vitamin_d",
            ReferenceType.AI,
            exposure=_dietary_exposure(),
        ),
    )
    matched = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "vitamin_d",
            ReferenceType.AI,
            exposure=_dietary_exposure(),
            minimal_cutaneous_synthesis=True,
        ),
    )

    assert missing.status is LookupStatus.INDETERMINATE
    assert ApplicabilityReason.MISSING_MINIMAL_CUTANEOUS_SYNTHESIS in missing.reasons

    assert matched.status is LookupStatus.MATCHED
    assert matched.match is not None
    assert matched.match.record.value == Decimal("15")


def test_mass_comparison_uses_exact_compatible_unit_conversion() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "selenium",
            ReferenceType.UL,
            exposure=_total_exposure(),
        ),
    )
    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:selenium",
            value="0.255",
            unit=Unit.MILLIGRAM,
        ),
        lookup,
    )

    assert comparison.status is ComparisonStatus.COMPARABLE
    assert comparison.relation is ComparisonRelation.EQUAL
    assert comparison.reference_value == Decimal("255")
    assert comparison.unit is Unit.MICROGRAM


def test_qualifying_dha_safe_level_is_exact_2026_record() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(),
        ),
    )

    assert result.status is LookupStatus.MATCHED
    assert result.match is not None
    assert result.match.record.record_id == "dha-2026-safe-level"
    assert result.match.record.value == Decimal("1")
    assert result.match.record.unit is Unit.GRAM
    assert result.match.source.stable_id == "10.2903/j.efsa.2026.9858"


def test_dha_no_ul_and_safe_level_are_separate_2026_records() -> None:
    exposure = _qualifying_dha_exposure()

    no_ul = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query("dha", ReferenceType.UL, exposure=exposure),
    )
    safe_level = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query("dha", ReferenceType.SAFE_LEVEL, exposure=exposure),
    )

    assert no_ul.status is LookupStatus.MATCHED
    assert no_ul.match is not None
    assert no_ul.match.record.record_id == ("dha-2026-ul-no-ul-safe-level-identified")
    assert no_ul.match.record.value is None
    assert no_ul.match.record.status is ReferenceStatus.NO_UL_SAFE_LEVEL_IDENTIFIED

    assert safe_level.status is LookupStatus.MATCHED
    assert safe_level.match is not None
    assert safe_level.match.record.reference_type is ReferenceType.SAFE_LEVEL


def test_dha_ratio_equal_0_3_does_not_match_2026_safe_level() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(epa="150", dha="500"),
        ),
    )

    assert result.status is LookupStatus.NOT_APPLICABLE
    assert ApplicabilityReason.EPA_DHA_RATIO_NOT_QUALIFYING in result.reasons


def test_dha_ratio_above_0_3_does_not_match_2026_safe_level() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(epa="151", dha="500"),
        ),
    )

    assert result.status is LookupStatus.NOT_APPLICABLE
    assert ApplicabilityReason.EPA_DHA_RATIO_NOT_QUALIFYING in result.reasons


def test_missing_epa_or_dha_is_indeterminate_for_2026_safe_level() -> None:
    missing_epa = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(epa=None),
        ),
    )
    missing_dha = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(dha=None),
        ),
    )

    assert missing_epa.status is LookupStatus.INDETERMINATE
    assert ApplicabilityReason.MISSING_EPA_OR_DHA in missing_epa.reasons
    assert missing_dha.status is LookupStatus.INDETERMINATE
    assert ApplicabilityReason.MISSING_EPA_OR_DHA in missing_dha.reasons


def test_generic_fish_oil_and_epa_dha_do_not_inherit_dha_safe_level() -> None:
    generic_fish_oil = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "fish_oil",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(),
        ),
    )
    generic_epa_dha = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "epa_plus_dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(),
        ),
    )

    assert generic_fish_oil.status is LookupStatus.NOT_FOUND
    assert generic_epa_dha.status is LookupStatus.NOT_FOUND


def test_generic_fish_oil_source_class_does_not_match_dha_safe_level() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(source_class=SourceClass.GENERIC_FISH_OIL),
        ),
    )

    assert result.status is LookupStatus.NOT_APPLICABLE
    assert ApplicabilityReason.SOURCE_CLASS_MISMATCH in result.reasons


def test_missing_dha_form_is_indeterminate() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(form=None),
        ),
    )

    assert result.status is LookupStatus.INDETERMINATE
    assert ApplicabilityReason.MISSING_CHEMICAL_FORM in result.reasons


def test_background_dietary_dha_is_excluded_from_2026_record() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(includes_background=True),
        ),
    )

    assert result.status is LookupStatus.NOT_APPLICABLE
    assert ApplicabilityReason.BACKGROUND_DIETARY_DHA_INCLUDED in result.reasons


def test_mixed_dha_exposure_returns_partial_coverage_not_complete_assessment() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(
                coverage=ExposureCoverage.MIXED_QUALIFYING_AND_NONQUALIFYING
            ),
        ),
    )

    assert result.status is LookupStatus.PARTIAL_COVERAGE
    assert ApplicabilityReason.MIXED_EXPOSURE_COVERAGE in result.reasons


def test_total_fish_oil_material_cannot_be_compared_as_dha() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(),
        ),
    )
    fish_oil_amount = _amount(
        subject_kind=SubjectKind.INGREDIENT,
        subject_id="ingredient:fish-oil",
        amount_basis=AmountBasis.MATERIAL,
        value="0.5",
        unit=Unit.GRAM,
    )

    comparison = compare_amount_to_reference(fish_oil_amount, lookup)

    assert comparison.status is ComparisonStatus.INPUT_NOT_COMPARABLE
    assert comparison.relation is None
    assert comparison.personal_safety_conclusion_withheld is True


def test_below_dha_safe_level_is_only_neutral_reference_relation() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(),
        ),
    )
    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:dha",
            value="900",
            unit=Unit.MILLIGRAM,
        ),
        lookup,
    )

    assert comparison.status is ComparisonStatus.COMPARABLE
    assert comparison.relation is ComparisonRelation.BELOW
    assert comparison.personal_safety_conclusion_withheld is True


def test_above_dha_safe_level_is_not_toxicity_classification() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(),
        ),
    )
    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:dha",
            value="1100",
            unit=Unit.MILLIGRAM,
        ),
        lookup,
    )

    assert comparison.status is ComparisonStatus.COMPARABLE
    assert comparison.relation is ComparisonRelation.ABOVE
    assert comparison.personal_safety_conclusion_withheld is True


def test_2026_narrow_precedence_preserves_exact_2012_historical_reproduction() -> None:
    current = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.UL,
            exposure=_qualifying_dha_exposure(),
        ),
    )
    historical = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.UL,
            exposure=_qualifying_dha_exposure(),
            exact_record_id="o3-2012-dha-ul-no-ul",
        ),
    )

    assert current.status is LookupStatus.MATCHED
    assert current.match is not None
    assert current.match.record.record_id == ("dha-2026-ul-no-ul-safe-level-identified")
    assert current.match.source.source_key == "O3-DHA-SAFE-2026"

    assert historical.status is LookupStatus.MATCHED
    assert historical.match is not None
    assert historical.match.record.record_id == "o3-2012-dha-ul-no-ul"
    assert historical.match.source.source_key == "O3-UL"


def test_exact_historical_lookup_cannot_cross_substance_or_type() -> None:
    result = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "iron",
            ReferenceType.SAFE_LEVEL,
            exact_record_id="o3-2012-dha-ul-no-ul",
        ),
    )

    assert result.status is LookupStatus.NOT_APPLICABLE
    assert ApplicabilityReason.QUERY_RECORD_IDENTITY_MISMATCH in result.reasons


def test_non_numeric_ul_comparison_stays_non_numeric() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query("vitamin_c", ReferenceType.UL),
    )

    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:vitamin-c",
            value="1000",
            unit=Unit.MILLIGRAM,
        ),
        lookup,
    )

    assert comparison.status is ComparisonStatus.NO_NUMERIC_REFERENCE
    assert comparison.relation is None


def test_increment_reference_does_not_compare_as_absolute_total() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "vitamin_c",
            ReferenceType.PRI,
            profile=_profile(
                sex=SexApplicability.FEMALE,
                life_stage=LifeStage.PREGNANCY,
            ),
            exposure=_dietary_exposure(),
        ),
    )
    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:vitamin-c",
            value="105",
            unit=Unit.MILLIGRAM,
        ),
        lookup,
    )

    assert lookup.status is LookupStatus.MATCHED
    assert lookup.match is not None
    assert lookup.match.record.value_semantics.value == "increment"
    assert comparison.status is ComparisonStatus.INCREMENT_REQUIRES_BASE
    assert comparison.relation is None


def test_dha_pregnancy_range_increment_does_not_invent_point_value() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.AI,
            profile=_profile(life_stage=LifeStage.PREGNANCY),
            exposure=_dietary_exposure(),
        ),
    )
    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:dha",
            value="150",
            unit=Unit.MILLIGRAM,
        ),
        lookup,
    )

    assert lookup.status is LookupStatus.MATCHED
    assert lookup.match is not None
    assert lookup.match.record.value is None
    assert lookup.match.record.value_min == Decimal("100")
    assert lookup.match.record.value_max == Decimal("200")
    assert comparison.status is ComparisonStatus.NON_SCALAR_REFERENCE


def test_runtime_binding_exposes_exact_record_source_and_version() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "vitamin_b6",
            ReferenceType.UL,
            exposure=_total_exposure(),
        ),
    )
    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:vitamin-b6",
            value="12",
            unit=Unit.MILLIGRAM,
        ),
        lookup,
        context_revision="product:v1",
    )

    assert comparison.record_id == "b6-ul-adult"
    assert comparison.reference_type is ReferenceType.UL
    assert comparison.reference_value == Decimal("12")
    assert comparison.source_key == "B6-UL"
    assert comparison.source_version == "EFSA Journal 2023;21(5):8006"
    assert comparison.dataset_version == EU_EFSA_REFERENCE_DATASET.version


def test_dha_lookup_context_revision_cannot_be_rebound_after_reformulation() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(),
            context_revision="formulation:v1",
        ),
    )

    assert lookup.status is LookupStatus.MATCHED
    assert lookup.context_revision == "formulation:v1"

    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:dha",
            value="900",
            unit=Unit.MILLIGRAM,
        ),
        lookup,
    )
    assert comparison.context_revision == "formulation:v1"
    assert (
        comparison_is_stale(
            comparison,
            EU_EFSA_REFERENCE_DATASET,
            context_revision="formulation:v2",
        )
        is True
    )

    with pytest.raises(ReferenceDataError, match="immutable lookup applicability context"):
        compare_amount_to_reference(
            _amount(
                subject_id="analyte:dha",
                value="900",
                unit=Unit.MILLIGRAM,
            ),
            lookup,
            context_revision="formulation:v2",
        )


def test_generic_reference_lookup_context_revision_cannot_be_rebound() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "selenium",
            ReferenceType.UL,
            exposure=_total_exposure(),
            context_revision="product-source:v1",
        ),
    )

    assert lookup.status is LookupStatus.MATCHED
    assert lookup.context_revision == "product-source:v1"

    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:selenium",
            value="200",
            unit=Unit.MICROGRAM,
        ),
        lookup,
    )
    assert comparison.context_revision == "product-source:v1"
    assert (
        comparison_is_stale(
            comparison,
            EU_EFSA_REFERENCE_DATASET,
            context_revision="product-source:v2",
        )
        is True
    )

    with pytest.raises(ReferenceDataError, match="immutable lookup applicability context"):
        compare_amount_to_reference(
            _amount(
                subject_id="analyte:selenium",
                value="200",
                unit=Unit.MICROGRAM,
            ),
            lookup,
            context_revision="product-source:v2",
        )


def test_context_revision_change_invalidates_stale_comparison() -> None:
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        _query(
            "dha",
            ReferenceType.SAFE_LEVEL,
            exposure=_qualifying_dha_exposure(),
            context_revision="formulation:v1",
        ),
    )
    comparison = compare_amount_to_reference(
        _amount(
            subject_id="analyte:dha",
            value="900",
            unit=Unit.MILLIGRAM,
        ),
        lookup,
    )

    assert (
        comparison_is_stale(
            comparison,
            EU_EFSA_REFERENCE_DATASET,
            context_revision="formulation:v1",
        )
        is False
    )
    assert (
        comparison_is_stale(
            comparison,
            EU_EFSA_REFERENCE_DATASET,
            context_revision="formulation:v2",
        )
        is True
    )
