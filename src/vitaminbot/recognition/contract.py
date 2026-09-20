from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Final, cast

EXTRACTION_SCHEMA_VERSION: Final = "1.0.0"


class RecognitionValidationError(ValueError):
    """Raised when a recognition contract object violates a KIR-111 invariant."""


class AcquisitionMethod(StrEnum):
    PHOTO = "photo"
    BARCODE = "barcode"
    MANUAL = "manual"


class SourceKind(StrEnum):
    LABEL_IMAGE = "label_image"
    EXTERNAL_CATALOG = "external_catalog"
    MANUAL_INPUT = "manual_input"


class PresenceState(StrEnum):
    PRESENT = "present"
    NOT_PRINTED = "not_printed"
    NOT_VISIBLE = "not_visible"
    UNREADABLE = "unreadable"
    UNKNOWN = "unknown"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class FieldConfirmationState(StrEnum):
    UNCONFIRMED = "unconfirmed"
    USER_CONFIRMED = "user_confirmed"
    USER_CORRECTED = "user_corrected"
    USER_CONFIRMED_UNKNOWN = "user_confirmed_unknown"
    REJECTED = "rejected"


_ACCEPTED_FIELD_CONFIRMATION_STATES: Final[frozenset[FieldConfirmationState]] = frozenset(
    {
        FieldConfirmationState.USER_CONFIRMED,
        FieldConfirmationState.USER_CORRECTED,
        FieldConfirmationState.USER_CONFIRMED_UNKNOWN,
    }
)


class SemanticState(StrEnum):
    RESOLVED_FOR_LABEL_MEANING = "resolved_for_label_meaning"
    UNRESOLVED = "unresolved"


class DownstreamEligibility(StrEnum):
    CANDIDATE_FOR_NORMALIZATION = "candidate_for_normalization"
    BLOCKED_UNRESOLVED = "blocked_unresolved"
    NOT_APPLICABLE = "not_applicable"


class AmbiguityCode(StrEnum):
    LOW_CONFIDENCE_TEXT = "low_confidence_text"
    CONFLICTING_OBSERVATIONS = "conflicting_observations"
    MISSING_SERVING_INFORMATION = "missing_serving_information"
    COMPOUND_VS_ELEMENTAL_UNCLEAR = "compound_vs_elemental_unclear"
    UNIT_UNCLEAR = "unit_unclear"
    ROW_RELATIONSHIP_UNCLEAR = "row_relationship_unclear"
    REFERENCE_VALUE_UNCLEAR = "reference_value_unclear"
    SOURCE_REGION_INCOMPLETE = "source_region_incomplete"
    CATALOG_CONFLICTS_WITH_LABEL = "catalog_conflicts_with_label"
    UNREADABLE_TEXT = "unreadable_text"


class RecordState(StrEnum):
    CAPTURE_RECEIVED = "capture_received"
    EXTRACTED_UNCONFIRMED = "extracted_unconfirmed"
    READY_FOR_USER_CONFIRMATION = "ready_for_user_confirmation"
    USER_RESOLUTION_REQUIRED = "user_resolution_required"
    MANUAL_ENTRY_REQUIRED = "manual_entry_required"
    ACCEPTED_FOR_STORAGE = "accepted_for_storage"
    REJECTED = "rejected"


_ALLOWED_RECORD_TRANSITIONS: Final[dict[RecordState, frozenset[RecordState]]] = {
    RecordState.CAPTURE_RECEIVED: frozenset(
        {
            RecordState.EXTRACTED_UNCONFIRMED,
            RecordState.MANUAL_ENTRY_REQUIRED,
            RecordState.REJECTED,
        }
    ),
    RecordState.EXTRACTED_UNCONFIRMED: frozenset(
        {
            RecordState.READY_FOR_USER_CONFIRMATION,
            RecordState.USER_RESOLUTION_REQUIRED,
            RecordState.MANUAL_ENTRY_REQUIRED,
            RecordState.REJECTED,
        }
    ),
    RecordState.READY_FOR_USER_CONFIRMATION: frozenset(
        {
            RecordState.ACCEPTED_FOR_STORAGE,
            RecordState.USER_RESOLUTION_REQUIRED,
            RecordState.MANUAL_ENTRY_REQUIRED,
            RecordState.REJECTED,
        }
    ),
    RecordState.USER_RESOLUTION_REQUIRED: frozenset(
        {
            RecordState.READY_FOR_USER_CONFIRMATION,
            RecordState.ACCEPTED_FOR_STORAGE,
            RecordState.MANUAL_ENTRY_REQUIRED,
            RecordState.REJECTED,
        }
    ),
    RecordState.MANUAL_ENTRY_REQUIRED: frozenset(
        {
            RecordState.READY_FOR_USER_CONFIRMATION,
            RecordState.USER_RESOLUTION_REQUIRED,
            RecordState.ACCEPTED_FOR_STORAGE,
            RecordState.REJECTED,
        }
    ),
    RecordState.ACCEPTED_FOR_STORAGE: frozenset(
        {
            RecordState.USER_RESOLUTION_REQUIRED,
            RecordState.REJECTED,
        }
    ),
    RecordState.REJECTED: frozenset(),
}


def _require_nonempty(value: str, field_name: str) -> None:
    if not value.strip():
        raise RecognitionValidationError(f"{field_name} must not be blank")


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise RecognitionValidationError(f"{field_name} must be an object")
    return cast(Mapping[str, object], value)


def _require_sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise RecognitionValidationError(f"{field_name} must be an array")
    return cast(Sequence[object], value)


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise RecognitionValidationError(f"{field_name} must be a string")
    _require_nonempty(value, field_name)
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field_name)


def _optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise RecognitionValidationError(f"{field_name} must be an integer")
    return value


def _enum_value[T: StrEnum](enum_type: type[T], value: object, field_name: str) -> T:
    raw = _require_string(value, field_name)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise RecognitionValidationError(f"{field_name} has unsupported value {raw!r}") from exc


def record_transition_allowed(current: RecordState, target: RecordState) -> bool:
    """Return whether the confirmation/ambiguity state machine permits the transition."""

    return target in _ALLOWED_RECORD_TRANSITIONS[current]


def require_record_transition(current: RecordState, target: RecordState) -> None:
    if not record_transition_allowed(current, target):
        raise RecognitionValidationError(
            f"record transition {current.value!r} -> {target.value!r} is not allowed"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceAsset:
    asset_id: str
    source_kind: SourceKind
    reference: str
    captured_at: str | None = None
    provider: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.asset_id, "asset_id")
        _require_nonempty(self.reference, "reference")
        if self.captured_at is not None:
            _require_nonempty(self.captured_at, "captured_at")
        if self.provider is not None:
            _require_nonempty(self.provider, "provider")
        if self.source_kind is SourceKind.EXTERNAL_CATALOG and self.provider is None:
            raise RecognitionValidationError("external catalog source assets require provider")

    def to_payload(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "source_kind": self.source_kind.value,
            "reference": self.reference,
            "captured_at": self.captured_at,
            "provider": self.provider,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> SourceAsset:
        return cls(
            asset_id=_require_string(payload.get("asset_id"), "asset_id"),
            source_kind=_enum_value(SourceKind, payload.get("source_kind"), "source_kind"),
            reference=_require_string(payload.get("reference"), "reference"),
            captured_at=_optional_string(payload.get("captured_at"), "captured_at"),
            provider=_optional_string(payload.get("provider"), "provider"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceRegion:
    asset_id: str
    region_id: str
    page_index: int | None = None
    bbox: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.asset_id, "asset_id")
        _require_nonempty(self.region_id, "region_id")
        if self.page_index is not None and self.page_index < 0:
            raise RecognitionValidationError("page_index must be non-negative")
        if self.bbox is not None:
            x1, y1, x2, y2 = self.bbox
            if not all(0 <= coordinate <= 1 for coordinate in self.bbox):
                raise RecognitionValidationError("bbox coordinates must be normalized to [0, 1]")
            if x2 <= x1 or y2 <= y1:
                raise RecognitionValidationError("bbox must have positive width and height")

    def to_payload(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "region_id": self.region_id,
            "page_index": self.page_index,
            "bbox": list(self.bbox) if self.bbox is not None else None,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> SourceRegion:
        bbox_value = payload.get("bbox")
        bbox: tuple[float, float, float, float] | None = None
        if bbox_value is not None:
            raw_bbox = _require_sequence(bbox_value, "bbox")
            if len(raw_bbox) != 4:
                raise RecognitionValidationError("bbox must contain four numbers")
            values: list[float] = []
            for index, coordinate in enumerate(raw_bbox):
                if not isinstance(coordinate, (int, float)) or isinstance(coordinate, bool):
                    raise RecognitionValidationError(f"bbox[{index}] must be numeric")
                values.append(float(coordinate))
            bbox = (values[0], values[1], values[2], values[3])
        return cls(
            asset_id=_require_string(payload.get("asset_id"), "asset_id"),
            region_id=_require_string(payload.get("region_id"), "region_id"),
            page_index=_optional_int(payload.get("page_index"), "page_index"),
            bbox=bbox,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfidenceMetadata:
    band: ConfidenceBand
    raw_score: Decimal | None = None
    score_scale: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.raw_score is not None and self.score_scale is None:
            raise RecognitionValidationError("raw_score requires score_scale")
        if self.score_scale is not None:
            _require_nonempty(self.score_scale, "score_scale")
        if self.reason is not None:
            _require_nonempty(self.reason, "reason")

    def to_payload(self) -> dict[str, object]:
        return {
            "band": self.band.value,
            "raw_score": (str(self.raw_score) if self.raw_score is not None else None),
            "score_scale": self.score_scale,
            "reason": self.reason,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ConfidenceMetadata:
        raw_score_value = payload.get("raw_score")
        raw_score: Decimal | None = None
        if raw_score_value is not None:
            raw_score_text = _require_string(raw_score_value, "raw_score")
            try:
                raw_score = Decimal(raw_score_text)
            except InvalidOperation as exc:
                raise RecognitionValidationError("raw_score must be a decimal string") from exc
        return cls(
            band=_enum_value(ConfidenceBand, payload.get("band"), "band"),
            raw_score=raw_score,
            score_scale=_optional_string(payload.get("score_scale"), "score_scale"),
            reason=_optional_string(payload.get("reason"), "reason"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrectionRecord:
    original_raw_text: str
    corrected_raw_text: str
    corrected_at: str

    def __post_init__(self) -> None:
        _require_nonempty(self.original_raw_text, "original_raw_text")
        _require_nonempty(self.corrected_raw_text, "corrected_raw_text")
        _require_nonempty(self.corrected_at, "corrected_at")
        if self.original_raw_text == self.corrected_raw_text:
            raise RecognitionValidationError("correction must change raw text")

    def to_payload(self) -> dict[str, object]:
        return {
            "original_raw_text": self.original_raw_text,
            "corrected_raw_text": self.corrected_raw_text,
            "corrected_at": self.corrected_at,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> CorrectionRecord:
        return cls(
            original_raw_text=_require_string(
                payload.get("original_raw_text"), "original_raw_text"
            ),
            corrected_raw_text=_require_string(
                payload.get("corrected_raw_text"), "corrected_raw_text"
            ),
            corrected_at=_require_string(payload.get("corrected_at"), "corrected_at"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FieldObservation:
    field_id: str
    source_kind: SourceKind
    presence_state: PresenceState
    raw_text: str | None
    normalized_candidate: str | None = None
    source_regions: tuple[SourceRegion, ...] = ()
    confidence: ConfidenceMetadata | None = None
    ambiguity_codes: tuple[AmbiguityCode, ...] = ()
    confirmation_state: FieldConfirmationState = FieldConfirmationState.UNCONFIRMED
    semantic_state: SemanticState = SemanticState.RESOLVED_FOR_LABEL_MEANING
    downstream_eligibility: DownstreamEligibility = (
        DownstreamEligibility.CANDIDATE_FOR_NORMALIZATION
    )
    corrections: tuple[CorrectionRecord, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty(self.field_id, "field_id")
        if self.raw_text is not None:
            _require_nonempty(self.raw_text, "raw_text")
        if self.normalized_candidate is not None:
            _require_nonempty(self.normalized_candidate, "normalized_candidate")
        if self.presence_state is PresenceState.PRESENT and self.raw_text is None:
            raise RecognitionValidationError("present fields require raw_text")
        if (
            self.presence_state in (PresenceState.NOT_PRINTED, PresenceState.NOT_VISIBLE)
            and self.normalized_candidate is not None
        ):
            raise RecognitionValidationError(
                "absent/not-visible fields cannot have normalized candidates"
            )
        if self.normalized_candidate is not None and self.raw_text is None:
            raise RecognitionValidationError("normalized candidates require raw_text")
        if (
            self.confirmation_state is FieldConfirmationState.USER_CORRECTED
            and not self.corrections
        ):
            raise RecognitionValidationError("user-corrected fields require correction history")
        if (
            self.corrections
            and self.confirmation_state is not FieldConfirmationState.USER_CORRECTED
        ):
            raise RecognitionValidationError(
                "correction history is valid only for user-corrected fields"
            )
        if (
            self.semantic_state is SemanticState.UNRESOLVED
            and self.downstream_eligibility is not DownstreamEligibility.BLOCKED_UNRESOLVED
        ):
            raise RecognitionValidationError(
                "semantically unresolved fields must be blocked from downstream use"
            )
        if (
            self.confirmation_state is FieldConfirmationState.REJECTED
            and self.downstream_eligibility is DownstreamEligibility.CANDIDATE_FOR_NORMALIZATION
        ):
            raise RecognitionValidationError(
                "rejected fields cannot remain downstream normalization candidates"
            )
        if (
            self.presence_state in (PresenceState.UNREADABLE, PresenceState.UNKNOWN)
            and self.confirmation_state is FieldConfirmationState.USER_CONFIRMED
        ):
            raise RecognitionValidationError(
                "unreadable/unknown fields require user_confirmed_unknown or correction"
            )
        if len(set(self.ambiguity_codes)) != len(self.ambiguity_codes):
            raise RecognitionValidationError("ambiguity_codes must be unique")
        region_keys = tuple((region.asset_id, region.region_id) for region in self.source_regions)
        if len(set(region_keys)) != len(region_keys):
            raise RecognitionValidationError("source region references must be unique per field")

    @property
    def needs_attention(self) -> bool:
        if self.confirmation_state is FieldConfirmationState.REJECTED:
            return True
        if self.confirmation_state is not FieldConfirmationState.UNCONFIRMED:
            return False
        low_confidence = self.confidence is not None and self.confidence.band in (
            ConfidenceBand.LOW,
            ConfidenceBand.UNKNOWN,
        )
        uncertain_presence = self.presence_state in (
            PresenceState.UNREADABLE,
            PresenceState.UNKNOWN,
            PresenceState.NOT_VISIBLE,
        )
        return bool(self.ambiguity_codes) or low_confidence or uncertain_presence

    def to_payload(self) -> dict[str, object]:
        return {
            "field_id": self.field_id,
            "source_kind": self.source_kind.value,
            "presence_state": self.presence_state.value,
            "raw_text": self.raw_text,
            "normalized_candidate": self.normalized_candidate,
            "source_regions": [region.to_payload() for region in self.source_regions],
            "confidence": (self.confidence.to_payload() if self.confidence is not None else None),
            "ambiguity_codes": [code.value for code in self.ambiguity_codes],
            "confirmation_state": self.confirmation_state.value,
            "semantic_state": self.semantic_state.value,
            "downstream_eligibility": self.downstream_eligibility.value,
            "corrections": [correction.to_payload() for correction in self.corrections],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> FieldObservation:
        raw_regions = _require_sequence(payload.get("source_regions", []), "source_regions")
        regions = tuple(
            SourceRegion.from_payload(_require_mapping(item, "source_regions item"))
            for item in raw_regions
        )
        raw_confidence = payload.get("confidence")
        confidence = (
            ConfidenceMetadata.from_payload(_require_mapping(raw_confidence, "confidence"))
            if raw_confidence is not None
            else None
        )
        raw_ambiguities = _require_sequence(payload.get("ambiguity_codes", []), "ambiguity_codes")
        ambiguity_codes = tuple(
            _enum_value(AmbiguityCode, item, "ambiguity_codes item") for item in raw_ambiguities
        )
        raw_corrections = _require_sequence(payload.get("corrections", []), "corrections")
        corrections = tuple(
            CorrectionRecord.from_payload(_require_mapping(item, "corrections item"))
            for item in raw_corrections
        )
        return cls(
            field_id=_require_string(payload.get("field_id"), "field_id"),
            source_kind=_enum_value(SourceKind, payload.get("source_kind"), "source_kind"),
            presence_state=_enum_value(
                PresenceState,
                payload.get("presence_state"),
                "presence_state",
            ),
            raw_text=_optional_string(payload.get("raw_text"), "raw_text"),
            normalized_candidate=_optional_string(
                payload.get("normalized_candidate"),
                "normalized_candidate",
            ),
            source_regions=regions,
            confidence=confidence,
            ambiguity_codes=ambiguity_codes,
            confirmation_state=_enum_value(
                FieldConfirmationState,
                payload.get(
                    "confirmation_state",
                    FieldConfirmationState.UNCONFIRMED.value,
                ),
                "confirmation_state",
            ),
            semantic_state=_enum_value(
                SemanticState,
                payload.get(
                    "semantic_state",
                    SemanticState.RESOLVED_FOR_LABEL_MEANING.value,
                ),
                "semantic_state",
            ),
            downstream_eligibility=_enum_value(
                DownstreamEligibility,
                payload.get(
                    "downstream_eligibility",
                    DownstreamEligibility.CANDIDATE_FOR_NORMALIZATION.value,
                ),
                "downstream_eligibility",
            ),
            corrections=corrections,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductIdentityObservation:
    product_name: FieldObservation
    brand: FieldObservation | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "product_name": self.product_name.to_payload(),
            "brand": (self.brand.to_payload() if self.brand is not None else None),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProductIdentityObservation:
        raw_brand = payload.get("brand")
        return cls(
            product_name=FieldObservation.from_payload(
                _require_mapping(payload.get("product_name"), "product_name")
            ),
            brand=(
                FieldObservation.from_payload(_require_mapping(raw_brand, "brand"))
                if raw_brand is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ServingObservation:
    serving_size: FieldObservation
    servings_per_container: FieldObservation | None = None
    serving_basis: FieldObservation | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "serving_size": self.serving_size.to_payload(),
            "servings_per_container": (
                self.servings_per_container.to_payload()
                if self.servings_per_container is not None
                else None
            ),
            "serving_basis": (
                self.serving_basis.to_payload() if self.serving_basis is not None else None
            ),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ServingObservation:
        raw_container = payload.get("servings_per_container")
        raw_basis = payload.get("serving_basis")
        return cls(
            serving_size=FieldObservation.from_payload(
                _require_mapping(payload.get("serving_size"), "serving_size")
            ),
            servings_per_container=(
                FieldObservation.from_payload(
                    _require_mapping(raw_container, "servings_per_container")
                )
                if raw_container is not None
                else None
            ),
            serving_basis=(
                FieldObservation.from_payload(_require_mapping(raw_basis, "serving_basis"))
                if raw_basis is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ExplicitEquivalentObservation:
    relationship_text: str
    subject: FieldObservation
    quantity: FieldObservation
    unit: FieldObservation

    def __post_init__(self) -> None:
        _require_nonempty(self.relationship_text, "relationship_text")
        if (
            self.subject.raw_text is None
            or self.quantity.raw_text is None
            or self.unit.raw_text is None
        ):
            raise RecognitionValidationError(
                "explicit elemental/equivalent observation requires "
                "visible subject, quantity, and unit"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "relationship_text": self.relationship_text,
            "subject": self.subject.to_payload(),
            "quantity": self.quantity.to_payload(),
            "unit": self.unit.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ExplicitEquivalentObservation:
        return cls(
            relationship_text=_require_string(
                payload.get("relationship_text"),
                "relationship_text",
            ),
            subject=FieldObservation.from_payload(
                _require_mapping(payload.get("subject"), "subject")
            ),
            quantity=FieldObservation.from_payload(
                _require_mapping(payload.get("quantity"), "quantity")
            ),
            unit=FieldObservation.from_payload(_require_mapping(payload.get("unit"), "unit")),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class LabelRowObservation:
    row_id: str
    row_raw_text: str
    printed_name: FieldObservation
    quantity: FieldObservation | None = None
    unit: FieldObservation | None = None
    chemical_form: FieldObservation | None = None
    elemental_or_equivalent: ExplicitEquivalentObservation | None = None
    reference_values: tuple[FieldObservation, ...] = ()
    ambiguity_codes: tuple[AmbiguityCode, ...] = ()
    semantic_state: SemanticState = SemanticState.RESOLVED_FOR_LABEL_MEANING
    downstream_eligibility: DownstreamEligibility = (
        DownstreamEligibility.CANDIDATE_FOR_NORMALIZATION
    )

    def __post_init__(self) -> None:
        _require_nonempty(self.row_id, "row_id")
        _require_nonempty(self.row_raw_text, "row_raw_text")
        if (
            self.semantic_state is SemanticState.UNRESOLVED
            and self.downstream_eligibility is not DownstreamEligibility.BLOCKED_UNRESOLVED
        ):
            raise RecognitionValidationError(
                "semantically unresolved rows must be blocked from downstream use"
            )
        if (
            AmbiguityCode.COMPOUND_VS_ELEMENTAL_UNCLEAR in self.ambiguity_codes
            and self.elemental_or_equivalent is not None
        ):
            raise RecognitionValidationError(
                "compound-vs-elemental-unclear row cannot contain explicit equivalent amount"
            )
        if len(set(self.ambiguity_codes)) != len(self.ambiguity_codes):
            raise RecognitionValidationError("row ambiguity_codes must be unique")

    @property
    def needs_attention(self) -> bool:
        fields: tuple[FieldObservation | None, ...] = (
            self.printed_name,
            self.quantity,
            self.unit,
            self.chemical_form,
        )
        return bool(self.ambiguity_codes) or any(
            field is not None and field.needs_attention for field in fields
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "row_id": self.row_id,
            "row_raw_text": self.row_raw_text,
            "printed_name": self.printed_name.to_payload(),
            "quantity": (self.quantity.to_payload() if self.quantity is not None else None),
            "unit": (self.unit.to_payload() if self.unit is not None else None),
            "chemical_form": (
                self.chemical_form.to_payload() if self.chemical_form is not None else None
            ),
            "elemental_or_equivalent": (
                self.elemental_or_equivalent.to_payload()
                if self.elemental_or_equivalent is not None
                else None
            ),
            "reference_values": [value.to_payload() for value in self.reference_values],
            "ambiguity_codes": [code.value for code in self.ambiguity_codes],
            "semantic_state": self.semantic_state.value,
            "downstream_eligibility": self.downstream_eligibility.value,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> LabelRowObservation:
        raw_quantity = payload.get("quantity")
        raw_unit = payload.get("unit")
        raw_form = payload.get("chemical_form")
        raw_equivalent = payload.get("elemental_or_equivalent")
        raw_references = _require_sequence(
            payload.get("reference_values", []),
            "reference_values",
        )
        raw_ambiguities = _require_sequence(
            payload.get("ambiguity_codes", []),
            "ambiguity_codes",
        )
        return cls(
            row_id=_require_string(payload.get("row_id"), "row_id"),
            row_raw_text=_require_string(payload.get("row_raw_text"), "row_raw_text"),
            printed_name=FieldObservation.from_payload(
                _require_mapping(payload.get("printed_name"), "printed_name")
            ),
            quantity=(
                FieldObservation.from_payload(_require_mapping(raw_quantity, "quantity"))
                if raw_quantity is not None
                else None
            ),
            unit=(
                FieldObservation.from_payload(_require_mapping(raw_unit, "unit"))
                if raw_unit is not None
                else None
            ),
            chemical_form=(
                FieldObservation.from_payload(_require_mapping(raw_form, "chemical_form"))
                if raw_form is not None
                else None
            ),
            elemental_or_equivalent=(
                ExplicitEquivalentObservation.from_payload(
                    _require_mapping(
                        raw_equivalent,
                        "elemental_or_equivalent",
                    )
                )
                if raw_equivalent is not None
                else None
            ),
            reference_values=tuple(
                FieldObservation.from_payload(_require_mapping(item, "reference_values item"))
                for item in raw_references
            ),
            ambiguity_codes=tuple(
                _enum_value(
                    AmbiguityCode,
                    item,
                    "ambiguity_codes item",
                )
                for item in raw_ambiguities
            ),
            semantic_state=_enum_value(
                SemanticState,
                payload.get(
                    "semantic_state",
                    SemanticState.RESOLVED_FOR_LABEL_MEANING.value,
                ),
                "semantic_state",
            ),
            downstream_eligibility=_enum_value(
                DownstreamEligibility,
                payload.get(
                    "downstream_eligibility",
                    DownstreamEligibility.CANDIDATE_FOR_NORMALIZATION.value,
                ),
                "downstream_eligibility",
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class LabelExtraction:
    extraction_id: str
    acquisition_method: AcquisitionMethod
    source_assets: tuple[SourceAsset, ...]
    raw_label_text: str
    product_identity: ProductIdentityObservation
    rows: tuple[LabelRowObservation, ...]
    record_state: RecordState
    serving: ServingObservation | None = None
    record_ambiguities: tuple[AmbiguityCode, ...] = ()
    confirmation_revision: int = 0
    schema_version: str = EXTRACTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_nonempty(self.extraction_id, "extraction_id")
        _require_nonempty(self.raw_label_text, "raw_label_text")
        if self.schema_version != EXTRACTION_SCHEMA_VERSION:
            raise RecognitionValidationError(
                f"unsupported extraction schema version {self.schema_version!r}"
            )
        if not self.source_assets:
            raise RecognitionValidationError("label extraction requires at least one source asset")
        asset_ids = tuple(asset.asset_id for asset in self.source_assets)
        if len(set(asset_ids)) != len(asset_ids):
            raise RecognitionValidationError("source asset IDs must be unique")
        row_ids = tuple(row.row_id for row in self.rows)
        if len(set(row_ids)) != len(row_ids):
            raise RecognitionValidationError("row IDs must be unique")
        if self.confirmation_revision < 0:
            raise RecognitionValidationError("confirmation_revision must be non-negative")
        if len(set(self.record_ambiguities)) != len(self.record_ambiguities):
            raise RecognitionValidationError("record_ambiguities must be unique")

        known_assets = set(asset_ids)
        for field in self._all_fields():
            for region in field.source_regions:
                if region.asset_id not in known_assets:
                    raise RecognitionValidationError(
                        f"field {field.field_id!r} references unknown asset {region.asset_id!r}"
                    )

        if (
            self.record_state is RecordState.READY_FOR_USER_CONFIRMATION
            and self.requires_user_resolution
        ):
            raise RecognitionValidationError(
                "ready-for-confirmation records cannot hide unresolved attention requirements"
            )

        if self.record_state is RecordState.ACCEPTED_FOR_STORAGE:
            if self.confirmation_revision == 0:
                raise RecognitionValidationError(
                    "accepted records require a positive confirmation revision"
                )
            if any(
                field.confirmation_state not in _ACCEPTED_FIELD_CONFIRMATION_STATES
                for field in self._all_fields()
            ):
                raise RecognitionValidationError(
                    "accepted records may contain only explicitly accepted field states"
                )

    def _all_fields(self) -> tuple[FieldObservation, ...]:
        fields: list[FieldObservation] = [self.product_identity.product_name]
        if self.product_identity.brand is not None:
            fields.append(self.product_identity.brand)
        if self.serving is not None:
            fields.append(self.serving.serving_size)
            if self.serving.servings_per_container is not None:
                fields.append(self.serving.servings_per_container)
            if self.serving.serving_basis is not None:
                fields.append(self.serving.serving_basis)
        for row in self.rows:
            fields.append(row.printed_name)
            if row.quantity is not None:
                fields.append(row.quantity)
            if row.unit is not None:
                fields.append(row.unit)
            if row.chemical_form is not None:
                fields.append(row.chemical_form)
            if row.elemental_or_equivalent is not None:
                fields.extend(
                    (
                        row.elemental_or_equivalent.subject,
                        row.elemental_or_equivalent.quantity,
                        row.elemental_or_equivalent.unit,
                    )
                )
            fields.extend(row.reference_values)
        return tuple(fields)

    @property
    def requires_user_resolution(self) -> bool:
        return (
            bool(self.record_ambiguities)
            or any(row.needs_attention for row in self.rows)
            or any(field.needs_attention for field in self._all_fields())
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "extraction_id": self.extraction_id,
            "acquisition_method": self.acquisition_method.value,
            "source_assets": [asset.to_payload() for asset in self.source_assets],
            "raw_label_text": self.raw_label_text,
            "product_identity": self.product_identity.to_payload(),
            "serving": (self.serving.to_payload() if self.serving is not None else None),
            "rows": [row.to_payload() for row in self.rows],
            "record_ambiguities": [code.value for code in self.record_ambiguities],
            "record_state": self.record_state.value,
            "confirmation_revision": self.confirmation_revision,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> LabelExtraction:
        raw_assets = _require_sequence(payload.get("source_assets"), "source_assets")
        raw_rows = _require_sequence(payload.get("rows"), "rows")
        raw_serving = payload.get("serving")
        raw_ambiguities = _require_sequence(
            payload.get("record_ambiguities", []),
            "record_ambiguities",
        )
        return cls(
            schema_version=_require_string(payload.get("schema_version"), "schema_version"),
            extraction_id=_require_string(payload.get("extraction_id"), "extraction_id"),
            acquisition_method=_enum_value(
                AcquisitionMethod,
                payload.get("acquisition_method"),
                "acquisition_method",
            ),
            source_assets=tuple(
                SourceAsset.from_payload(_require_mapping(item, "source_assets item"))
                for item in raw_assets
            ),
            raw_label_text=_require_string(payload.get("raw_label_text"), "raw_label_text"),
            product_identity=ProductIdentityObservation.from_payload(
                _require_mapping(
                    payload.get("product_identity"),
                    "product_identity",
                )
            ),
            serving=(
                ServingObservation.from_payload(_require_mapping(raw_serving, "serving"))
                if raw_serving is not None
                else None
            ),
            rows=tuple(
                LabelRowObservation.from_payload(_require_mapping(item, "rows item"))
                for item in raw_rows
            ),
            record_ambiguities=tuple(
                _enum_value(
                    AmbiguityCode,
                    item,
                    "record_ambiguities item",
                )
                for item in raw_ambiguities
            ),
            record_state=_enum_value(
                RecordState,
                payload.get("record_state"),
                "record_state",
            ),
            confirmation_revision=(
                _optional_int(
                    payload.get("confirmation_revision"),
                    "confirmation_revision",
                )
                or 0
            ),
        )


def validate_extraction_payload(
    payload: Mapping[str, object],
) -> LabelExtraction:
    """Validate and materialize a versioned recognition payload."""

    return LabelExtraction.from_payload(payload)
