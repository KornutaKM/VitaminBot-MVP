from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final

DOMAIN_SCHEMA_VERSION: Final = "1.0.0"


class DomainValidationError(ValueError):
    """Raised when a domain object violates a KIR-109 invariant."""


class UnitDimension(StrEnum):
    MASS = "mass"
    VOLUME = "volume"
    COUNT = "count"
    ACTIVITY = "activity"


class Unit(StrEnum):
    GRAM = "g"
    MILLIGRAM = "mg"
    MICROGRAM = "ug"
    LITER = "L"
    MILLILITER = "mL"
    COUNT = "count"
    INTERNATIONAL_UNIT = "IU"


class SubjectKind(StrEnum):
    ANALYTE = "analyte"
    INGREDIENT = "ingredient"


class AmountBasis(StrEnum):
    ANALYTE = "analyte"
    ELEMENTAL = "elemental"
    INGREDIENT_COMPOUND = "ingredient_compound"
    MATERIAL = "material"
    EQUIVALENT = "equivalent"


class QuantityBasis(StrEnum):
    PER_CONSUMPTION_UNIT = "per_consumption_unit"
    PER_LABEL_PORTION = "per_label_portion"
    PER_RECOMMENDED_DAILY_PORTION = "per_recommended_daily_portion"
    PER_100_G = "per_100_g"
    PER_100_ML = "per_100_ml"
    PER_DAY = "per_day"
    ABSOLUTE = "absolute"
    OTHER_EXPLICIT = "other_explicit"


class EvidenceStatus(StrEnum):
    DECLARED = "declared"
    DERIVED = "derived"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED_IDENTITY = "unresolved_identity"


class SourceType(StrEnum):
    EU_LAW = "eu_law"
    EFSA_OPINION = "efsa_opinion"
    OFFICIAL_GUIDANCE = "official_guidance"
    PRODUCT_LABEL = "product_label"
    SECONDARY_AUTHORITATIVE = "secondary_authoritative"
    CHEMICAL_ONTOLOGY = "chemical_ontology"
    USER_DECLARATION = "user_declaration"


class AgeUnit(StrEnum):
    DAYS = "days"
    MONTHS = "months"
    YEARS = "years"


class SexApplicability(StrEnum):
    MALE = "male"
    FEMALE = "female"
    ALL = "all"


class LifeStage(StrEnum):
    GENERAL = "general"
    PREGNANCY = "pregnancy"
    LACTATION = "lactation"


class CandidateState(StrEnum):
    ACTIVE = "active"
    EXCLUDED = "excluded"


class ConfirmationState(StrEnum):
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ScientificResolutionState(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"


_UNIT_DIMENSIONS: Final[dict[Unit, UnitDimension]] = {
    Unit.GRAM: UnitDimension.MASS,
    Unit.MILLIGRAM: UnitDimension.MASS,
    Unit.MICROGRAM: UnitDimension.MASS,
    Unit.LITER: UnitDimension.VOLUME,
    Unit.MILLILITER: UnitDimension.VOLUME,
    Unit.COUNT: UnitDimension.COUNT,
    Unit.INTERNATIONAL_UNIT: UnitDimension.ACTIVITY,
}

_CANONICAL_UNITS: Final[dict[UnitDimension, Unit | None]] = {
    UnitDimension.MASS: Unit.MICROGRAM,
    UnitDimension.VOLUME: Unit.MILLILITER,
    UnitDimension.COUNT: Unit.COUNT,
    UnitDimension.ACTIVITY: None,
}

_LABEL_REFERENCE_BASES: Final[frozenset[QuantityBasis]] = frozenset(
    {
        QuantityBasis.PER_CONSUMPTION_UNIT,
        QuantityBasis.PER_LABEL_PORTION,
        QuantityBasis.PER_RECOMMENDED_DAILY_PORTION,
    }
)


def _require_nonempty(value: str, field_name: str) -> None:
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be blank")


def _require_positive(value: Decimal, field_name: str) -> None:
    if value <= 0:
        raise DomainValidationError(f"{field_name} must be greater than zero")


def _require_nonnegative(value: Decimal, field_name: str) -> None:
    if value < 0:
        raise DomainValidationError(f"{field_name} must not be negative")


def unit_dimension(unit: Unit) -> UnitDimension:
    """Return only the physical/logical dimension of a unit.

    This function intentionally performs no scientific conversion.
    """

    return _UNIT_DIMENSIONS[unit]


def canonical_unit_for_dimension(dimension: UnitDimension) -> Unit | None:
    """Return the generic canonical unit, if the dimension has one.

    Activity/equivalence units intentionally have no generic canonical mass unit.
    """

    return _CANONICAL_UNITS[dimension]


@dataclass(frozen=True, slots=True, kw_only=True)
class Jurisdiction:
    code: str
    parent_code: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.code, "code")
        if self.parent_code is not None:
            _require_nonempty(self.parent_code, "parent_code")

    def to_payload(self) -> dict[str, object]:
        return {"code": self.code, "parent_code": self.parent_code}


@dataclass(frozen=True, slots=True, kw_only=True)
class PopulationApplicability:
    source_label: str
    age_min: Decimal | None = None
    age_max: Decimal | None = None
    age_unit: AgeUnit | None = None
    min_inclusive: bool = True
    max_inclusive: bool = True
    sex: SexApplicability | None = None
    life_stage: LifeStage | None = None
    physiological_condition: str | None = None
    source_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty(self.source_label, "source_label")
        if self.age_min is not None:
            _require_nonnegative(self.age_min, "age_min")
        if self.age_max is not None:
            _require_nonnegative(self.age_max, "age_max")
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise DomainValidationError("age_min must not exceed age_max")
        has_age = self.age_min is not None or self.age_max is not None
        if has_age != (self.age_unit is not None):
            raise DomainValidationError("age_unit is required exactly when an age boundary exists")
        if self.physiological_condition is not None:
            _require_nonempty(self.physiological_condition, "physiological_condition")
        for condition in self.source_conditions:
            _require_nonempty(condition, "source_conditions item")

    def to_payload(self) -> dict[str, object]:
        return {
            "source_label": self.source_label,
            "age_min": str(self.age_min) if self.age_min is not None else None,
            "age_max": str(self.age_max) if self.age_max is not None else None,
            "age_unit": self.age_unit.value if self.age_unit is not None else None,
            "min_inclusive": self.min_inclusive,
            "max_inclusive": self.max_inclusive,
            "sex": self.sex.value if self.sex is not None else None,
            "life_stage": self.life_stage.value if self.life_stage is not None else None,
            "physiological_condition": self.physiological_condition,
            "source_conditions": list(self.source_conditions),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceRecord:
    source_id: str
    authority: str
    source_type: SourceType
    title: str
    stable_identifier: str
    version: str
    retrieved_on: date
    jurisdiction: Jurisdiction | None = None
    url: str | None = None
    published_on: date | None = None
    adopted_on: date | None = None
    effective_on: date | None = None
    locator: str | None = None
    supersedes_source_id: str | None = None
    superseded_by_source_id: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("source_id", self.source_id),
            ("authority", self.authority),
            ("title", self.title),
            ("stable_identifier", self.stable_identifier),
            ("version", self.version),
        ):
            _require_nonempty(value, field_name)
        if self.url is not None:
            _require_nonempty(self.url, "url")
        if self.locator is not None:
            _require_nonempty(self.locator, "locator")
        if self.supersedes_source_id == self.source_id:
            raise DomainValidationError("a source cannot supersede itself")
        if self.superseded_by_source_id == self.source_id:
            raise DomainValidationError("a source cannot be superseded by itself")

    def to_payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "authority": self.authority,
            "source_type": self.source_type.value,
            "title": self.title,
            "stable_identifier": self.stable_identifier,
            "version": self.version,
            "retrieved_on": self.retrieved_on.isoformat(),
            "jurisdiction": self.jurisdiction.to_payload()
            if self.jurisdiction is not None
            else None,
            "url": self.url,
            "published_on": self.published_on.isoformat()
            if self.published_on is not None
            else None,
            "adopted_on": self.adopted_on.isoformat() if self.adopted_on is not None else None,
            "effective_on": self.effective_on.isoformat()
            if self.effective_on is not None
            else None,
            "locator": self.locator,
            "supersedes_source_id": self.supersedes_source_id,
            "superseded_by_source_id": self.superseded_by_source_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackedAnalyte:
    analyte_id: str
    display_name: str
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty(self.analyte_id, "analyte_id")
        _require_nonempty(self.display_name, "display_name")
        for alias in self.aliases:
            _require_nonempty(alias, "aliases item")


@dataclass(frozen=True, slots=True, kw_only=True)
class ChemicalForm:
    chemical_form_id: str
    display_name: str
    identity_status: ResolutionStatus
    external_identifier: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.chemical_form_id, "chemical_form_id")
        _require_nonempty(self.display_name, "display_name")
        if self.external_identifier is not None:
            _require_nonempty(self.external_identifier, "external_identifier")


@dataclass(frozen=True, slots=True, kw_only=True)
class Ingredient:
    ingredient_id: str
    display_name: str
    chemical_form_id: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.ingredient_id, "ingredient_id")
        _require_nonempty(self.display_name, "display_name")
        if self.chemical_form_id is not None:
            _require_nonempty(self.chemical_form_id, "chemical_form_id")


@dataclass(frozen=True, slots=True, kw_only=True)
class SupplyRelationship:
    relationship_id: str
    ingredient_id: str
    analyte_id: str
    source_id: str
    chemical_form_id: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("relationship_id", self.relationship_id),
            ("ingredient_id", self.ingredient_id),
            ("analyte_id", self.analyte_id),
            ("source_id", self.source_id),
        ):
            _require_nonempty(value, field_name)
        if self.chemical_form_id is not None:
            _require_nonempty(self.chemical_form_id, "chemical_form_id")


@dataclass(frozen=True, slots=True, kw_only=True)
class RegulatoryClassificationRecord:
    classification_id: str
    subject_kind: SubjectKind
    subject_id: str
    classification: str
    jurisdiction: Jurisdiction
    source_id: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("classification_id", self.classification_id),
            ("subject_id", self.subject_id),
            ("classification", self.classification),
            ("source_id", self.source_id),
        ):
            _require_nonempty(value, field_name)


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsumptionUnitDefinition:
    unit_id: str
    label_name: str
    source_id: str

    def __post_init__(self) -> None:
        _require_nonempty(self.unit_id, "unit_id")
        _require_nonempty(self.label_name, "label_name")
        _require_nonempty(self.source_id, "source_id")


@dataclass(frozen=True, slots=True, kw_only=True)
class ServingDefinition:
    basis_id: str
    basis_type: QuantityBasis
    label_text: str
    source_id: str
    basis_quantity: Decimal | None = None
    basis_unit: Unit | None = None
    consumption_unit_id: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.basis_id, "basis_id")
        _require_nonempty(self.label_text, "label_text")
        _require_nonempty(self.source_id, "source_id")
        if (self.basis_quantity is None) != (self.basis_unit is None):
            raise DomainValidationError(
                "basis_quantity and basis_unit must either both be set or both be absent"
            )
        if self.basis_quantity is not None:
            _require_positive(self.basis_quantity, "basis_quantity")
        if self.consumption_unit_id is not None:
            _require_nonempty(self.consumption_unit_id, "consumption_unit_id")
        if self.basis_unit is Unit.COUNT and self.consumption_unit_id is None:
            raise DomainValidationError(
                "count-based serving definitions require a consumption_unit_id"
            )
        if (
            self.basis_type is QuantityBasis.PER_CONSUMPTION_UNIT
            and self.consumption_unit_id is None
        ):
            raise DomainValidationError("per-consumption-unit basis requires a consumption_unit_id")


@dataclass(frozen=True, slots=True, kw_only=True)
class Derivation:
    rule_id: str
    rule_version: str
    authority_source_id: str
    input_amount_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonempty(self.rule_id, "rule_id")
        _require_nonempty(self.rule_version, "rule_version")
        _require_nonempty(self.authority_source_id, "authority_source_id")
        if not self.input_amount_ids:
            raise DomainValidationError("derived values require at least one input amount")
        for amount_id in self.input_amount_ids:
            _require_nonempty(amount_id, "input_amount_ids item")

    def to_payload(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "authority_source_id": self.authority_source_id,
            "input_amount_ids": list(self.input_amount_ids),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class AmountRecord:
    amount_id: str
    subject_kind: SubjectKind
    subject_id: str
    source_id: str
    resolution_status: ResolutionStatus
    evidence_status: EvidenceStatus
    value: Decimal | None = None
    unit: Unit | None = None
    amount_basis: AmountBasis | None = None
    quantity_basis: QuantityBasis | None = None
    quantity_basis_id: str | None = None
    equivalence_basis: str | None = None
    raw_text: str | None = None
    derivation: Derivation | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.amount_id, "amount_id")
        _require_nonempty(self.subject_id, "subject_id")
        _require_nonempty(self.source_id, "source_id")

        if self.value is not None:
            _require_nonnegative(self.value, "value")
        if self.quantity_basis_id is not None:
            _require_nonempty(self.quantity_basis_id, "quantity_basis_id")
        if self.raw_text is not None:
            _require_nonempty(self.raw_text, "raw_text")

        if self.resolution_status is ResolutionStatus.RESOLVED:
            if (
                self.value is None
                or self.unit is None
                or self.amount_basis is None
                or self.quantity_basis is None
            ):
                raise DomainValidationError(
                    "resolved amount requires value, unit, amount_basis, and quantity_basis"
                )
            if self.evidence_status in (EvidenceStatus.AMBIGUOUS, EvidenceStatus.UNKNOWN):
                raise DomainValidationError(
                    "resolved amount cannot have ambiguous/unknown evidence status"
                )

        if (
            self.quantity_basis in _LABEL_REFERENCE_BASES
            and self.quantity_basis_id is None
            and self.resolution_status is ResolutionStatus.RESOLVED
        ):
            raise DomainValidationError("resolved label-basis amount requires quantity_basis_id")

        if self.evidence_status is EvidenceStatus.DERIVED:
            if self.derivation is None:
                raise DomainValidationError("derived amount requires derivation provenance")
            if self.resolution_status is not ResolutionStatus.RESOLVED:
                raise DomainValidationError("derived amount must be resolved")
        elif self.derivation is not None:
            raise DomainValidationError("derivation metadata is only valid for derived evidence")

        if self.amount_basis is AmountBasis.EQUIVALENT:
            if self.equivalence_basis is None:
                raise DomainValidationError(
                    "equivalent amount requires an explicit equivalence_basis"
                )
            _require_nonempty(self.equivalence_basis, "equivalence_basis")
        elif self.equivalence_basis is not None:
            raise DomainValidationError("equivalence_basis is only valid for equivalent amounts")

        if (
            self.amount_basis
            in (
                AmountBasis.ANALYTE,
                AmountBasis.ELEMENTAL,
                AmountBasis.EQUIVALENT,
            )
            and self.subject_kind is not SubjectKind.ANALYTE
        ):
            raise DomainValidationError(
                "analyte/elemental/equivalent amounts must reference an analyte subject"
            )

        if (
            self.amount_basis
            in (
                AmountBasis.INGREDIENT_COMPOUND,
                AmountBasis.MATERIAL,
            )
            and self.subject_kind is not SubjectKind.INGREDIENT
        ):
            raise DomainValidationError(
                "compound/material amounts must reference an ingredient subject"
            )

    @property
    def deterministically_usable(self) -> bool:
        return self.resolution_status is ResolutionStatus.RESOLVED and self.evidence_status in (
            EvidenceStatus.DECLARED,
            EvidenceStatus.DERIVED,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": DOMAIN_SCHEMA_VERSION,
            "amount_id": self.amount_id,
            "subject_kind": self.subject_kind.value,
            "subject_id": self.subject_id,
            "source_id": self.source_id,
            "resolution_status": self.resolution_status.value,
            "evidence_status": self.evidence_status.value,
            "value": str(self.value) if self.value is not None else None,
            "unit": self.unit.value if self.unit is not None else None,
            "amount_basis": self.amount_basis.value if self.amount_basis is not None else None,
            "quantity_basis": self.quantity_basis.value
            if self.quantity_basis is not None
            else None,
            "quantity_basis_id": self.quantity_basis_id,
            "equivalence_basis": self.equivalence_basis,
            "raw_text": self.raw_text,
            "derivation": self.derivation.to_payload() if self.derivation is not None else None,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductIdentity:
    product_id: str
    name: str
    market_jurisdiction_status: ResolutionStatus
    market_jurisdiction: Jurisdiction | None = None
    brand: str | None = None
    variant: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.product_id, "product_id")
        _require_nonempty(self.name, "name")

        if self.market_jurisdiction_status is ResolutionStatus.RESOLVED:
            if self.market_jurisdiction is None:
                raise DomainValidationError(
                    "resolved market jurisdiction requires a jurisdiction value"
                )
        elif self.market_jurisdiction is not None:
            raise DomainValidationError(
                "unresolved market jurisdiction must not carry a guessed jurisdiction value"
            )

        if self.brand is not None:
            _require_nonempty(self.brand, "brand")
        if self.variant is not None:
            _require_nonempty(self.variant, "variant")

    def to_payload(self) -> dict[str, object]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "market_jurisdiction_status": self.market_jurisdiction_status.value,
            "market_jurisdiction": self.market_jurisdiction.to_payload()
            if self.market_jurisdiction is not None
            else None,
            "brand": self.brand,
            "variant": self.variant,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductFormulationVersion:
    formulation_id: str
    product_id: str
    version: str
    source_ids: tuple[str, ...]
    ingredient_ids: tuple[str, ...] = ()
    amount_ids: tuple[str, ...] = ()
    serving_basis_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty(self.formulation_id, "formulation_id")
        _require_nonempty(self.product_id, "product_id")
        _require_nonempty(self.version, "version")
        if not self.source_ids:
            raise DomainValidationError("formulation version requires source provenance")
        for source_id in self.source_ids:
            _require_nonempty(source_id, "source_ids item")


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackedSupplementInstance:
    instance_id: str
    formulation_id: str
    container_label: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.instance_id, "instance_id")
        _require_nonempty(self.formulation_id, "formulation_id")
        if self.container_label is not None:
            _require_nonempty(self.container_label, "container_label")


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedIntakeEvent:
    event_id: str
    consumption_unit_id: str
    consumption_units: Decimal
    schedule_label: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.event_id, "event_id")
        _require_nonempty(self.consumption_unit_id, "consumption_unit_id")
        _require_positive(self.consumption_units, "consumption_units")
        if self.schedule_label is not None:
            _require_nonempty(self.schedule_label, "schedule_label")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsumedIntakeEvent:
    event_id: str
    tracked_instance_id: str
    consumption_unit_id: str
    consumption_units: Decimal
    consumed_at: datetime
    confirmation_source_id: str

    def __post_init__(self) -> None:
        _require_nonempty(self.event_id, "event_id")
        _require_nonempty(self.tracked_instance_id, "tracked_instance_id")
        _require_nonempty(self.consumption_unit_id, "consumption_unit_id")
        _require_positive(self.consumption_units, "consumption_units")
        _require_nonempty(self.confirmation_source_id, "confirmation_source_id")
        if self.consumed_at.tzinfo is None:
            raise DomainValidationError("consumed_at must be timezone-aware")


@dataclass(frozen=True, slots=True, kw_only=True)
class IntakePlan:
    plan_id: str
    tracked_instance_id: str
    version: str
    events: tuple[PlannedIntakeEvent, ...]

    def __post_init__(self) -> None:
        _require_nonempty(self.plan_id, "plan_id")
        _require_nonempty(self.tracked_instance_id, "tracked_instance_id")
        _require_nonempty(self.version, "version")
        event_ids = tuple(event.event_id for event in self.events)
        if len(set(event_ids)) != len(event_ids):
            raise DomainValidationError("plan event IDs must be unique")


@dataclass(frozen=True, slots=True, kw_only=True)
class EntityCandidate:
    candidate_id: str
    canonical_entity_id: str
    source_id: str
    state: CandidateState = CandidateState.ACTIVE

    def __post_init__(self) -> None:
        _require_nonempty(self.candidate_id, "candidate_id")
        _require_nonempty(self.canonical_entity_id, "canonical_entity_id")
        _require_nonempty(self.source_id, "source_id")


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateResolution:
    candidate_set_id: str
    candidates: tuple[EntityCandidate, ...]
    confirmation_state: ConfirmationState = ConfirmationState.UNCONFIRMED
    scientific_resolution_state: ScientificResolutionState = ScientificResolutionState.NOT_EVALUATED
    selected_candidate_id: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.candidate_set_id, "candidate_set_id")
        if not self.candidates:
            raise DomainValidationError("candidate set must retain at least one candidate")

        candidate_ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise DomainValidationError("candidate IDs must be unique")

        candidate_by_id = {candidate.candidate_id: candidate for candidate in self.candidates}

        if self.selected_candidate_id is not None:
            _require_nonempty(self.selected_candidate_id, "selected_candidate_id")
            if self.selected_candidate_id not in candidate_by_id:
                raise DomainValidationError(
                    "selected_candidate_id must refer to a retained candidate"
                )

        if self.confirmation_state is ConfirmationState.CONFIRMED:
            if self.selected_candidate_id is None:
                raise DomainValidationError(
                    "confirmed candidate resolution requires selected_candidate_id"
                )
            selected = candidate_by_id[self.selected_candidate_id]
            if selected.state is not CandidateState.ACTIVE:
                raise DomainValidationError(
                    "confirmed candidate resolution must select an active candidate"
                )
        elif self.selected_candidate_id is not None:
            raise DomainValidationError(
                "selected_candidate_id is permitted only for confirmed resolution"
            )
