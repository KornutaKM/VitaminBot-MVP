from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Final

from vitaminbot.domain import (
    AmountBasis,
    LifeStage,
    QuantityBasis,
    SexApplicability,
    SubjectKind,
    Unit,
    UnitDimension,
    unit_dimension,
)
from vitaminbot.nutrition.normalization import ComputedAmount, convert_mass


class ReferenceDataError(ValueError):
    """Raised when versioned scientific reference data violate the KIR-115 contract."""


class Authority(StrEnum):
    EU_LEGISLATOR = "eu_legislator"
    EFSA_NDA = "efsa_nda"
    EFSA = "efsa"
    SCF = "scf"


class Jurisdiction(StrEnum):
    EU = "EU"


class SourceFamily(StrEnum):
    EU_LAW = "eu_law"
    EFSA_DRV = "efsa_drv"
    EFSA_SAFETY = "efsa_safety"
    SCF_SAFETY = "scf_safety"
    EFSA_SUMMARY = "efsa_summary"


class StableIdKind(StrEnum):
    DOI = "doi"
    CELEX = "celex"
    OFFICIAL_DOCUMENT_ID = "official_document_id"


class SourceLifecycle(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class ReferenceDomain(StrEnum):
    EU_LABELLING = "eu_labelling"
    EFSA_DIETARY_REFERENCE = "efsa_dietary_reference"
    EFSA_SAFETY = "efsa_safety"


class ReferenceType(StrEnum):
    NRV = "NRV"
    AR = "AR"
    PRI = "PRI"
    AI = "AI"
    RI = "RI"
    UL = "UL"
    SAFE_LEVEL = "SAFE_LEVEL"


class ReferenceStatus(StrEnum):
    ESTABLISHED_NUMERIC = "established_numeric"
    CONDITIONAL_NUMERIC = "conditional_numeric"
    NOT_ESTABLISHED = "not_established"
    NO_UL_INSUFFICIENT_DATA = "no_ul_insufficient_data"
    NO_NUMERIC_UL_NO_DEFINED_ADVERSE_EFFECTS = "no_numeric_ul_no_defined_adverse_effects"
    NO_UL_SAFE_LEVEL_IDENTIFIED = "no_ul_safe_level_identified"


class ReferenceLifecycle(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class ValueSemantics(StrEnum):
    ABSOLUTE = "absolute"
    INCREMENT = "increment"
    RANGE_INCREMENT = "range_increment"


class PhysiologicalCondition(StrEnum):
    PREMENOPAUSAL = "premenopausal"
    POSTMENOPAUSAL = "postmenopausal"


class ExposureBasis(StrEnum):
    LABELLING_REFERENCE = "labelling_reference"
    DIETARY_TOTAL = "dietary_total"
    TOTAL_INTAKE = "total_intake"
    SOURCE_NATIVE_UNSPECIFIED = "source_native_unspecified"
    MAGNESIUM_SUPPLEMENTAL_WATER_OR_ADDED = "magnesium_supplemental_water_or_added"
    FORTIFIED_AND_SUPPLEMENTAL_FOLATE = "fortified_and_supplemental_folate"
    IRON_FORTIFIED_PLUS_SUPPLEMENTAL_EXCLUDING_FORMULA = (
        "iron_fortified_plus_supplemental_excluding_formula"
    )
    SUPPLEMENTAL_OR_ADDED_DHA = "supplemental_or_added_dha"


class SourceClass(StrEnum):
    FISH_OIL_CONCENTRATE = "fish_oil_concentrate"
    ALGAL_OIL = "algal_oil"
    KRILL_OIL = "krill_oil"
    GENERIC_FISH_OIL = "generic_fish_oil"
    GENERIC_OMEGA3 = "generic_omega3"
    GENERIC_EPA_DHA = "generic_epa_dha"


class DHAForm(StrEnum):
    TRIACYLGLYCEROL = "triacylglycerol"
    ETHYL_ESTER = "ethyl_ester"
    PHOSPHOLIPID = "phospholipid"


class ExposureCoverage(StrEnum):
    COMPLETE_QUALIFYING = "complete_qualifying"
    MIXED_QUALIFYING_AND_NONQUALIFYING = "mixed_qualifying_and_nonqualifying"


class ApplicabilityStatus(StrEnum):
    MATCH = "match"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not_applicable"
    PARTIAL_COVERAGE = "partial_coverage"


class ApplicabilityReason(StrEnum):
    MISSING_AGE = "missing_age"
    AGE_MISMATCH = "age_mismatch"
    MISSING_SEX = "missing_sex"
    SEX_MISMATCH = "sex_mismatch"
    MISSING_LIFE_STAGE = "missing_life_stage"
    LIFE_STAGE_MISMATCH = "life_stage_mismatch"
    MISSING_PHYSIOLOGICAL_CONDITION = "missing_physiological_condition"
    PHYSIOLOGICAL_CONDITION_MISMATCH = "physiological_condition_mismatch"
    MISSING_EXPOSURE_BASIS = "missing_exposure_basis"
    EXPOSURE_BASIS_MISMATCH = "exposure_basis_mismatch"
    MISSING_PHYTATE = "missing_phytate"
    PHYTATE_MISMATCH = "phytate_mismatch"
    MISSING_MINIMAL_CUTANEOUS_SYNTHESIS = "missing_minimal_cutaneous_synthesis"
    MINIMAL_CUTANEOUS_SYNTHESIS_MISMATCH = "minimal_cutaneous_synthesis_mismatch"
    MISSING_SOURCE_CLASS = "missing_source_class"
    SOURCE_CLASS_MISMATCH = "source_class_mismatch"
    MISSING_CHEMICAL_FORM = "missing_chemical_form"
    CHEMICAL_FORM_MISMATCH = "chemical_form_mismatch"
    MISSING_EPA_OR_DHA = "missing_epa_or_dha"
    EPA_DHA_RATIO_NOT_QUALIFYING = "epa_dha_ratio_not_qualifying"
    BACKGROUND_DIETARY_DHA_INCLUDED = "background_dietary_dha_included"
    MISSING_BACKGROUND_DHA_SCOPE = "missing_background_dha_scope"
    MISSING_EXPOSURE_COVERAGE = "missing_exposure_coverage"
    MIXED_EXPOSURE_COVERAGE = "mixed_exposure_coverage"
    MISSING_MEDICAL_SUPERVISION_STATUS = "missing_medical_supervision_status"
    MEDICAL_SUPERVISION_EXCLUDED = "medical_supervision_excluded"
    JURISDICTION_MISMATCH = "jurisdiction_mismatch"
    QUERY_RECORD_IDENTITY_MISMATCH = "query_record_identity_mismatch"
    EXACT_RECORD_NOT_FOUND = "exact_record_not_found"


class LookupStatus(StrEnum):
    MATCHED = "matched"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not_applicable"
    PARTIAL_COVERAGE = "partial_coverage"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class ComparisonStatus(StrEnum):
    COMPARABLE = "comparable"
    LOOKUP_NOT_MATCHED = "lookup_not_matched"
    NO_NUMERIC_REFERENCE = "no_numeric_reference"
    NON_SCALAR_REFERENCE = "non_scalar_reference"
    INCREMENT_REQUIRES_BASE = "increment_requires_base"
    INPUT_NOT_COMPARABLE = "input_not_comparable"


class ComparisonRelation(StrEnum):
    BELOW = "below"
    EQUAL = "equal"
    ABOVE = "above"


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceRecord:
    source_key: str
    authority: Authority
    jurisdiction: Jurisdiction
    family: SourceFamily
    stable_id_kind: StableIdKind
    stable_id: str
    title: str
    source_url: str
    adopted_date: str | None
    published_date: str | None
    amended_date: str | None
    version_label: str
    retrieved_at: str
    lifecycle: SourceLifecycle = SourceLifecycle.ACTIVE
    supersedes_source_keys: tuple[str, ...] = ()
    superseded_by_source_key: str | None = None
    provenance_note: str = ""

    def __post_init__(self) -> None:
        for field_name, value in (
            ("source_key", self.source_key),
            ("stable_id", self.stable_id),
            ("title", self.title),
            ("source_url", self.source_url),
            ("version_label", self.version_label),
            ("retrieved_at", self.retrieved_at),
        ):
            if not value.strip():
                raise ReferenceDataError(f"{field_name} must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class PopulationCriteria:
    age_min_months: int | None = None
    age_max_months_exclusive: int | None = None
    sex: SexApplicability = SexApplicability.ALL
    life_stage: LifeStage | None = None
    physiological_condition: PhysiologicalCondition | None = None

    def __post_init__(self) -> None:
        if self.age_min_months is not None and self.age_min_months < 0:
            raise ReferenceDataError("age_min_months must be non-negative")
        if self.age_max_months_exclusive is not None and self.age_max_months_exclusive <= 0:
            raise ReferenceDataError("age_max_months_exclusive must be positive")
        if (
            self.age_min_months is not None
            and self.age_max_months_exclusive is not None
            and self.age_min_months >= self.age_max_months_exclusive
        ):
            raise ReferenceDataError("population age interval must be non-empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceRecord:
    record_id: str
    dataset_version: str
    domain: ReferenceDomain
    reference_type: ReferenceType
    authority: Authority
    jurisdiction: Jurisdiction
    substance_key: str
    subject_kind: SubjectKind
    subject_id: str
    amount_basis: AmountBasis
    equivalence_basis: str | None
    population: PopulationCriteria
    value: Decimal | None
    value_min: Decimal | None
    value_max: Decimal | None
    unit: Unit | None
    quantity_basis: QuantityBasis
    value_semantics: ValueSemantics
    exposure_basis: ExposureBasis
    exposure_match_required: bool
    status: ReferenceStatus
    source_key: str
    source_locator: str
    lifecycle: ReferenceLifecycle = ReferenceLifecycle.ACTIVE
    selection_priority: int = 0
    base_reference_id: str | None = None
    dietary_phytate_mg_per_day: Decimal | None = None
    requires_minimal_cutaneous_synthesis: bool = False
    allowed_source_classes: tuple[SourceClass, ...] = ()
    allowed_dha_forms: tuple[DHAForm, ...] = ()
    epa_dha_ratio_max_exclusive: Decimal | None = None
    requires_epa_and_dha_amounts: bool = False
    excludes_background_dietary_dha: bool = False
    excludes_medical_supervision: bool = False
    supersedes_record_ids: tuple[str, ...] = ()
    superseded_by_record_id: str | None = None
    provenance_note: str = ""

    def __post_init__(self) -> None:
        for field_name, value in (
            ("record_id", self.record_id),
            ("dataset_version", self.dataset_version),
            ("substance_key", self.substance_key),
            ("subject_id", self.subject_id),
            ("source_key", self.source_key),
            ("source_locator", self.source_locator),
        ):
            if not value.strip():
                raise ReferenceDataError(f"{field_name} must not be blank")

        if self.quantity_basis is not QuantityBasis.PER_DAY:
            raise ReferenceDataError("KIR-115 reference values must use PER_DAY basis")

        if self.amount_basis is AmountBasis.EQUIVALENT:
            if self.equivalence_basis is None or not self.equivalence_basis.strip():
                raise ReferenceDataError("equivalent reference amount requires equivalence_basis")
        elif self.equivalence_basis is not None:
            raise ReferenceDataError(
                "equivalence_basis is valid only for equivalent reference amounts"
            )

        scalar = self.value is not None
        ranged = self.value_min is not None or self.value_max is not None
        if scalar and ranged:
            raise ReferenceDataError("reference cannot contain scalar and range values")
        if ranged and (self.value_min is None or self.value_max is None):
            raise ReferenceDataError("range reference requires both endpoints")

        numeric = scalar or ranged
        if numeric and self.unit is None:
            raise ReferenceDataError("numeric reference requires a unit")
        if not numeric and self.unit is not None:
            raise ReferenceDataError("non-numeric reference must not carry a unit")

        values = tuple(
            value for value in (self.value, self.value_min, self.value_max) if value is not None
        )
        if any(not value.is_finite() or value < 0 for value in values):
            raise ReferenceDataError("reference values must be finite and non-negative")
        if (
            self.value_min is not None
            and self.value_max is not None
            and self.value_min > self.value_max
        ):
            raise ReferenceDataError("reference value range is inverted")

        numeric_statuses = {
            ReferenceStatus.ESTABLISHED_NUMERIC,
            ReferenceStatus.CONDITIONAL_NUMERIC,
        }
        if self.status in numeric_statuses and not numeric:
            raise ReferenceDataError("numeric status requires numeric value")
        if self.status not in numeric_statuses and numeric:
            raise ReferenceDataError("non-numeric status cannot carry numeric value")

        if (
            self.value_semantics
            in {
                ValueSemantics.INCREMENT,
                ValueSemantics.RANGE_INCREMENT,
            }
            and self.base_reference_id is None
        ):
            raise ReferenceDataError("increment reference requires base_reference_id")
        if self.value_semantics is ValueSemantics.RANGE_INCREMENT and not ranged:
            raise ReferenceDataError("range increment requires a range value")

        if self.epa_dha_ratio_max_exclusive is not None and self.epa_dha_ratio_max_exclusive <= 0:
            raise ReferenceDataError("EPA/DHA ratio bound must be positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceDataset:
    version: str
    sources: tuple[SourceRecord, ...]
    records: tuple[ReferenceRecord, ...]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ReferenceDataError("dataset version must not be blank")

        source_keys = tuple(source.source_key for source in self.sources)
        if len(source_keys) != len(set(source_keys)):
            raise ReferenceDataError("source keys must be unique")

        record_ids = tuple(record.record_id for record in self.records)
        if len(record_ids) != len(set(record_ids)):
            raise ReferenceDataError("reference record IDs must be unique")

        sources = {source.source_key: source for source in self.sources}
        records = {record.record_id: record for record in self.records}

        for record in self.records:
            if record.dataset_version != self.version:
                raise ReferenceDataError("record dataset_version mismatch")
            source = sources.get(record.source_key)
            if source is None:
                raise ReferenceDataError(f"reference {record.record_id} has unknown source")
            if source.authority is not record.authority:
                raise ReferenceDataError(f"reference {record.record_id} authority/source mismatch")
            if source.jurisdiction is not record.jurisdiction:
                raise ReferenceDataError(
                    f"reference {record.record_id} jurisdiction/source mismatch"
                )
            if record.base_reference_id is not None and record.base_reference_id not in records:
                raise ReferenceDataError(f"reference {record.record_id} has unknown base reference")
            for superseded_id in record.supersedes_record_ids:
                if superseded_id not in records:
                    raise ReferenceDataError(
                        f"reference {record.record_id} supersedes unknown record"
                    )
            if (
                record.superseded_by_record_id is not None
                and record.superseded_by_record_id not in records
            ):
                raise ReferenceDataError(
                    f"reference {record.record_id} has unknown superseding record"
                )

    def get_source(self, source_key: str) -> SourceRecord | None:
        return next(
            (source for source in self.sources if source.source_key == source_key),
            None,
        )

    def get_record(self, record_id: str) -> ReferenceRecord | None:
        return next(
            (record for record in self.records if record.record_id == record_id),
            None,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PopulationProfile:
    age_months: int | None = None
    sex: SexApplicability | None = None
    life_stage: LifeStage | None = None
    physiological_condition: PhysiologicalCondition | None = None

    def __post_init__(self) -> None:
        if self.age_months is not None and self.age_months < 0:
            raise ReferenceDataError("profile age_months must be non-negative")
        if self.sex is SexApplicability.ALL:
            raise ReferenceDataError("profile sex must be male, female, or unknown")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExposureContext:
    exposure_basis: ExposureBasis | None = None
    source_class: SourceClass | None = None
    dha_form: DHAForm | None = None
    epa_mg_per_day: Decimal | None = None
    dha_mg_per_day: Decimal | None = None
    coverage: ExposureCoverage | None = None
    amount_includes_background_dietary_dha: bool | None = None
    under_medical_supervision: bool | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("epa_mg_per_day", self.epa_mg_per_day),
            ("dha_mg_per_day", self.dha_mg_per_day),
        ):
            if value is not None and (not value.is_finite() or value < 0):
                raise ReferenceDataError(f"{field_name} must be finite and non-negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceQuery:
    substance_key: str
    reference_type: ReferenceType
    profile: PopulationProfile
    exposure: ExposureContext
    jurisdiction: Jurisdiction = Jurisdiction.EU
    dietary_phytate_mg_per_day: Decimal | None = None
    minimal_cutaneous_synthesis: bool | None = None
    exact_record_id: str | None = None
    context_revision: str | None = None

    def __post_init__(self) -> None:
        if not self.substance_key.strip():
            raise ReferenceDataError("query substance_key must not be blank")
        if self.dietary_phytate_mg_per_day is not None and (
            not self.dietary_phytate_mg_per_day.is_finite() or self.dietary_phytate_mg_per_day < 0
        ):
            raise ReferenceDataError("dietary_phytate_mg_per_day must be finite and non-negative")
        if self.exact_record_id is not None and not self.exact_record_id.strip():
            raise ReferenceDataError("exact_record_id must not be blank")
        if self.context_revision is not None and not self.context_revision.strip():
            raise ReferenceDataError("context_revision must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicabilityResult:
    status: ApplicabilityStatus
    reasons: tuple[ApplicabilityReason, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceMatch:
    record: ReferenceRecord
    source: SourceRecord
    applicability: ApplicabilityResult


@dataclass(frozen=True, slots=True, kw_only=True)
class LookupResult:
    status: LookupStatus
    dataset_version: str
    context_revision: str | None
    match: ReferenceMatch | None
    reasons: tuple[ApplicabilityReason, ...]
    candidate_record_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ComparisonResult:
    status: ComparisonStatus
    dataset_version: str
    context_revision: str | None
    record_id: str | None
    reference_type: ReferenceType | None
    source_key: str | None
    source_version: str | None
    reference_value: Decimal | None
    reference_value_min: Decimal | None
    reference_value_max: Decimal | None
    unit: Unit | None
    exposure_basis: ExposureBasis | None
    relation: ComparisonRelation | None
    personal_safety_conclusion_withheld: bool = True


def _evaluate_population(
    criteria: PopulationCriteria,
    profile: PopulationProfile,
) -> ApplicabilityResult:
    reasons: list[ApplicabilityReason] = []

    if criteria.age_min_months is not None or criteria.age_max_months_exclusive is not None:
        if profile.age_months is None:
            reasons.append(ApplicabilityReason.MISSING_AGE)
        else:
            if criteria.age_min_months is not None and profile.age_months < criteria.age_min_months:
                return ApplicabilityResult(
                    status=ApplicabilityStatus.NOT_APPLICABLE,
                    reasons=(ApplicabilityReason.AGE_MISMATCH,),
                )
            if (
                criteria.age_max_months_exclusive is not None
                and profile.age_months >= criteria.age_max_months_exclusive
            ):
                return ApplicabilityResult(
                    status=ApplicabilityStatus.NOT_APPLICABLE,
                    reasons=(ApplicabilityReason.AGE_MISMATCH,),
                )

    if criteria.sex is not SexApplicability.ALL:
        if profile.sex is None:
            reasons.append(ApplicabilityReason.MISSING_SEX)
        elif profile.sex is not criteria.sex:
            return ApplicabilityResult(
                status=ApplicabilityStatus.NOT_APPLICABLE,
                reasons=(ApplicabilityReason.SEX_MISMATCH,),
            )

    if criteria.life_stage is not None:
        if profile.life_stage is None:
            reasons.append(ApplicabilityReason.MISSING_LIFE_STAGE)
        elif profile.life_stage is not criteria.life_stage:
            return ApplicabilityResult(
                status=ApplicabilityStatus.NOT_APPLICABLE,
                reasons=(ApplicabilityReason.LIFE_STAGE_MISMATCH,),
            )

    if criteria.physiological_condition is not None:
        if profile.physiological_condition is None:
            reasons.append(ApplicabilityReason.MISSING_PHYSIOLOGICAL_CONDITION)
        elif profile.physiological_condition is not criteria.physiological_condition:
            return ApplicabilityResult(
                status=ApplicabilityStatus.NOT_APPLICABLE,
                reasons=(ApplicabilityReason.PHYSIOLOGICAL_CONDITION_MISMATCH,),
            )

    if reasons:
        return ApplicabilityResult(
            status=ApplicabilityStatus.INDETERMINATE,
            reasons=tuple(sorted(set(reasons), key=lambda reason: reason.value)),
        )

    return ApplicabilityResult(status=ApplicabilityStatus.MATCH, reasons=())


def _evaluate_record(
    record: ReferenceRecord,
    query: ReferenceQuery,
) -> ApplicabilityResult:
    if record.jurisdiction is not query.jurisdiction:
        return ApplicabilityResult(
            status=ApplicabilityStatus.NOT_APPLICABLE,
            reasons=(ApplicabilityReason.JURISDICTION_MISMATCH,),
        )

    population = _evaluate_population(record.population, query.profile)
    if population.status is not ApplicabilityStatus.MATCH:
        return population

    reasons: list[ApplicabilityReason] = []

    if record.exposure_match_required:
        if query.exposure.exposure_basis is None:
            reasons.append(ApplicabilityReason.MISSING_EXPOSURE_BASIS)
        elif query.exposure.exposure_basis is not record.exposure_basis:
            return ApplicabilityResult(
                status=ApplicabilityStatus.NOT_APPLICABLE,
                reasons=(ApplicabilityReason.EXPOSURE_BASIS_MISMATCH,),
            )

    if record.dietary_phytate_mg_per_day is not None:
        if query.dietary_phytate_mg_per_day is None:
            reasons.append(ApplicabilityReason.MISSING_PHYTATE)
        elif query.dietary_phytate_mg_per_day != record.dietary_phytate_mg_per_day:
            return ApplicabilityResult(
                status=ApplicabilityStatus.NOT_APPLICABLE,
                reasons=(ApplicabilityReason.PHYTATE_MISMATCH,),
            )

    if record.requires_minimal_cutaneous_synthesis:
        if query.minimal_cutaneous_synthesis is None:
            reasons.append(ApplicabilityReason.MISSING_MINIMAL_CUTANEOUS_SYNTHESIS)
        elif not query.minimal_cutaneous_synthesis:
            return ApplicabilityResult(
                status=ApplicabilityStatus.NOT_APPLICABLE,
                reasons=(ApplicabilityReason.MINIMAL_CUTANEOUS_SYNTHESIS_MISMATCH,),
            )

    if record.allowed_source_classes:
        if query.exposure.source_class is None:
            reasons.append(ApplicabilityReason.MISSING_SOURCE_CLASS)
        elif query.exposure.source_class not in record.allowed_source_classes:
            return ApplicabilityResult(
                status=ApplicabilityStatus.NOT_APPLICABLE,
                reasons=(ApplicabilityReason.SOURCE_CLASS_MISMATCH,),
            )

    if record.allowed_dha_forms:
        if query.exposure.dha_form is None:
            reasons.append(ApplicabilityReason.MISSING_CHEMICAL_FORM)
        elif query.exposure.dha_form not in record.allowed_dha_forms:
            return ApplicabilityResult(
                status=ApplicabilityStatus.NOT_APPLICABLE,
                reasons=(ApplicabilityReason.CHEMICAL_FORM_MISMATCH,),
            )

    if record.requires_epa_and_dha_amounts:
        epa = query.exposure.epa_mg_per_day
        dha = query.exposure.dha_mg_per_day
        if epa is None or dha is None or dha == 0:
            reasons.append(ApplicabilityReason.MISSING_EPA_OR_DHA)
        elif record.epa_dha_ratio_max_exclusive is not None:
            ratio = Fraction(epa) / Fraction(dha)
            if ratio >= Fraction(record.epa_dha_ratio_max_exclusive):
                return ApplicabilityResult(
                    status=ApplicabilityStatus.NOT_APPLICABLE,
                    reasons=(ApplicabilityReason.EPA_DHA_RATIO_NOT_QUALIFYING,),
                )

    if record.excludes_background_dietary_dha:
        includes_background = query.exposure.amount_includes_background_dietary_dha
        if includes_background is None:
            reasons.append(ApplicabilityReason.MISSING_BACKGROUND_DHA_SCOPE)
        elif includes_background:
            return ApplicabilityResult(
                status=ApplicabilityStatus.NOT_APPLICABLE,
                reasons=(ApplicabilityReason.BACKGROUND_DIETARY_DHA_INCLUDED,),
            )

        if query.exposure.coverage is None:
            reasons.append(ApplicabilityReason.MISSING_EXPOSURE_COVERAGE)
        elif query.exposure.coverage is ExposureCoverage.MIXED_QUALIFYING_AND_NONQUALIFYING:
            return ApplicabilityResult(
                status=ApplicabilityStatus.PARTIAL_COVERAGE,
                reasons=(ApplicabilityReason.MIXED_EXPOSURE_COVERAGE,),
            )

    if record.excludes_medical_supervision:
        supervision = query.exposure.under_medical_supervision
        if supervision is None:
            reasons.append(ApplicabilityReason.MISSING_MEDICAL_SUPERVISION_STATUS)
        elif supervision:
            return ApplicabilityResult(
                status=ApplicabilityStatus.NOT_APPLICABLE,
                reasons=(ApplicabilityReason.MEDICAL_SUPERVISION_EXCLUDED,),
            )

    if reasons:
        return ApplicabilityResult(
            status=ApplicabilityStatus.INDETERMINATE,
            reasons=tuple(sorted(set(reasons), key=lambda reason: reason.value)),
        )

    return ApplicabilityResult(status=ApplicabilityStatus.MATCH, reasons=())


def lookup_reference(
    dataset: ReferenceDataset,
    query: ReferenceQuery,
) -> LookupResult:
    candidates: tuple[ReferenceRecord, ...]
    if query.exact_record_id is not None:
        record = dataset.get_record(query.exact_record_id)
        if record is None:
            return LookupResult(
                status=LookupStatus.NOT_FOUND,
                dataset_version=dataset.version,
                context_revision=query.context_revision,
                match=None,
                reasons=(ApplicabilityReason.EXACT_RECORD_NOT_FOUND,),
                candidate_record_ids=(),
            )
        if (
            record.substance_key != query.substance_key
            or record.reference_type is not query.reference_type
            or record.jurisdiction is not query.jurisdiction
        ):
            return LookupResult(
                status=LookupStatus.NOT_APPLICABLE,
                dataset_version=dataset.version,
                context_revision=query.context_revision,
                match=None,
                reasons=(ApplicabilityReason.QUERY_RECORD_IDENTITY_MISMATCH,),
                candidate_record_ids=(record.record_id,),
            )
        candidates = (record,)
    else:
        candidates = tuple(
            record
            for record in dataset.records
            if record.lifecycle is ReferenceLifecycle.ACTIVE
            and record.substance_key == query.substance_key
            and record.reference_type is query.reference_type
            and record.jurisdiction is query.jurisdiction
        )

    if not candidates:
        return LookupResult(
            status=LookupStatus.NOT_FOUND,
            dataset_version=dataset.version,
            context_revision=query.context_revision,
            match=None,
            reasons=(),
            candidate_record_ids=(),
        )

    evaluated = tuple((record, _evaluate_record(record, query)) for record in candidates)
    matches = tuple(
        (record, applicability)
        for record, applicability in evaluated
        if applicability.status is ApplicabilityStatus.MATCH
    )

    if matches:
        max_priority = max(record.selection_priority for record, _ in matches)
        preferred = tuple(item for item in matches if item[0].selection_priority == max_priority)
        if len(preferred) != 1:
            return LookupResult(
                status=LookupStatus.AMBIGUOUS,
                dataset_version=dataset.version,
                context_revision=query.context_revision,
                match=None,
                reasons=(),
                candidate_record_ids=tuple(sorted(record.record_id for record, _ in preferred)),
            )

        record, applicability = preferred[0]
        source = dataset.get_source(record.source_key)
        if source is None:
            raise ReferenceDataError("validated dataset lost source record")
        return LookupResult(
            status=LookupStatus.MATCHED,
            dataset_version=dataset.version,
            context_revision=query.context_revision,
            match=ReferenceMatch(
                record=record,
                source=source,
                applicability=applicability,
            ),
            reasons=(),
            candidate_record_ids=tuple(sorted(record.record_id for record, _ in matches)),
        )

    partial = tuple(
        applicability
        for _, applicability in evaluated
        if applicability.status is ApplicabilityStatus.PARTIAL_COVERAGE
    )
    if partial:
        reasons = tuple(
            sorted(
                {reason for applicability in partial for reason in applicability.reasons},
                key=lambda reason: reason.value,
            )
        )
        return LookupResult(
            status=LookupStatus.PARTIAL_COVERAGE,
            dataset_version=dataset.version,
            context_revision=query.context_revision,
            match=None,
            reasons=reasons,
            candidate_record_ids=tuple(
                sorted(
                    record.record_id
                    for record, applicability in evaluated
                    if applicability.status is ApplicabilityStatus.PARTIAL_COVERAGE
                )
            ),
        )

    indeterminate = tuple(
        applicability
        for _, applicability in evaluated
        if applicability.status is ApplicabilityStatus.INDETERMINATE
    )
    if indeterminate:
        reasons = tuple(
            sorted(
                {reason for applicability in indeterminate for reason in applicability.reasons},
                key=lambda reason: reason.value,
            )
        )
        return LookupResult(
            status=LookupStatus.INDETERMINATE,
            dataset_version=dataset.version,
            context_revision=query.context_revision,
            match=None,
            reasons=reasons,
            candidate_record_ids=tuple(sorted(record.record_id for record in candidates)),
        )

    return LookupResult(
        status=LookupStatus.NOT_APPLICABLE,
        dataset_version=dataset.version,
        context_revision=query.context_revision,
        match=None,
        reasons=tuple(
            sorted(
                {reason for _, applicability in evaluated for reason in applicability.reasons},
                key=lambda reason: reason.value,
            )
        ),
        candidate_record_ids=tuple(sorted(record.record_id for record in candidates)),
    )


def _comparison_result(
    *,
    status: ComparisonStatus,
    lookup: LookupResult,
    context_revision: str | None,
    record: ReferenceRecord | None,
    source: SourceRecord | None,
    relation: ComparisonRelation | None,
) -> ComparisonResult:
    return ComparisonResult(
        status=status,
        dataset_version=lookup.dataset_version,
        context_revision=context_revision,
        record_id=record.record_id if record is not None else None,
        reference_type=record.reference_type if record is not None else None,
        source_key=source.source_key if source is not None else None,
        source_version=source.version_label if source is not None else None,
        reference_value=record.value if record is not None else None,
        reference_value_min=record.value_min if record is not None else None,
        reference_value_max=record.value_max if record is not None else None,
        unit=record.unit if record is not None else None,
        exposure_basis=record.exposure_basis if record is not None else None,
        relation=relation,
    )


def compare_amount_to_reference(
    amount: ComputedAmount,
    lookup: LookupResult,
    *,
    context_revision: str | None = None,
) -> ComparisonResult:
    if context_revision is not None and not context_revision.strip():
        raise ReferenceDataError("context_revision must not be blank")
    if context_revision is not None and context_revision != lookup.context_revision:
        raise ReferenceDataError(
            "context_revision does not match the immutable lookup applicability context"
        )

    bound_context_revision = lookup.context_revision

    if lookup.status is not LookupStatus.MATCHED or lookup.match is None:
        return _comparison_result(
            status=ComparisonStatus.LOOKUP_NOT_MATCHED,
            lookup=lookup,
            context_revision=bound_context_revision,
            record=None,
            source=None,
            relation=None,
        )

    record = lookup.match.record
    source = lookup.match.source

    if record.value is None and record.value_min is None:
        return _comparison_result(
            status=ComparisonStatus.NO_NUMERIC_REFERENCE,
            lookup=lookup,
            context_revision=bound_context_revision,
            record=record,
            source=source,
            relation=None,
        )

    if record.value_semantics is ValueSemantics.INCREMENT:
        return _comparison_result(
            status=ComparisonStatus.INCREMENT_REQUIRES_BASE,
            lookup=lookup,
            context_revision=bound_context_revision,
            record=record,
            source=source,
            relation=None,
        )
    if record.value_semantics is ValueSemantics.RANGE_INCREMENT:
        return _comparison_result(
            status=ComparisonStatus.NON_SCALAR_REFERENCE,
            lookup=lookup,
            context_revision=bound_context_revision,
            record=record,
            source=source,
            relation=None,
        )
    if record.value is None or record.unit is None:
        raise ReferenceDataError("scalar reference unexpectedly lacks value or unit")

    if (
        amount.quantity_basis is not QuantityBasis.PER_DAY
        or amount.subject_kind is not record.subject_kind
        or amount.subject_id != record.subject_id
        or amount.amount_basis is not record.amount_basis
        or amount.equivalence_basis != record.equivalence_basis
    ):
        return _comparison_result(
            status=ComparisonStatus.INPUT_NOT_COMPARABLE,
            lookup=lookup,
            context_revision=bound_context_revision,
            record=record,
            source=source,
            relation=None,
        )

    if (
        unit_dimension(amount.unit) is UnitDimension.MASS
        and unit_dimension(record.unit) is UnitDimension.MASS
    ):
        comparable_value = convert_mass(amount.value, amount.unit, record.unit)
    elif amount.unit is record.unit:
        comparable_value = amount.value
    else:
        return _comparison_result(
            status=ComparisonStatus.INPUT_NOT_COMPARABLE,
            lookup=lookup,
            context_revision=bound_context_revision,
            record=record,
            source=source,
            relation=None,
        )

    if comparable_value < record.value:
        relation = ComparisonRelation.BELOW
    elif comparable_value > record.value:
        relation = ComparisonRelation.ABOVE
    else:
        relation = ComparisonRelation.EQUAL

    return _comparison_result(
        status=ComparisonStatus.COMPARABLE,
        lookup=lookup,
        context_revision=bound_context_revision,
        record=record,
        source=source,
        relation=relation,
    )


def comparison_is_stale(
    result: ComparisonResult,
    dataset: ReferenceDataset,
    *,
    context_revision: str | None,
) -> bool:
    if result.dataset_version != dataset.version:
        return True
    if result.context_revision != context_revision:
        return True
    if result.record_id is None:
        return False
    record = dataset.get_record(result.record_id)
    if record is None or record.lifecycle is not ReferenceLifecycle.ACTIVE:
        return True
    source = dataset.get_source(record.source_key)
    return source is None or source.lifecycle is not SourceLifecycle.ACTIVE


DATASET_VERSION: Final = "eu-efsa-mvp-2026-09-20.v1"


def _source(
    source_key: str,
    authority: Authority,
    family: SourceFamily,
    stable_id_kind: StableIdKind,
    stable_id: str,
    title: str,
    source_url: str,
    *,
    adopted_date: str | None,
    published_date: str | None,
    amended_date: str | None = None,
    version_label: str,
    retrieved_at: str = "2026-09-19",
    provenance_note: str = "",
) -> SourceRecord:
    return SourceRecord(
        source_key=source_key,
        authority=authority,
        jurisdiction=Jurisdiction.EU,
        family=family,
        stable_id_kind=stable_id_kind,
        stable_id=stable_id,
        title=title,
        source_url=source_url,
        adopted_date=adopted_date,
        published_date=published_date,
        amended_date=amended_date,
        version_label=version_label,
        retrieved_at=retrieved_at,
        provenance_note=provenance_note,
    )


SOURCES: Final[tuple[SourceRecord, ...]] = (
    _source(
        "EU-NRV",
        Authority.EU_LEGISLATOR,
        SourceFamily.EU_LAW,
        StableIdKind.CELEX,
        "32011R1169",
        "Regulation (EU) No 1169/2011, Annex XIII Part A",
        "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32011R1169",
        adopted_date=None,
        published_date=None,
        version_label="current consolidated act checked 2026-09-19",
    ),
    _source(
        "VD-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2016.4547",
        "Dietary reference values for vitamin D",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2016.4547",
        adopted_date="2016-06-29",
        published_date="2016-10-28",
        version_label="EFSA Journal 2016;14(10):4547",
    ),
    _source(
        "VC-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2013.3418",
        "Dietary Reference Values for vitamin C",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2013.3418",
        adopted_date="2013-10-10",
        published_date="2013-11-04",
        version_label="EFSA Journal 2013;11(11):3418",
    ),
    _source(
        "MG-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2015.4186",
        "Dietary Reference Values for magnesium",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2015.4186",
        adopted_date="2015-06-29",
        published_date="2015-07-27",
        version_label="EFSA Journal 2015;13(7):4186",
    ),
    _source(
        "ZN-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2014.3844",
        "Dietary Reference Values for zinc",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2014.3844",
        adopted_date="2014-09-19",
        published_date="2014-10-10",
        version_label="EFSA Journal 2014;12(10):3844",
    ),
    _source(
        "SE-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2014.3846",
        "Dietary Reference Values for selenium",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2014.3846",
        adopted_date="2014-09-19",
        published_date="2014-10-10",
        version_label="EFSA Journal 2014;12(10):3846",
    ),
    _source(
        "B6-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2016.4485",
        "Dietary Reference Values for vitamin B6",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2016.4485",
        adopted_date="2016-04-21",
        published_date="2016-06-24",
        version_label="EFSA Journal 2016;14(6):4485",
    ),
    _source(
        "B12-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2015.4150",
        "Dietary Reference Values for cobalamin (vitamin B12)",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2015.4150",
        adopted_date="2015-06-11",
        published_date="2015-07-09",
        version_label="EFSA Journal 2015;13(7):4150",
    ),
    _source(
        "FOL-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2014.3893",
        "Dietary Reference Values for folate",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2014.3893",
        adopted_date="2014-10-30",
        published_date="2014-11-20",
        version_label="EFSA Journal 2014;12(11):3893",
    ),
    _source(
        "FE-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2015.4254",
        "Dietary Reference Values for iron",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2015.4254",
        adopted_date="2015-09-23",
        published_date="2015-10-21",
        version_label="EFSA Journal 2015;13(10):4254",
    ),
    _source(
        "CA-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2015.4101",
        "Dietary Reference Values for calcium",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2015.4101",
        adopted_date="2015-04-23",
        published_date="2015-05-27",
        version_label="EFSA Journal 2015;13(5):4101",
    ),
    _source(
        "O3-DRV",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_DRV,
        StableIdKind.DOI,
        "10.2903/j.efsa.2010.1461",
        "Dietary Reference Values for fats, including EPA/DHA",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2010.1461",
        adopted_date="2009-12-04",
        published_date="2010-03-25",
        version_label="EFSA Journal 2010;8(3):1461",
    ),
    _source(
        "VD-UL",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_SAFETY,
        StableIdKind.DOI,
        "10.2903/j.efsa.2023.8145",
        "Tolerable upper intake level for vitamin D",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2023.8145",
        adopted_date="2023-07-05",
        published_date="2023-08-08",
        version_label="EFSA Journal 2023;21(8):8145",
    ),
    _source(
        "VC-UL",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_SAFETY,
        StableIdKind.DOI,
        "10.2903/j.efsa.2004.59",
        "Tolerable upper intake level assessment for vitamin C",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2004.59",
        adopted_date="2004-04-28",
        published_date="2004-05-19",
        version_label="EFSA Journal 2004;59",
    ),
    _source(
        "MG-UL",
        Authority.SCF,
        SourceFamily.SCF_SAFETY,
        StableIdKind.OFFICIAL_DOCUMENT_ID,
        "SCF/CS/NUT/UPPLEV/54 Final",
        "Opinion on the Tolerable Upper Intake Level of Magnesium",
        "https://www.efsa.europa.eu/sites/default/files/2024-05/ul-summary-report.pdf",
        adopted_date="2001-09-26",
        published_date="2001-10-11",
        version_label="SCF final; retained in EFSA UL Summary Version 11 (2025-08)",
        provenance_note=(
            "KIR-127 did not capture an original SCF URL; the current EFSA UL "
            "summary is used as the non-invented online locator."
        ),
    ),
    _source(
        "ZN-UL",
        Authority.SCF,
        SourceFamily.SCF_SAFETY,
        StableIdKind.OFFICIAL_DOCUMENT_ID,
        "SCF/CS/NUT/UPPLEV/62 Final",
        "Opinion on the Tolerable Upper Intake Level of Zinc",
        "https://www.efsa.europa.eu/sites/default/files/2024-05/ul-summary-report.pdf",
        adopted_date="2003-03-05",
        published_date="2003-03-19",
        version_label="SCF final; retained in EFSA UL Summary Version 11 (2025-08)",
        provenance_note=(
            "KIR-127 did not capture an original SCF URL; the current EFSA UL "
            "summary is used as the non-invented online locator."
        ),
    ),
    _source(
        "SE-UL",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_SAFETY,
        StableIdKind.DOI,
        "10.2903/j.efsa.2023.7704",
        "Tolerable upper intake level for selenium",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2023.7704",
        adopted_date="2022-11-24",
        published_date="2023-01-20",
        version_label="EFSA Journal 2023;21(1):7704",
        provenance_note="Supersedes the older SCF adult 300 ug/day value.",
    ),
    _source(
        "B6-UL",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_SAFETY,
        StableIdKind.DOI,
        "10.2903/j.efsa.2023.8006",
        "Tolerable upper intake level for vitamin B6",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2023.8006",
        adopted_date="2023-03-29",
        published_date="2023-05-17",
        version_label="EFSA Journal 2023;21(5):8006",
        provenance_note=(
            "The established adult UL is 12 mg/day; 12.5 mg/day is an "
            "intermediate derivation and is not a dataset value."
        ),
    ),
    _source(
        "B12-UL",
        Authority.SCF,
        SourceFamily.SCF_SAFETY,
        StableIdKind.OFFICIAL_DOCUMENT_ID,
        "SCF/CS/NUT/UPPLEV/42 Final",
        "Tolerable Upper Intake Level of Vitamin B12",
        "https://food.ec.europa.eu/system/files/2020-12/sci-com_scf_out80d_en.pdf",
        adopted_date="2000-10-19",
        published_date="2000-11-28",
        version_label="SCF final; status retained in EFSA UL Summary Version 11 (2025-08)",
    ),
    _source(
        "FOL-UL",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_SAFETY,
        StableIdKind.DOI,
        "10.2903/j.efsa.2023.8353",
        "Tolerable upper intake level for folate",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2023.8353",
        adopted_date="2023-09-27",
        published_date="2023-11-13",
        amended_date="2024-11-21",
        version_label="EFSA Journal 2023;21(11):8353; amended 2024-11-21",
    ),
    _source(
        "FE-SAFE",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_SAFETY,
        StableIdKind.DOI,
        "10.2903/j.efsa.2024.8819",
        "Safety assessment for iron",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2024.8819",
        adopted_date="2024-04-30",
        published_date="2024-06-12",
        version_label="EFSA Journal 2024;22(6):8819",
    ),
    _source(
        "CA-UL",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_SAFETY,
        StableIdKind.DOI,
        "10.2903/j.efsa.2012.2814",
        "Tolerable upper intake level of calcium",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2012.2814",
        adopted_date="2012-06-26",
        published_date="2012-07-27",
        version_label="EFSA Journal 2012;10(7):2814",
    ),
    _source(
        "O3-UL",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_SAFETY,
        StableIdKind.DOI,
        "10.2903/j.efsa.2012.2815",
        "Safety of long-chain n-3 polyunsaturated fatty acids",
        "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2012.2815",
        adopted_date="2012-06-26",
        published_date="2012-07-27",
        version_label="EFSA Journal 2012;10(7):2815",
    ),
    _source(
        "O3-DHA-SAFE-2026",
        Authority.EFSA_NDA,
        SourceFamily.EFSA_SAFETY,
        StableIdKind.DOI,
        "10.2903/j.efsa.2026.9858",
        (
            "Scientific Opinion on the tolerable upper intake level for supplemental "
            "docosahexaenoic acid"
        ),
        "https://doi.org/10.2903/j.efsa.2026.9858",
        adopted_date="2025-12-15",
        published_date="2026-01-14",
        version_label="EFSA Journal 2026;24(1):e9858",
        retrieved_at="2026-09-20",
        provenance_note=(
            "Narrow current-source precedence applies only to the source-defined "
            "supplemental DHA-alone/mostly-DHA exposure."
        ),
    ),
)


def _pop(
    age_min_months: int | None = None,
    age_max_months_exclusive: int | None = None,
    *,
    sex: SexApplicability = SexApplicability.ALL,
    life_stage: LifeStage | None = None,
    physiological_condition: PhysiologicalCondition | None = None,
) -> PopulationCriteria:
    return PopulationCriteria(
        age_min_months=age_min_months,
        age_max_months_exclusive=age_max_months_exclusive,
        sex=sex,
        life_stage=life_stage,
        physiological_condition=physiological_condition,
    )


def _numeric(
    record_id: str,
    domain: ReferenceDomain,
    reference_type: ReferenceType,
    authority: Authority,
    substance_key: str,
    subject_id: str,
    value: str,
    unit: Unit,
    population: PopulationCriteria,
    source_key: str,
    source_locator: str,
    *,
    amount_basis: AmountBasis = AmountBasis.ANALYTE,
    equivalence_basis: str | None = None,
    value_semantics: ValueSemantics = ValueSemantics.ABSOLUTE,
    exposure_basis: ExposureBasis = ExposureBasis.DIETARY_TOTAL,
    exposure_match_required: bool = True,
    status: ReferenceStatus = ReferenceStatus.ESTABLISHED_NUMERIC,
    selection_priority: int = 0,
    base_reference_id: str | None = None,
    dietary_phytate_mg_per_day: str | None = None,
    requires_minimal_cutaneous_synthesis: bool = False,
    allowed_source_classes: tuple[SourceClass, ...] = (),
    allowed_dha_forms: tuple[DHAForm, ...] = (),
    epa_dha_ratio_max_exclusive: str | None = None,
    requires_epa_and_dha_amounts: bool = False,
    excludes_background_dietary_dha: bool = False,
    excludes_medical_supervision: bool = False,
    provenance_note: str = "",
) -> ReferenceRecord:
    return ReferenceRecord(
        record_id=record_id,
        dataset_version=DATASET_VERSION,
        domain=domain,
        reference_type=reference_type,
        authority=authority,
        jurisdiction=Jurisdiction.EU,
        substance_key=substance_key,
        subject_kind=SubjectKind.ANALYTE,
        subject_id=subject_id,
        amount_basis=amount_basis,
        equivalence_basis=equivalence_basis,
        population=population,
        value=Decimal(value),
        value_min=None,
        value_max=None,
        unit=unit,
        quantity_basis=QuantityBasis.PER_DAY,
        value_semantics=value_semantics,
        exposure_basis=exposure_basis,
        exposure_match_required=exposure_match_required,
        status=status,
        source_key=source_key,
        source_locator=source_locator,
        selection_priority=selection_priority,
        base_reference_id=base_reference_id,
        dietary_phytate_mg_per_day=(
            Decimal(dietary_phytate_mg_per_day) if dietary_phytate_mg_per_day is not None else None
        ),
        requires_minimal_cutaneous_synthesis=requires_minimal_cutaneous_synthesis,
        allowed_source_classes=allowed_source_classes,
        allowed_dha_forms=allowed_dha_forms,
        epa_dha_ratio_max_exclusive=(
            Decimal(epa_dha_ratio_max_exclusive)
            if epa_dha_ratio_max_exclusive is not None
            else None
        ),
        requires_epa_and_dha_amounts=requires_epa_and_dha_amounts,
        excludes_background_dietary_dha=excludes_background_dietary_dha,
        excludes_medical_supervision=excludes_medical_supervision,
        provenance_note=provenance_note,
    )


def _range_numeric(
    record_id: str,
    domain: ReferenceDomain,
    reference_type: ReferenceType,
    authority: Authority,
    substance_key: str,
    subject_id: str,
    value_min: str,
    value_max: str,
    unit: Unit,
    population: PopulationCriteria,
    source_key: str,
    source_locator: str,
    *,
    value_semantics: ValueSemantics,
    exposure_basis: ExposureBasis,
    base_reference_id: str,
) -> ReferenceRecord:
    return ReferenceRecord(
        record_id=record_id,
        dataset_version=DATASET_VERSION,
        domain=domain,
        reference_type=reference_type,
        authority=authority,
        jurisdiction=Jurisdiction.EU,
        substance_key=substance_key,
        subject_kind=SubjectKind.ANALYTE,
        subject_id=subject_id,
        amount_basis=AmountBasis.ANALYTE,
        equivalence_basis=None,
        population=population,
        value=None,
        value_min=Decimal(value_min),
        value_max=Decimal(value_max),
        unit=unit,
        quantity_basis=QuantityBasis.PER_DAY,
        value_semantics=value_semantics,
        exposure_basis=exposure_basis,
        exposure_match_required=True,
        status=ReferenceStatus.ESTABLISHED_NUMERIC,
        source_key=source_key,
        source_locator=source_locator,
        base_reference_id=base_reference_id,
    )


def _no_value(
    record_id: str,
    domain: ReferenceDomain,
    reference_type: ReferenceType,
    authority: Authority,
    substance_key: str,
    subject_id: str,
    population: PopulationCriteria,
    source_key: str,
    source_locator: str,
    status: ReferenceStatus,
    *,
    amount_basis: AmountBasis = AmountBasis.ANALYTE,
    equivalence_basis: str | None = None,
    exposure_basis: ExposureBasis = ExposureBasis.SOURCE_NATIVE_UNSPECIFIED,
    exposure_match_required: bool = False,
    selection_priority: int = 0,
    allowed_source_classes: tuple[SourceClass, ...] = (),
    allowed_dha_forms: tuple[DHAForm, ...] = (),
    epa_dha_ratio_max_exclusive: str | None = None,
    requires_epa_and_dha_amounts: bool = False,
    excludes_background_dietary_dha: bool = False,
    provenance_note: str = "",
) -> ReferenceRecord:
    return ReferenceRecord(
        record_id=record_id,
        dataset_version=DATASET_VERSION,
        domain=domain,
        reference_type=reference_type,
        authority=authority,
        jurisdiction=Jurisdiction.EU,
        substance_key=substance_key,
        subject_kind=SubjectKind.ANALYTE,
        subject_id=subject_id,
        amount_basis=amount_basis,
        equivalence_basis=equivalence_basis,
        population=population,
        value=None,
        value_min=None,
        value_max=None,
        unit=None,
        quantity_basis=QuantityBasis.PER_DAY,
        value_semantics=ValueSemantics.ABSOLUTE,
        exposure_basis=exposure_basis,
        exposure_match_required=exposure_match_required,
        status=status,
        source_key=source_key,
        source_locator=source_locator,
        selection_priority=selection_priority,
        allowed_source_classes=allowed_source_classes,
        allowed_dha_forms=allowed_dha_forms,
        epa_dha_ratio_max_exclusive=(
            Decimal(epa_dha_ratio_max_exclusive)
            if epa_dha_ratio_max_exclusive is not None
            else None
        ),
        requires_epa_and_dha_amounts=requires_epa_and_dha_amounts,
        excludes_background_dietary_dha=excludes_background_dietary_dha,
        provenance_note=provenance_note,
    )


def _build_records() -> tuple[ReferenceRecord, ...]:
    r: list[ReferenceRecord] = []

    # EU Annex XIII adult labelling NRVs.
    nrv_specs = (
        ("vitamin_d", "analyte:vitamin-d", "5", Unit.MICROGRAM),
        ("vitamin_c", "analyte:vitamin-c", "80", Unit.MILLIGRAM),
        ("magnesium", "analyte:magnesium", "375", Unit.MILLIGRAM),
        ("zinc", "analyte:zinc", "10", Unit.MILLIGRAM),
        ("selenium", "analyte:selenium", "55", Unit.MICROGRAM),
        ("vitamin_b6", "analyte:vitamin-b6", "1.4", Unit.MILLIGRAM),
        ("vitamin_b12", "analyte:vitamin-b12", "2.5", Unit.MICROGRAM),
        ("folic_acid", "analyte:folic-acid", "200", Unit.MICROGRAM),
        ("iron", "analyte:iron", "14", Unit.MILLIGRAM),
        ("calcium", "analyte:calcium", "800", Unit.MILLIGRAM),
    )
    for key, subject_id, value, unit in nrv_specs:
        r.append(
            _numeric(
                f"eu-nrv-{key}-adult",
                ReferenceDomain.EU_LABELLING,
                ReferenceType.NRV,
                Authority.EU_LEGISLATOR,
                key,
                subject_id,
                value,
                unit,
                _pop(216, None),
                "EU-NRV",
                "Annex XIII Part A adult vitamin/mineral reference intakes",
                exposure_basis=ExposureBasis.LABELLING_REFERENCE,
            )
        )
    r.append(
        _no_value(
            "eu-nrv-epa-plus-dha-not-established",
            ReferenceDomain.EU_LABELLING,
            ReferenceType.NRV,
            Authority.EU_LEGISLATOR,
            "epa_plus_dha",
            "analyte:epa-plus-dha",
            _pop(216, None),
            "EU-NRV",
            "Annex XIII Part A contains no EPA/DHA NRV",
            ReferenceStatus.NOT_ESTABLISHED,
            exposure_basis=ExposureBasis.LABELLING_REFERENCE,
            exposure_match_required=True,
        )
    )

    # Vitamin D AI and UL.
    for record_id, minimum, maximum, life_stage, value in (
        ("vd-ai-7-11m", 7, 12, None, "10"),
        ("vd-ai-1-17y", 12, 216, None, "15"),
        ("vd-ai-adult", 216, None, LifeStage.GENERAL, "15"),
        ("vd-ai-pregnancy", 216, None, LifeStage.PREGNANCY, "15"),
        ("vd-ai-lactation", 216, None, LifeStage.LACTATION, "15"),
    ):
        r.append(
            _numeric(
                record_id,
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ReferenceType.AI,
                Authority.EFSA_NDA,
                "vitamin_d",
                "analyte:vitamin-d",
                value,
                Unit.MICROGRAM,
                _pop(minimum, maximum, life_stage=life_stage),
                "VD-DRV",
                "KIR-127 §4.1 vitamin D AI population table",
                requires_minimal_cutaneous_synthesis=True,
            )
        )
    for record_id, minimum, maximum, value in (
        ("vd-ul-0-6m", 0, 7, "25"),
        ("vd-ul-7-11m", 7, 12, "35"),
        ("vd-ul-1-10y", 12, 132, "50"),
        ("vd-ul-11-17y", 132, 216, "100"),
        ("vd-ul-adult", 216, None, "100"),
    ):
        r.append(
            _numeric(
                record_id,
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.EFSA_NDA,
                "vitamin_d",
                "analyte:vitamin-d",
                value,
                Unit.MICROGRAM,
                _pop(minimum, maximum),
                "VD-UL",
                "KIR-127 §4.1 vitamin D UL population table",
                amount_basis=AmountBasis.EQUIVALENT,
                equivalence_basis="EFSA 2023 vitamin D equivalent (VDE)",
                exposure_basis=ExposureBasis.TOTAL_INTAKE,
            )
        )

    # Vitamin C.
    vc_pairs = (
        ("vc-1-3y", 12, 48, SexApplicability.ALL, "15", "20"),
        ("vc-4-6y", 48, 84, SexApplicability.ALL, "25", "30"),
        ("vc-7-10y", 84, 132, SexApplicability.ALL, "40", "45"),
        ("vc-11-14y", 132, 180, SexApplicability.ALL, "60", "70"),
        ("vc-15-17y-male", 180, 216, SexApplicability.MALE, "85", "100"),
        ("vc-15-17y-female", 180, 216, SexApplicability.FEMALE, "75", "90"),
        ("vc-adult-male", 216, None, SexApplicability.MALE, "90", "110"),
        ("vc-adult-female", 216, None, SexApplicability.FEMALE, "80", "95"),
    )
    r.append(
        _numeric(
            "vc-pri-7-11m",
            ReferenceDomain.EFSA_DIETARY_REFERENCE,
            ReferenceType.PRI,
            Authority.EFSA_NDA,
            "vitamin_c",
            "analyte:vitamin-c",
            "20",
            Unit.MILLIGRAM,
            _pop(7, 12),
            "VC-DRV",
            "KIR-127 §4.2 vitamin C population table",
        )
    )
    for prefix, minimum, maximum, sex, ar, pri in vc_pairs:
        population = _pop(
            minimum,
            maximum,
            sex=sex,
            life_stage=LifeStage.GENERAL if minimum == 216 else None,
        )
        r.extend(
            (
                _numeric(
                    f"{prefix}-ar",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.AR,
                    Authority.EFSA_NDA,
                    "vitamin_c",
                    "analyte:vitamin-c",
                    ar,
                    Unit.MILLIGRAM,
                    population,
                    "VC-DRV",
                    "KIR-127 §4.2 vitamin C AR/PRI table",
                ),
                _numeric(
                    f"{prefix}-pri",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.PRI,
                    Authority.EFSA_NDA,
                    "vitamin_c",
                    "analyte:vitamin-c",
                    pri,
                    Unit.MILLIGRAM,
                    population,
                    "VC-DRV",
                    "KIR-127 §4.2 vitamin C AR/PRI table",
                ),
            )
        )
    r.extend(
        (
            _numeric(
                "vc-pregnancy-pri-increment",
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ReferenceType.PRI,
                Authority.EFSA_NDA,
                "vitamin_c",
                "analyte:vitamin-c",
                "10",
                Unit.MILLIGRAM,
                _pop(216, None, life_stage=LifeStage.PREGNANCY),
                "VC-DRV",
                "KIR-127 §4.2 pregnancy PRI increment",
                value_semantics=ValueSemantics.INCREMENT,
                base_reference_id="vc-adult-female-pri",
            ),
            _numeric(
                "vc-lactation-pri-increment",
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ReferenceType.PRI,
                Authority.EFSA_NDA,
                "vitamin_c",
                "analyte:vitamin-c",
                "60",
                Unit.MILLIGRAM,
                _pop(216, None, life_stage=LifeStage.LACTATION),
                "VC-DRV",
                "KIR-127 §4.2 final lactation PRI increment",
                value_semantics=ValueSemantics.INCREMENT,
                base_reference_id="vc-adult-female-pri",
                provenance_note="Final opinion value; draft +75 mg/day is non-controlling.",
            ),
            _no_value(
                "vc-ul-no-ul",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.EFSA_NDA,
                "vitamin_c",
                "analyte:vitamin-c",
                _pop(),
                "VC-UL",
                "KIR-127 §4.2 safety state",
                ReferenceStatus.NO_UL_INSUFFICIENT_DATA,
            ),
        )
    )

    # Magnesium.
    mg_ai = (
        ("mg-ai-7-11m", 7, 12, SexApplicability.ALL, None, "80"),
        ("mg-ai-1-lt3y", 12, 36, SexApplicability.ALL, None, "170"),
        ("mg-ai-3-lt10y", 36, 120, SexApplicability.ALL, None, "230"),
        ("mg-ai-10-lt18y-male", 120, 216, SexApplicability.MALE, None, "300"),
        ("mg-ai-10-lt18y-female", 120, 216, SexApplicability.FEMALE, None, "250"),
        ("mg-ai-adult-male", 216, None, SexApplicability.MALE, LifeStage.GENERAL, "350"),
        ("mg-ai-adult-female", 216, None, SexApplicability.FEMALE, None, "300"),
    )
    for record_id, minimum, maximum, sex, stage, value in mg_ai:
        r.append(
            _numeric(
                record_id,
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ReferenceType.AI,
                Authority.EFSA_NDA,
                "magnesium",
                "analyte:magnesium",
                value,
                Unit.MILLIGRAM,
                _pop(minimum, maximum, sex=sex, life_stage=stage),
                "MG-DRV",
                "KIR-127 §4.3 magnesium AI table",
            )
        )
    r.extend(
        (
            _no_value(
                "mg-ul-1-3y-not-established",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.SCF,
                "magnesium",
                "analyte:magnesium",
                _pop(12, 48),
                "MG-UL",
                "KIR-127 §4.3 magnesium UL table",
                ReferenceStatus.NO_UL_INSUFFICIENT_DATA,
                exposure_basis=ExposureBasis.MAGNESIUM_SUPPLEMENTAL_WATER_OR_ADDED,
                exposure_match_required=True,
            ),
            _numeric(
                "mg-ul-4y-plus",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.SCF,
                "magnesium",
                "analyte:magnesium",
                "250",
                Unit.MILLIGRAM,
                _pop(48, None),
                "MG-UL",
                "KIR-127 §4.3 magnesium UL scope",
                exposure_basis=ExposureBasis.MAGNESIUM_SUPPLEMENTAL_WATER_OR_ADDED,
                provenance_note=(
                    "Applies to readily dissociable Mg salts/compounds such as "
                    "MgO in supplements, water, or added food; excludes natural foods."
                ),
            ),
        )
    )

    # Zinc DRV and UL.
    zinc_child = (
        ("7-11m", 7, 12, SexApplicability.ALL, "2.4", "2.9"),
        ("1-3y", 12, 48, SexApplicability.ALL, "3.6", "4.3"),
        ("4-6y", 48, 84, SexApplicability.ALL, "4.6", "5.5"),
        ("7-10y", 84, 132, SexApplicability.ALL, "6.2", "7.4"),
        ("11-14y", 132, 180, SexApplicability.ALL, "8.9", "10.7"),
        ("15-17y-male", 180, 216, SexApplicability.MALE, "11.8", "14.2"),
        ("15-17y-female", 180, 216, SexApplicability.FEMALE, "9.9", "11.9"),
    )
    for suffix, minimum, maximum, sex, ar, pri in zinc_child:
        population = _pop(minimum, maximum, sex=sex)
        r.extend(
            (
                _numeric(
                    f"zn-ar-{suffix}",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.AR,
                    Authority.EFSA_NDA,
                    "zinc",
                    "analyte:zinc",
                    ar,
                    Unit.MILLIGRAM,
                    population,
                    "ZN-DRV",
                    "KIR-127 §4.4 pediatric zinc AR table",
                ),
                _numeric(
                    f"zn-pri-{suffix}",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.PRI,
                    Authority.EFSA_NDA,
                    "zinc",
                    "analyte:zinc",
                    pri,
                    Unit.MILLIGRAM,
                    population,
                    "ZN-DRV",
                    "KIR-127 §4.4 pediatric zinc PRI table",
                ),
            )
        )
    phytate_rows = (
        ("300", "6.2", "7.5", "7.5", "9.4"),
        ("600", "7.6", "9.3", "9.3", "11.7"),
        ("900", "8.9", "11.0", "11.0", "14.0"),
        ("1200", "10.2", "12.7", "12.7", "16.3"),
    )
    for phytate, female_ar, female_pri, male_ar, male_pri in phytate_rows:
        for sex, ar, pri, sex_name in (
            (SexApplicability.FEMALE, female_ar, female_pri, "female"),
            (SexApplicability.MALE, male_ar, male_pri, "male"),
        ):
            pop = _pop(216, None, sex=sex, life_stage=LifeStage.GENERAL)
            r.extend(
                (
                    _numeric(
                        f"zn-ar-adult-{sex_name}-phytate-{phytate}",
                        ReferenceDomain.EFSA_DIETARY_REFERENCE,
                        ReferenceType.AR,
                        Authority.EFSA_NDA,
                        "zinc",
                        "analyte:zinc",
                        ar,
                        Unit.MILLIGRAM,
                        pop,
                        "ZN-DRV",
                        "KIR-127 §4.4 adult zinc phytate-conditioned table",
                        status=ReferenceStatus.CONDITIONAL_NUMERIC,
                        dietary_phytate_mg_per_day=phytate,
                    ),
                    _numeric(
                        f"zn-pri-adult-{sex_name}-phytate-{phytate}",
                        ReferenceDomain.EFSA_DIETARY_REFERENCE,
                        ReferenceType.PRI,
                        Authority.EFSA_NDA,
                        "zinc",
                        "analyte:zinc",
                        pri,
                        Unit.MILLIGRAM,
                        pop,
                        "ZN-DRV",
                        "KIR-127 §4.4 adult zinc phytate-conditioned table",
                        status=ReferenceStatus.CONDITIONAL_NUMERIC,
                        dietary_phytate_mg_per_day=phytate,
                    ),
                )
            )
        female_base = f"zn-pri-adult-female-phytate-{phytate}"
        r.extend(
            (
                _numeric(
                    f"zn-pri-pregnancy-increment-phytate-{phytate}",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.PRI,
                    Authority.EFSA_NDA,
                    "zinc",
                    "analyte:zinc",
                    "1.6",
                    Unit.MILLIGRAM,
                    _pop(216, None, sex=SexApplicability.FEMALE, life_stage=LifeStage.PREGNANCY),
                    "ZN-DRV",
                    "KIR-127 §4.4 pregnancy PRI increment",
                    value_semantics=ValueSemantics.INCREMENT,
                    base_reference_id=female_base,
                    status=ReferenceStatus.CONDITIONAL_NUMERIC,
                    dietary_phytate_mg_per_day=phytate,
                ),
                _numeric(
                    f"zn-pri-lactation-increment-phytate-{phytate}",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.PRI,
                    Authority.EFSA_NDA,
                    "zinc",
                    "analyte:zinc",
                    "2.9",
                    Unit.MILLIGRAM,
                    _pop(216, None, sex=SexApplicability.FEMALE, life_stage=LifeStage.LACTATION),
                    "ZN-DRV",
                    "KIR-127 §4.4 lactation PRI increment",
                    value_semantics=ValueSemantics.INCREMENT,
                    base_reference_id=female_base,
                    status=ReferenceStatus.CONDITIONAL_NUMERIC,
                    dietary_phytate_mg_per_day=phytate,
                ),
            )
        )
    r.append(
        _no_value(
            "zn-ul-infant-not-established",
            ReferenceDomain.EFSA_SAFETY,
            ReferenceType.UL,
            Authority.SCF,
            "zinc",
            "analyte:zinc",
            _pop(0, 12),
            "ZN-UL",
            "KIR-127 §4.4 current UL table has no infant numeric UL",
            ReferenceStatus.NOT_ESTABLISHED,
            exposure_basis=ExposureBasis.TOTAL_INTAKE,
            exposure_match_required=True,
        )
    )
    for suffix, minimum, maximum, value in (
        ("1-3y", 12, 48, "7"),
        ("4-6y", 48, 84, "10"),
        ("7-10y", 84, 132, "13"),
        ("11-14y", 132, 180, "18"),
        ("15-17y", 180, 216, "22"),
        ("adult", 216, None, "25"),
    ):
        r.append(
            _numeric(
                f"zn-ul-{suffix}",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.SCF,
                "zinc",
                "analyte:zinc",
                value,
                Unit.MILLIGRAM,
                _pop(minimum, maximum),
                "ZN-UL",
                "KIR-127 §4.4 zinc UL table",
                exposure_basis=ExposureBasis.TOTAL_INTAKE,
            )
        )

    # Selenium AI and current UL.
    for suffix, minimum, maximum, stage, value in (
        ("7-11m", 7, 12, None, "15"),
        ("1-3y", 12, 48, None, "15"),
        ("4-6y", 48, 84, None, "20"),
        ("7-10y", 84, 132, None, "35"),
        ("11-14y", 132, 180, None, "55"),
        ("15-17y", 180, 216, None, "70"),
        ("adult", 216, None, LifeStage.GENERAL, "70"),
        ("pregnancy", 216, None, LifeStage.PREGNANCY, "70"),
        ("lactation", 216, None, LifeStage.LACTATION, "85"),
    ):
        r.append(
            _numeric(
                f"se-ai-{suffix}",
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ReferenceType.AI,
                Authority.EFSA_NDA,
                "selenium",
                "analyte:selenium",
                value,
                Unit.MICROGRAM,
                _pop(minimum, maximum, life_stage=stage),
                "SE-DRV",
                "KIR-127 §4.5 selenium AI table",
            )
        )
    for suffix, minimum, maximum, value in (
        ("4-6m", 4, 7, "45"),
        ("7-11m", 7, 12, "55"),
        ("1-3y", 12, 48, "70"),
        ("4-6y", 48, 84, "95"),
        ("7-10y", 84, 132, "130"),
        ("11-14y", 132, 180, "180"),
        ("15-17y", 180, 216, "230"),
        ("adult", 216, None, "255"),
    ):
        r.append(
            _numeric(
                f"se-ul-{suffix}",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.EFSA_NDA,
                "selenium",
                "analyte:selenium",
                value,
                Unit.MICROGRAM,
                _pop(minimum, maximum),
                "SE-UL",
                "KIR-127 §4.5 selenium UL table",
                exposure_basis=ExposureBasis.TOTAL_INTAKE,
                provenance_note=(
                    "Current 2023 EFSA value; adult 255 ug/day supersedes old SCF 300."
                ),
            )
        )

    # Vitamin B6.
    r.append(
        _numeric(
            "b6-ai-7-11m",
            ReferenceDomain.EFSA_DIETARY_REFERENCE,
            ReferenceType.AI,
            Authority.EFSA_NDA,
            "vitamin_b6",
            "analyte:vitamin-b6",
            "0.3",
            Unit.MILLIGRAM,
            _pop(7, 12),
            "B6-DRV",
            "KIR-127 §4.6 vitamin B6 table",
        )
    )
    b6_pairs = (
        ("1-3y", 12, 48, SexApplicability.ALL, None, "0.5", "0.6"),
        ("4-6y", 48, 84, SexApplicability.ALL, None, "0.6", "0.7"),
        ("7-10y", 84, 132, SexApplicability.ALL, None, "0.9", "1.0"),
        ("11-14y", 132, 180, SexApplicability.ALL, None, "1.2", "1.4"),
        ("15-17y-male", 180, 216, SexApplicability.MALE, None, "1.5", "1.7"),
        ("15-17y-female", 180, 216, SexApplicability.FEMALE, None, "1.3", "1.6"),
        ("adult-male", 216, None, SexApplicability.MALE, LifeStage.GENERAL, "1.5", "1.7"),
        ("adult-female", 216, None, SexApplicability.FEMALE, LifeStage.GENERAL, "1.3", "1.6"),
        ("pregnancy", 216, None, SexApplicability.FEMALE, LifeStage.PREGNANCY, "1.5", "1.8"),
        ("lactation", 216, None, SexApplicability.FEMALE, LifeStage.LACTATION, "1.4", "1.7"),
    )
    for suffix, minimum, maximum, sex, stage, ar, pri in b6_pairs:
        pop = _pop(minimum, maximum, sex=sex, life_stage=stage)
        r.extend(
            (
                _numeric(
                    f"b6-ar-{suffix}",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.AR,
                    Authority.EFSA_NDA,
                    "vitamin_b6",
                    "analyte:vitamin-b6",
                    ar,
                    Unit.MILLIGRAM,
                    pop,
                    "B6-DRV",
                    "KIR-127 §4.6 vitamin B6 AR/PRI table",
                ),
                _numeric(
                    f"b6-pri-{suffix}",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.PRI,
                    Authority.EFSA_NDA,
                    "vitamin_b6",
                    "analyte:vitamin-b6",
                    pri,
                    Unit.MILLIGRAM,
                    pop,
                    "B6-DRV",
                    "KIR-127 §4.6 vitamin B6 AR/PRI table",
                ),
            )
        )
    for suffix, minimum, maximum, value in (
        ("4-6m", 4, 7, "2.2"),
        ("7-11m", 7, 12, "2.5"),
        ("1-3y", 12, 48, "3.2"),
        ("4-6y", 48, 84, "4.5"),
        ("7-10y", 84, 132, "6.1"),
        ("11-14y", 132, 180, "8.6"),
        ("15-17y", 180, 216, "10.7"),
        ("adult", 216, None, "12"),
    ):
        r.append(
            _numeric(
                f"b6-ul-{suffix}",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.EFSA_NDA,
                "vitamin_b6",
                "analyte:vitamin-b6",
                value,
                Unit.MILLIGRAM,
                _pop(minimum, maximum),
                "B6-UL",
                "KIR-127 §4.6 final established B6 UL table",
                exposure_basis=ExposureBasis.TOTAL_INTAKE,
            )
        )

    # Vitamin B12.
    for suffix, minimum, maximum, stage, value in (
        ("7-11m", 7, 12, None, "1.5"),
        ("1-3y", 12, 48, None, "1.5"),
        ("4-6y", 48, 84, None, "1.5"),
        ("7-10y", 84, 132, None, "2.5"),
        ("11-14y", 132, 180, None, "3.5"),
        ("15-17y", 180, 216, None, "4"),
        ("adult", 216, None, LifeStage.GENERAL, "4"),
        ("pregnancy", 216, None, LifeStage.PREGNANCY, "4.5"),
        ("lactation", 216, None, LifeStage.LACTATION, "5"),
    ):
        r.append(
            _numeric(
                f"b12-ai-{suffix}",
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ReferenceType.AI,
                Authority.EFSA_NDA,
                "vitamin_b12",
                "analyte:vitamin-b12",
                value,
                Unit.MICROGRAM,
                _pop(minimum, maximum, life_stage=stage),
                "B12-DRV",
                "KIR-127 §4.7 vitamin B12 AI table",
            )
        )
    r.append(
        _no_value(
            "b12-ul-no-defined-adverse-effects",
            ReferenceDomain.EFSA_SAFETY,
            ReferenceType.UL,
            Authority.SCF,
            "vitamin_b12",
            "analyte:vitamin-b12",
            _pop(),
            "B12-UL",
            "KIR-127 §4.7 safety state",
            ReferenceStatus.NO_NUMERIC_UL_NO_DEFINED_ADVERSE_EFFECTS,
        )
    )

    # Folate DFE DRV and supplemental-folate UL.
    folate_drv = (
        ("7-11m-ai", ReferenceType.AI, 7, 12, None, "80"),
        ("1-3y-pri", ReferenceType.PRI, 12, 48, None, "120"),
        ("4-6y-pri", ReferenceType.PRI, 48, 84, None, "140"),
        ("7-10y-pri", ReferenceType.PRI, 84, 132, None, "200"),
        ("11-14y-pri", ReferenceType.PRI, 132, 180, None, "270"),
        ("15-17y-pri", ReferenceType.PRI, 180, 216, None, "330"),
        ("adult-ar", ReferenceType.AR, 216, None, LifeStage.GENERAL, "250"),
        ("adult-pri", ReferenceType.PRI, 216, None, LifeStage.GENERAL, "330"),
        ("pregnancy-ai", ReferenceType.AI, 216, None, LifeStage.PREGNANCY, "600"),
        ("lactation-pri", ReferenceType.PRI, 216, None, LifeStage.LACTATION, "500"),
    )
    for suffix, ref_type, minimum, maximum, stage, value in folate_drv:
        r.append(
            _numeric(
                f"folate-dfe-{suffix}",
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ref_type,
                Authority.EFSA_NDA,
                "folate_dfe",
                "analyte:folate-dfe",
                value,
                Unit.MICROGRAM,
                _pop(minimum, maximum, life_stage=stage),
                "FOL-DRV",
                "KIR-127 §4.8 folate DRV table",
                amount_basis=AmountBasis.EQUIVALENT,
                equivalence_basis="dietary_folate_equivalent",
            )
        )
    for suffix, minimum, maximum, value in (
        ("4-11m", 4, 12, "200"),
        ("1-3y", 12, 48, "200"),
        ("4-6y", 48, 84, "300"),
        ("7-10y", 84, 132, "400"),
        ("11-14y", 132, 180, "600"),
        ("15-17y", 180, 216, "800"),
        ("adult", 216, None, "1000"),
    ):
        r.append(
            _numeric(
                f"supplemental-folate-ul-{suffix}",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.EFSA_NDA,
                "supplemental_folate",
                "analyte:supplemental-folate",
                value,
                Unit.MICROGRAM,
                _pop(minimum, maximum),
                "FOL-UL",
                "KIR-127 §4.8 supplemental-form folate UL table",
                exposure_basis=ExposureBasis.FORTIFIED_AND_SUPPLEMENTAL_FOLATE,
                provenance_note=(
                    "Combined supplemental folate from folic acid, "
                    "(6S)-5-MTHF glucosamine and L-5-MTHF calcium salts under "
                    "authorised use; excludes naturally occurring food folate."
                ),
            )
        )

    # Iron DRV, explicit no-UL, and SAFE_LEVEL.
    iron_pairs = (
        ("7-11m", 7, 12, SexApplicability.ALL, None, None, "8", "11"),
        ("1-6y", 12, 84, SexApplicability.ALL, None, None, "5", "7"),
        ("7-11y", 84, 144, SexApplicability.ALL, None, None, "8", "11"),
        ("12-17y-male", 144, 216, SexApplicability.MALE, None, None, "8", "11"),
        ("12-17y-female", 144, 216, SexApplicability.FEMALE, None, None, "7", "13"),
        (
            "adult-men",
            216,
            None,
            SexApplicability.MALE,
            LifeStage.GENERAL,
            None,
            "6",
            "11",
        ),
        (
            "adult-postmenopausal",
            216,
            None,
            SexApplicability.FEMALE,
            LifeStage.GENERAL,
            PhysiologicalCondition.POSTMENOPAUSAL,
            "6",
            "11",
        ),
        (
            "adult-premenopausal",
            216,
            None,
            SexApplicability.FEMALE,
            LifeStage.GENERAL,
            PhysiologicalCondition.PREMENOPAUSAL,
            "7",
            "16",
        ),
        (
            "pregnancy",
            216,
            None,
            SexApplicability.FEMALE,
            LifeStage.PREGNANCY,
            None,
            "7",
            "16",
        ),
        (
            "lactation",
            216,
            None,
            SexApplicability.FEMALE,
            LifeStage.LACTATION,
            None,
            "7",
            "16",
        ),
    )
    for suffix, minimum, maximum, sex, stage, condition, ar, pri in iron_pairs:
        pop = _pop(
            minimum,
            maximum,
            sex=sex,
            life_stage=stage,
            physiological_condition=condition,
        )
        r.extend(
            (
                _numeric(
                    f"iron-ar-{suffix}",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.AR,
                    Authority.EFSA_NDA,
                    "iron",
                    "analyte:iron",
                    ar,
                    Unit.MILLIGRAM,
                    pop,
                    "FE-DRV",
                    "KIR-127 §4.9 iron AR/PRI table",
                ),
                _numeric(
                    f"iron-pri-{suffix}",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.PRI,
                    Authority.EFSA_NDA,
                    "iron",
                    "analyte:iron",
                    pri,
                    Unit.MILLIGRAM,
                    pop,
                    "FE-DRV",
                    "KIR-127 §4.9 iron AR/PRI table",
                ),
            )
        )
    r.append(
        _no_value(
            "iron-ul-none-safe-level-identified",
            ReferenceDomain.EFSA_SAFETY,
            ReferenceType.UL,
            Authority.EFSA_NDA,
            "iron",
            "analyte:iron",
            _pop(),
            "FE-SAFE",
            "KIR-127 §4.9 no-UL safety conclusion",
            ReferenceStatus.NO_UL_SAFE_LEVEL_IDENTIFIED,
        )
    )
    iron_safe = (
        (
            "4-6m",
            4,
            7,
            "5",
            ExposureBasis.IRON_FORTIFIED_PLUS_SUPPLEMENTAL_EXCLUDING_FORMULA,
        ),
        (
            "7-11m",
            7,
            12,
            "5",
            ExposureBasis.IRON_FORTIFIED_PLUS_SUPPLEMENTAL_EXCLUDING_FORMULA,
        ),
        ("1-3y", 12, 48, "10", ExposureBasis.TOTAL_INTAKE),
        ("4-6y", 48, 84, "15", ExposureBasis.TOTAL_INTAKE),
        ("7-10y", 84, 132, "20", ExposureBasis.TOTAL_INTAKE),
        ("11-14y", 132, 180, "30", ExposureBasis.TOTAL_INTAKE),
        ("15-17y", 180, 216, "35", ExposureBasis.TOTAL_INTAKE),
        ("adult", 216, None, "40", ExposureBasis.TOTAL_INTAKE),
    )
    for suffix, minimum, maximum, value, exposure in iron_safe:
        r.append(
            _numeric(
                f"iron-safe-level-{suffix}",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.SAFE_LEVEL,
                Authority.EFSA_NDA,
                "iron",
                "analyte:iron",
                value,
                Unit.MILLIGRAM,
                _pop(minimum, maximum),
                "FE-SAFE",
                "KIR-127 §4.9 iron SAFE_LEVEL table",
                exposure_basis=exposure,
                excludes_medical_supervision=True,
                provenance_note=(
                    "SAFE_LEVEL is not a UL and does not apply to individuals "
                    "receiving iron under medical supervision."
                ),
            )
        )

    # Calcium.
    r.append(
        _numeric(
            "calcium-ai-7-11m",
            ReferenceDomain.EFSA_DIETARY_REFERENCE,
            ReferenceType.AI,
            Authority.EFSA_NDA,
            "calcium",
            "analyte:calcium",
            "280",
            Unit.MILLIGRAM,
            _pop(7, 12),
            "CA-DRV",
            "KIR-127 §4.10 calcium table",
        )
    )
    for suffix, minimum, maximum, ar, pri in (
        ("1-3y", 12, 48, "390", "450"),
        ("4-10y", 48, 132, "680", "800"),
        ("11-17y", 132, 216, "960", "1150"),
        ("18-24y", 216, 300, "860", "1000"),
        ("25y-plus", 300, None, "750", "950"),
    ):
        pop = _pop(minimum, maximum)
        r.extend(
            (
                _numeric(
                    f"calcium-ar-{suffix}",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.AR,
                    Authority.EFSA_NDA,
                    "calcium",
                    "analyte:calcium",
                    ar,
                    Unit.MILLIGRAM,
                    pop,
                    "CA-DRV",
                    "KIR-127 §4.10 calcium AR/PRI table",
                ),
                _numeric(
                    f"calcium-pri-{suffix}",
                    ReferenceDomain.EFSA_DIETARY_REFERENCE,
                    ReferenceType.PRI,
                    Authority.EFSA_NDA,
                    "calcium",
                    "analyte:calcium",
                    pri,
                    Unit.MILLIGRAM,
                    pop,
                    "CA-DRV",
                    "KIR-127 §4.10 calcium AR/PRI table",
                ),
            )
        )
    r.extend(
        (
            _no_value(
                "calcium-ul-pediatric-no-ul",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.EFSA_NDA,
                "calcium",
                "analyte:calcium",
                _pop(0, 216),
                "CA-UL",
                "KIR-127 §4.10 insufficient pediatric UL data",
                ReferenceStatus.NO_UL_INSUFFICIENT_DATA,
                exposure_basis=ExposureBasis.TOTAL_INTAKE,
                exposure_match_required=True,
            ),
            _numeric(
                "calcium-ul-adult",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.EFSA_NDA,
                "calcium",
                "analyte:calcium",
                "2500",
                Unit.MILLIGRAM,
                _pop(216, None),
                "CA-UL",
                "KIR-127 §4.10 adult calcium UL",
                exposure_basis=ExposureBasis.TOTAL_INTAKE,
            ),
        )
    )

    # EPA/DHA DRV and historical/current safety semantics.
    r.extend(
        (
            _numeric(
                "epa-dha-ai-adult",
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ReferenceType.AI,
                Authority.EFSA_NDA,
                "epa_plus_dha",
                "analyte:epa-plus-dha",
                "250",
                Unit.MILLIGRAM,
                _pop(216, None, life_stage=LifeStage.GENERAL),
                "O3-DRV",
                "KIR-127 §4.11 adult EPA+DHA AI",
            ),
            _numeric(
                "dha-ai-7m-lt24m",
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ReferenceType.AI,
                Authority.EFSA_NDA,
                "dha",
                "analyte:dha",
                "100",
                Unit.MILLIGRAM,
                _pop(7, 24),
                "O3-DRV",
                "KIR-127 §4.11 infant/young-child DHA AI",
            ),
            _range_numeric(
                "dha-ai-pregnancy-increment",
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ReferenceType.AI,
                Authority.EFSA_NDA,
                "dha",
                "analyte:dha",
                "100",
                "200",
                Unit.MILLIGRAM,
                _pop(216, None, life_stage=LifeStage.PREGNANCY),
                "O3-DRV",
                "KIR-127 §4.11 pregnancy DHA range increment",
                value_semantics=ValueSemantics.RANGE_INCREMENT,
                exposure_basis=ExposureBasis.DIETARY_TOTAL,
                base_reference_id="epa-dha-ai-adult",
            ),
            _range_numeric(
                "dha-ai-lactation-increment",
                ReferenceDomain.EFSA_DIETARY_REFERENCE,
                ReferenceType.AI,
                Authority.EFSA_NDA,
                "dha",
                "analyte:dha",
                "100",
                "200",
                Unit.MILLIGRAM,
                _pop(216, None, life_stage=LifeStage.LACTATION),
                "O3-DRV",
                "KIR-127 §4.11 lactation DHA range increment",
                value_semantics=ValueSemantics.RANGE_INCREMENT,
                exposure_basis=ExposureBasis.DIETARY_TOTAL,
                base_reference_id="epa-dha-ai-adult",
            ),
            _no_value(
                "o3-2012-dha-ul-no-ul",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.EFSA_NDA,
                "dha",
                "analyte:dha",
                _pop(),
                "O3-UL",
                "KIR-127 §4.11 / 2012 long-chain n-3 PUFA safety opinion",
                ReferenceStatus.NO_UL_INSUFFICIENT_DATA,
                selection_priority=10,
                provenance_note=(
                    "2012 broader DHA safety semantics remain selectable and "
                    "historically reproducible."
                ),
            ),
            _no_value(
                "o3-2012-epa-plus-dha-ul-no-ul",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.EFSA_NDA,
                "epa_plus_dha",
                "analyte:epa-plus-dha",
                _pop(),
                "O3-UL",
                "KIR-127 §4.11 / 2012 long-chain n-3 PUFA safety opinion",
                ReferenceStatus.NO_UL_INSUFFICIENT_DATA,
                selection_priority=10,
            ),
        )
    )

    dha_source_classes = (
        SourceClass.FISH_OIL_CONCENTRATE,
        SourceClass.ALGAL_OIL,
        SourceClass.KRILL_OIL,
    )
    dha_forms = (
        DHAForm.TRIACYLGLYCEROL,
        DHAForm.ETHYL_ESTER,
        DHAForm.PHOSPHOLIPID,
    )
    r.extend(
        (
            _no_value(
                "dha-2026-ul-no-ul-safe-level-identified",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.UL,
                Authority.EFSA_NDA,
                "dha",
                "analyte:dha",
                _pop(),
                "O3-DHA-SAFE-2026",
                "KIR-127 2026 DHA erratum + KIR-153 accepted applicability",
                ReferenceStatus.NO_UL_SAFE_LEVEL_IDENTIFIED,
                exposure_basis=ExposureBasis.SUPPLEMENTAL_OR_ADDED_DHA,
                exposure_match_required=True,
                selection_priority=100,
                allowed_source_classes=dha_source_classes,
                allowed_dha_forms=dha_forms,
                epa_dha_ratio_max_exclusive="0.3",
                requires_epa_and_dha_amounts=True,
                excludes_background_dietary_dha=True,
                provenance_note=(
                    "Applies only to supplemental/added DHA-alone or mostly-DHA "
                    "exposure with EPA/DHA <0.3. SAFE_LEVEL is not UL or dose advice."
                ),
            ),
            _numeric(
                "dha-2026-safe-level",
                ReferenceDomain.EFSA_SAFETY,
                ReferenceType.SAFE_LEVEL,
                Authority.EFSA_NDA,
                "dha",
                "analyte:dha",
                "1",
                Unit.GRAM,
                _pop(),
                "O3-DHA-SAFE-2026",
                "KIR-127 2026 DHA erratum + KIR-153 accepted applicability",
                exposure_basis=ExposureBasis.SUPPLEMENTAL_OR_ADDED_DHA,
                exposure_match_required=True,
                status=ReferenceStatus.CONDITIONAL_NUMERIC,
                selection_priority=100,
                allowed_source_classes=dha_source_classes,
                allowed_dha_forms=dha_forms,
                epa_dha_ratio_max_exclusive="0.3",
                requires_epa_and_dha_amounts=True,
                excludes_background_dietary_dha=True,
                provenance_note=(
                    "Applies only to supplemental/added DHA-alone or mostly-DHA "
                    "exposure with EPA/DHA <0.3. SAFE_LEVEL is not UL or dose advice."
                ),
            ),
        )
    )

    return tuple(r)


RECORDS: Final[tuple[ReferenceRecord, ...]] = _build_records()

EU_EFSA_REFERENCE_DATASET: Final = ReferenceDataset(
    version=DATASET_VERSION,
    sources=SOURCES,
    records=RECORDS,
)
