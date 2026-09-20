from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from threading import RLock
from typing import Final, Protocol

from vitaminbot.recognition.contract import (
    AcquisitionMethod,
    CorrectionRecord,
    DownstreamEligibility,
    ExplicitEquivalentObservation,
    FieldConfirmationState,
    FieldObservation,
    LabelExtraction,
    LabelRowObservation,
    PresenceState,
    ProductIdentityObservation,
    RecordState,
    RecognitionValidationError,
    ServingObservation,
    SourceAsset,
    SourceKind,
)

DEFAULT_TRANSIENT_IMAGE_TTL: Final = timedelta(minutes=30)
SUPPORTED_IMAGE_MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)


class PhotoPipelineError(RuntimeError):
    """Base error for the KIR-117 photo-recognition pipeline."""


class TransientImageExpiredError(PhotoPipelineError):
    """Raised when source pixels have expired and must be re-uploaded."""


class ProviderExecutionError(PhotoPipelineError):
    """Expected provider timeout/unavailability/malformed-response failure."""


class ProviderContractError(PhotoPipelineError):
    """Raised when a provider adapter violates the project-owned contract."""


class StaleConfirmationError(PhotoPipelineError):
    """Raised when a confirmation targets an outdated extraction revision."""


class IncompleteConfirmationError(PhotoPipelineError):
    """Raised when the displayed/decided confirmation scope is incomplete."""


class FieldDecisionAction(StrEnum):
    CONFIRM = "confirm"
    CONFIRM_UNKNOWN = "confirm_unknown"
    CORRECT = "correct"
    REJECT = "reject"


class ManualFallbackReason(StrEnum):
    SOURCE_EXPIRED = "source_expired"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_INVALID_OUTPUT = "provider_invalid_output"


@dataclass(frozen=True, slots=True)
class TransientImageHandle:
    asset_id: str
    object_key: str
    media_type: str
    sha256_hex: str
    stored_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ProviderRevision:
    provider_key: str
    model_revision: str
    adapter_revision: str
    prompt_revision: str
    schema_revision: str
    preprocessing_revision: str

    def __post_init__(self) -> None:
        for name, value in (
            ("provider_key", self.provider_key),
            ("model_revision", self.model_revision),
            ("adapter_revision", self.adapter_revision),
            ("prompt_revision", self.prompt_revision),
            ("schema_revision", self.schema_revision),
            ("preprocessing_revision", self.preprocessing_revision),
        ):
            if not value.strip():
                raise ProviderContractError(f"{name} must not be blank")


@dataclass(frozen=True, slots=True)
class ProviderExtractionResult:
    extraction: LabelExtraction
    revision: ProviderRevision
    raw_response_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.raw_response_sha256 is not None:
            _require_sha256(self.raw_response_sha256, "raw_response_sha256")


@dataclass(frozen=True, slots=True)
class ExtractionProvenance:
    provider: ProviderRevision
    requested_at: datetime
    completed_at: datetime
    image_sha256: str
    raw_response_sha256: str | None

    def __post_init__(self) -> None:
        _require_aware(self.requested_at, "requested_at")
        _require_aware(self.completed_at, "completed_at")
        if self.completed_at < self.requested_at:
            raise ProviderContractError("completed_at cannot precede requested_at")
        _require_sha256(self.image_sha256, "image_sha256")
        if self.raw_response_sha256 is not None:
            _require_sha256(self.raw_response_sha256, "raw_response_sha256")


@dataclass(frozen=True, slots=True)
class PhotoCapture:
    capture_id: str
    image: TransientImageHandle

    def __post_init__(self) -> None:
        if not self.capture_id.strip():
            raise PhotoPipelineError("capture_id must not be blank")


@dataclass(frozen=True, slots=True)
class PhotoExtractionCandidate:
    capture: PhotoCapture
    extraction: LabelExtraction
    provenance: ExtractionProvenance


@dataclass(frozen=True, slots=True)
class ManualEntryFallback:
    capture_id: str
    reason: ManualFallbackReason
    detail: str
    record_state: RecordState = RecordState.MANUAL_ENTRY_REQUIRED

    def __post_init__(self) -> None:
        if not self.capture_id.strip():
            raise PhotoPipelineError("capture_id must not be blank")
        if not self.detail.strip():
            raise PhotoPipelineError("manual fallback detail must not be blank")
        if self.record_state is not RecordState.MANUAL_ENTRY_REQUIRED:
            raise PhotoPipelineError("manual fallback must use manual_entry_required state")


@dataclass(frozen=True, slots=True)
class FieldDecision:
    field_id: str
    action: FieldDecisionAction
    corrected_raw_text: str | None = None

    def __post_init__(self) -> None:
        if not self.field_id.strip():
            raise IncompleteConfirmationError("field_id must not be blank")
        if self.action is FieldDecisionAction.CORRECT:
            if self.corrected_raw_text is None or not self.corrected_raw_text.strip():
                raise IncompleteConfirmationError("correct action requires corrected_raw_text")
        elif self.corrected_raw_text is not None:
            raise IncompleteConfirmationError(
                "corrected_raw_text is valid only for correct action"
            )


@dataclass(frozen=True, slots=True)
class ConfirmationRequest:
    expected_revision: int
    displayed_field_ids: tuple[str, ...]
    decisions: tuple[FieldDecision, ...]
    confirmed_at: datetime

    def __post_init__(self) -> None:
        if self.expected_revision < 0:
            raise StaleConfirmationError("expected_revision must be non-negative")
        _require_aware(self.confirmed_at, "confirmed_at")
        if len(set(self.displayed_field_ids)) != len(self.displayed_field_ids):
            raise IncompleteConfirmationError("displayed_field_ids must be unique")
        decision_ids = tuple(decision.field_id for decision in self.decisions)
        if len(set(decision_ids)) != len(decision_ids):
            raise IncompleteConfirmationError("each field may have only one decision")


@dataclass(frozen=True, slots=True)
class ConfirmedLabelRecord:
    extraction: LabelExtraction
    provenance: ExtractionProvenance
    confirmed_at: datetime
    idempotency_key: str

    def __post_init__(self) -> None:
        if self.extraction.record_state is not RecordState.ACCEPTED_FOR_STORAGE:
            raise PhotoPipelineError("only accepted_for_storage extraction may be persisted")
        _require_aware(self.confirmed_at, "confirmed_at")
        if not self.idempotency_key.strip():
            raise PhotoPipelineError("idempotency_key must not be blank")


@dataclass(frozen=True, slots=True)
class RejectedPhotoCapture:
    capture_id: str
    extraction: LabelExtraction
    record_state: RecordState = RecordState.REJECTED

    def __post_init__(self) -> None:
        if self.extraction.record_state is not RecordState.REJECTED:
            raise PhotoPipelineError("rejected result must carry rejected extraction")
        if self.record_state is not RecordState.REJECTED:
            raise PhotoPipelineError("rejected result must use rejected state")


class RecognitionProvider(Protocol):
    def extract(
        self,
        image: bytes,
        *,
        media_type: str,
        source_asset: SourceAsset,
    ) -> ProviderExtractionResult:
        """Map provider output into the project-owned KIR-111 contract."""


class ConfirmedLabelSink(Protocol):
    def persist(self, record: ConfirmedLabelRecord) -> None:
        """Persist idempotently by record.idempotency_key or fail without partial commit."""


class TransientImageStore(Protocol):
    def put(
        self,
        *,
        asset_id: str,
        image: bytes,
        media_type: str,
        ttl: timedelta,
    ) -> TransientImageHandle: ...

    def read(self, handle: TransientImageHandle) -> bytes: ...

    def delete(self, handle: TransientImageHandle) -> None: ...

    def purge_expired(self) -> int: ...


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PhotoPipelineError(f"{field_name} must be timezone-aware")


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise PhotoPipelineError(f"{field_name} must be a hexadecimal SHA-256 digest")


class InMemoryTransientImageStore:
    """Bounded transient store for tests/local wiring; production may inject object storage."""

    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock
        self._items: dict[str, tuple[TransientImageHandle, bytes]] = {}
        self._lock = RLock()

    def put(
        self,
        *,
        asset_id: str,
        image: bytes,
        media_type: str,
        ttl: timedelta,
    ) -> TransientImageHandle:
        if not asset_id.strip():
            raise PhotoPipelineError("asset_id must not be blank")
        if not image:
            raise PhotoPipelineError("image must not be empty")
        if media_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
            raise PhotoPipelineError(f"unsupported image media type {media_type!r}")
        if ttl <= timedelta(0):
            raise PhotoPipelineError("ttl must be positive")

        now = self._clock()
        _require_aware(now, "clock value")
        digest = sha256(image).hexdigest()
        object_key = f"{asset_id}:{digest}"
        handle = TransientImageHandle(
            asset_id=asset_id,
            object_key=object_key,
            media_type=media_type,
            sha256_hex=digest,
            stored_at=now,
            expires_at=now + ttl,
        )
        with self._lock:
            self._items[object_key] = (handle, bytes(image))
        return handle

    def read(self, handle: TransientImageHandle) -> bytes:
        now = self._clock()
        _require_aware(now, "clock value")
        with self._lock:
            item = self._items.get(handle.object_key)
            if item is None:
                raise TransientImageExpiredError("transient source image is unavailable")
            stored_handle, image = item
            if stored_handle != handle:
                raise PhotoPipelineError("transient image handle mismatch")
            if handle.expires_at <= now:
                del self._items[handle.object_key]
                raise TransientImageExpiredError("transient source image expired")
            if sha256(image).hexdigest() != handle.sha256_hex:
                del self._items[handle.object_key]
                raise PhotoPipelineError("transient source image integrity check failed")
            return bytes(image)

    def delete(self, handle: TransientImageHandle) -> None:
        with self._lock:
            self._items.pop(handle.object_key, None)

    def purge_expired(self) -> int:
        now = self._clock()
        _require_aware(now, "clock value")
        with self._lock:
            expired = [
                key
                for key, (handle, _) in self._items.items()
                if handle.expires_at <= now
            ]
            for key in expired:
                del self._items[key]
            return len(expired)


def iter_label_fields(extraction: LabelExtraction) -> tuple[FieldObservation, ...]:
    fields: list[FieldObservation] = [extraction.product_identity.product_name]
    if extraction.product_identity.brand is not None:
        fields.append(extraction.product_identity.brand)
    if extraction.serving is not None:
        fields.append(extraction.serving.serving_size)
        if extraction.serving.servings_per_container is not None:
            fields.append(extraction.serving.servings_per_container)
        if extraction.serving.serving_basis is not None:
            fields.append(extraction.serving.serving_basis)
    for row in extraction.rows:
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


def _validate_provider_candidate(
    result: ProviderExtractionResult,
    *,
    source_asset: SourceAsset,
) -> LabelExtraction:
    extraction = result.extraction
    if extraction.acquisition_method is not AcquisitionMethod.PHOTO:
        raise ProviderContractError("photo provider must return acquisition_method=photo")
    if extraction.confirmation_revision != 0:
        raise ProviderContractError("provider output cannot carry a confirmation revision")
    if extraction.record_state is not RecordState.EXTRACTED_UNCONFIRMED:
        raise ProviderContractError("provider output must start as extracted_unconfirmed")
    fields = iter_label_fields(extraction)
    if any(
        field.confirmation_state is not FieldConfirmationState.UNCONFIRMED
        for field in fields
    ):
        raise ProviderContractError("provider output cannot confirm any field")
    if len({field.field_id for field in fields}) != len(fields):
        raise ProviderContractError("provider field IDs must be unique for confirmation")
    if extraction.source_assets != (source_asset,):
        raise ProviderContractError(
            "provider output must preserve exactly the pipeline-owned label source asset"
        )

    target_state = (
        RecordState.USER_RESOLUTION_REQUIRED
        if extraction.requires_user_resolution
        else RecordState.READY_FOR_USER_CONFIRMATION
    )
    try:
        return replace(extraction, record_state=target_state)
    except RecognitionValidationError as exc:
        raise ProviderContractError(str(exc)) from exc


def _map_equivalent(
    value: ExplicitEquivalentObservation,
    mapper: Callable[[FieldObservation], FieldObservation],
) -> ExplicitEquivalentObservation:
    return replace(
        value,
        subject=mapper(value.subject),
        quantity=mapper(value.quantity),
        unit=mapper(value.unit),
    )


def _map_row(
    row: LabelRowObservation,
    mapper: Callable[[FieldObservation], FieldObservation],
) -> LabelRowObservation:
    return replace(
        row,
        printed_name=mapper(row.printed_name),
        quantity=mapper(row.quantity) if row.quantity is not None else None,
        unit=mapper(row.unit) if row.unit is not None else None,
        chemical_form=mapper(row.chemical_form) if row.chemical_form is not None else None,
        elemental_or_equivalent=(
            _map_equivalent(row.elemental_or_equivalent, mapper)
            if row.elemental_or_equivalent is not None
            else None
        ),
        reference_values=tuple(mapper(value) for value in row.reference_values),
    )


def _map_extraction_fields(
    extraction: LabelExtraction,
    mapper: Callable[[FieldObservation], FieldObservation],
) -> LabelExtraction:
    identity = ProductIdentityObservation(
        product_name=mapper(extraction.product_identity.product_name),
        brand=(
            mapper(extraction.product_identity.brand)
            if extraction.product_identity.brand is not None
            else None
        ),
    )
    serving: ServingObservation | None = None
    if extraction.serving is not None:
        serving = ServingObservation(
            serving_size=mapper(extraction.serving.serving_size),
            servings_per_container=(
                mapper(extraction.serving.servings_per_container)
                if extraction.serving.servings_per_container is not None
                else None
            ),
            serving_basis=(
                mapper(extraction.serving.serving_basis)
                if extraction.serving.serving_basis is not None
                else None
            ),
        )
    return replace(
        extraction,
        product_identity=identity,
        serving=serving,
        rows=tuple(_map_row(row, mapper) for row in extraction.rows),
    )


def _apply_decision(
    field: FieldObservation,
    decision: FieldDecision,
    *,
    confirmed_at: datetime,
) -> FieldObservation:
    if decision.action is FieldDecisionAction.CONFIRM:
        if field.presence_state is not PresenceState.PRESENT:
            raise IncompleteConfirmationError(
                f"field {field.field_id!r} is not visibly present; confirm_unknown or correct it"
            )
        return replace(
            field,
            confirmation_state=FieldConfirmationState.USER_CONFIRMED,
        )
    if decision.action is FieldDecisionAction.CONFIRM_UNKNOWN:
        if field.presence_state is PresenceState.PRESENT:
            raise IncompleteConfirmationError(
                f"field {field.field_id!r} is present and cannot be confirmed unknown"
            )
        return replace(
            field,
            confirmation_state=FieldConfirmationState.USER_CONFIRMED_UNKNOWN,
            downstream_eligibility=DownstreamEligibility.BLOCKED_UNRESOLVED,
        )
    if decision.action is FieldDecisionAction.CORRECT:
        if field.raw_text is None:
            raise IncompleteConfirmationError(
                f"field {field.field_id!r} has no raw text; use manual-entry fallback"
            )
        corrected = decision.corrected_raw_text
        if corrected is None:
            raise IncompleteConfirmationError("correct action requires corrected_raw_text")
        corrected = corrected.strip()
        if corrected == field.raw_text:
            raise IncompleteConfirmationError("correction must change the raw text")
        correction = CorrectionRecord(
            original_raw_text=field.raw_text,
            corrected_raw_text=corrected,
            corrected_at=confirmed_at.isoformat(),
        )
        return replace(
            field,
            presence_state=PresenceState.PRESENT,
            raw_text=corrected,
            normalized_candidate=None,
            confidence=None,
            confirmation_state=FieldConfirmationState.USER_CORRECTED,
            corrections=field.corrections + (correction,),
        )
    return replace(
        field,
        confirmation_state=FieldConfirmationState.REJECTED,
        downstream_eligibility=DownstreamEligibility.BLOCKED_UNRESOLVED,
    )


class PhotoRecognitionPipeline:
    def __init__(
        self,
        *,
        provider: RecognitionProvider,
        image_store: TransientImageStore,
        sink: ConfirmedLabelSink,
        image_ttl: timedelta = DEFAULT_TRANSIENT_IMAGE_TTL,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if image_ttl <= timedelta(0):
            raise PhotoPipelineError("image_ttl must be positive")
        if image_ttl > DEFAULT_TRANSIENT_IMAGE_TTL:
            raise PhotoPipelineError("image_ttl exceeds the 30-minute KIR-117 privacy cap")
        self._provider = provider
        self._image_store = image_store
        self._sink = sink
        self._image_ttl = image_ttl
        self._clock = clock

    def capture(
        self,
        *,
        capture_id: str,
        image: bytes,
        media_type: str,
    ) -> PhotoCapture:
        if not capture_id.strip():
            raise PhotoPipelineError("capture_id must not be blank")
        handle = self._image_store.put(
            asset_id=f"image:{capture_id}",
            image=image,
            media_type=media_type,
            ttl=self._image_ttl,
        )
        return PhotoCapture(capture_id=capture_id, image=handle)

    def extract(
        self,
        capture: PhotoCapture,
    ) -> PhotoExtractionCandidate | ManualEntryFallback:
        requested_at = self._clock()
        _require_aware(requested_at, "clock value")
        try:
            image = self._image_store.read(capture.image)
        except TransientImageExpiredError:
            return ManualEntryFallback(
                capture_id=capture.capture_id,
                reason=ManualFallbackReason.SOURCE_EXPIRED,
                detail="source image expired; request re-upload or manual entry",
            )

        source_asset = SourceAsset(
            asset_id=capture.image.asset_id,
            source_kind=SourceKind.LABEL_IMAGE,
            reference=f"transient://{capture.image.object_key}",
            captured_at=capture.image.stored_at.isoformat(),
        )
        try:
            result = self._provider.extract(
                image, media_type=capture.image.media_type, source_asset=source_asset
            )
            extraction = _validate_provider_candidate(result, source_asset=source_asset)
        except ProviderExecutionError as exc:
            self._image_store.delete(capture.image)
            return ManualEntryFallback(
                capture_id=capture.capture_id,
                reason=ManualFallbackReason.PROVIDER_UNAVAILABLE,
                detail=str(exc) or "provider unavailable",
            )
        except (ProviderContractError, RecognitionValidationError) as exc:
            self._image_store.delete(capture.image)
            return ManualEntryFallback(
                capture_id=capture.capture_id,
                reason=ManualFallbackReason.PROVIDER_INVALID_OUTPUT,
                detail=str(exc) or "provider output violated recognition contract",
            )

        completed_at = self._clock()
        _require_aware(completed_at, "clock value")
        provenance = ExtractionProvenance(
            provider=result.revision,
            requested_at=requested_at,
            completed_at=completed_at,
            image_sha256=capture.image.sha256_hex,
            raw_response_sha256=result.raw_response_sha256,
        )
        return PhotoExtractionCandidate(
            capture=capture,
            extraction=extraction,
            provenance=provenance,
        )

    def confirm_and_persist(
        self,
        candidate: PhotoExtractionCandidate,
        request: ConfirmationRequest,
    ) -> ConfirmedLabelRecord | RejectedPhotoCapture | ManualEntryFallback:
        try:
            self._image_store.read(candidate.capture.image)
        except TransientImageExpiredError:
            return ManualEntryFallback(
                capture_id=candidate.capture.capture_id,
                reason=ManualFallbackReason.SOURCE_EXPIRED,
                detail="source image expired before confirmation; request re-upload or manual entry",
            )

        extraction = candidate.extraction
        if request.expected_revision != extraction.confirmation_revision:
            raise StaleConfirmationError(
                "confirmation revision does not match current extraction revision"
            )

        fields = iter_label_fields(extraction)
        field_ids = tuple(field.field_id for field in fields)
        if len(set(field_ids)) != len(field_ids):
            raise ProviderContractError("extraction field IDs are not unique")

        expected_scope = set(field_ids)
        displayed_scope = set(request.displayed_field_ids)
        decision_map = {decision.field_id: decision for decision in request.decisions}
        if displayed_scope != expected_scope:
            raise IncompleteConfirmationError(
                "confirmation UI must display the complete extraction field scope"
            )
        if set(decision_map) != expected_scope:
            raise IncompleteConfirmationError(
                "every displayed field requires an explicit confirmation decision"
            )

        def mapper(field: FieldObservation) -> FieldObservation:
            return _apply_decision(
                field,
                decision_map[field.field_id],
                confirmed_at=request.confirmed_at,
            )

        decided = _map_extraction_fields(extraction, mapper)
        if any(
            field.confirmation_state is FieldConfirmationState.REJECTED
            for field in iter_label_fields(decided)
        ):
            rejected = replace(decided, record_state=RecordState.REJECTED)
            self._image_store.delete(candidate.capture.image)
            return RejectedPhotoCapture(
                capture_id=candidate.capture.capture_id,
                extraction=rejected,
            )

        accepted = replace(
            decided,
            record_state=RecordState.ACCEPTED_FOR_STORAGE,
            confirmation_revision=extraction.confirmation_revision + 1,
        )
        record = ConfirmedLabelRecord(
            extraction=accepted,
            provenance=candidate.provenance,
            confirmed_at=request.confirmed_at,
            idempotency_key=(
                f"{accepted.extraction_id}:{accepted.confirmation_revision}"
            ),
        )
        self._sink.persist(record)
        self._image_store.delete(candidate.capture.image)
        return record

    def abandon(self, candidate: PhotoExtractionCandidate) -> RejectedPhotoCapture:
        rejected = replace(candidate.extraction, record_state=RecordState.REJECTED)
        self._image_store.delete(candidate.capture.image)
        return RejectedPhotoCapture(
            capture_id=candidate.capture.capture_id,
            extraction=rejected,
        )
