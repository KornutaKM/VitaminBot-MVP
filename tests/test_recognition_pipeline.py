import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from vitaminbot.recognition import (
    FieldConfirmationState,
    PresenceState,
    RecordState,
    SourceAsset,
    validate_extraction_payload,
)
from vitaminbot.recognition.pipeline import (
    DEFAULT_TRANSIENT_IMAGE_TTL,
    ConfirmationRequest,
    ConfirmedLabelRecord,
    FieldDecision,
    FieldDecisionAction,
    IncompleteConfirmationError,
    InMemoryTransientImageStore,
    ManualEntryFallback,
    ManualFallbackReason,
    PhotoPipelineError,
    PhotoRecognitionPipeline,
    ProviderExecutionError,
    ProviderExtractionResult,
    ProviderRevision,
    RecognitionProvider,
    StaleConfirmationError,
    TransientImageExpiredError,
    iter_label_fields,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "recognition"
IMAGE_BYTES = b"synthetic-image-bytes"


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class FixtureProvider(RecognitionProvider):
    def __init__(self, fixture_name: str = "vitamin_d_iu.json") -> None:
        self.fixture_name = fixture_name
        self.calls = 0

    def extract(
        self,
        image: bytes,
        *,
        media_type: str,
        source_asset: SourceAsset,
    ) -> ProviderExtractionResult:
        assert image == IMAGE_BYTES
        assert media_type == "image/png"
        self.calls += 1
        raw = json.loads((FIXTURE_DIR / self.fixture_name).read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        payload = cast(dict[str, object], raw)
        payload["source_assets"] = [source_asset.to_payload()]
        payload["record_state"] = RecordState.EXTRACTED_UNCONFIRMED.value
        payload["confirmation_revision"] = 0
        return ProviderExtractionResult(
            extraction=validate_extraction_payload(payload),
            revision=ProviderRevision(
                provider_key="fixture",
                model_revision="fixture-model-v1",
                adapter_revision="adapter-v1",
                prompt_revision="prompt-v1",
                schema_revision="1.0.0",
                preprocessing_revision="none-v1",
            ),
            raw_response_sha256="0" * 64,
        )


class InvalidStateProvider(FixtureProvider):
    def extract(
        self,
        image: bytes,
        *,
        media_type: str,
        source_asset: SourceAsset,
    ) -> ProviderExtractionResult:
        result = super().extract(image, media_type=media_type, source_asset=source_asset)
        payload = result.extraction.to_payload()
        payload["record_state"] = RecordState.READY_FOR_USER_CONFIRMATION.value
        return ProviderExtractionResult(
            extraction=validate_extraction_payload(payload),
            revision=result.revision,
            raw_response_sha256=result.raw_response_sha256,
        )


class UnavailableProvider(FixtureProvider):
    def extract(
        self,
        image: bytes,
        *,
        media_type: str,
        source_asset: SourceAsset,
    ) -> ProviderExtractionResult:
        raise ProviderExecutionError("fixture provider unavailable")


class ChangingCandidateProvider(FixtureProvider):
    def extract(
        self,
        image: bytes,
        *,
        media_type: str,
        source_asset: SourceAsset,
    ) -> ProviderExtractionResult:
        result = super().extract(image, media_type=media_type, source_asset=source_asset)
        if self.calls == 1:
            return result

        payload = result.extraction.to_payload()
        rows = cast(list[object], payload["rows"])
        row = cast(dict[str, object], rows[0])
        quantity = cast(dict[str, object], row["quantity"])
        quantity["raw_text"] = "1200"
        quantity["normalized_candidate"] = "1200"
        return ProviderExtractionResult(
            extraction=validate_extraction_payload(payload),
            revision=result.revision,
            raw_response_sha256=result.raw_response_sha256,
        )


class MemorySink:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.records: dict[str, ConfirmedLabelRecord] = {}
        self.attempted_keys: list[str] = []

    def persist(self, record: ConfirmedLabelRecord) -> None:
        self.attempted_keys.append(record.idempotency_key)
        if self.fail:
            raise RuntimeError("persistence failed")
        existing = self.records.get(record.idempotency_key)
        if existing is not None and existing != record:
            raise RuntimeError("idempotency key collision")
        self.records.setdefault(record.idempotency_key, record)


def _pipeline(
    *,
    clock: MutableClock,
    provider: RecognitionProvider | None = None,
    sink: MemorySink | None = None,
) -> tuple[PhotoRecognitionPipeline, InMemoryTransientImageStore, MemorySink]:
    store = InMemoryTransientImageStore(clock=clock)
    actual_sink = sink or MemorySink()
    pipeline = PhotoRecognitionPipeline(
        provider=provider or FixtureProvider(),
        image_store=store,
        sink=actual_sink,
        clock=clock,
    )
    return pipeline, store, actual_sink


def _candidate(
    *,
    clock: MutableClock,
    provider: RecognitionProvider | None = None,
    sink: MemorySink | None = None,
):
    pipeline, store, actual_sink = _pipeline(clock=clock, provider=provider, sink=sink)
    capture = pipeline.capture(
        capture_id="capture-1",
        image=IMAGE_BYTES,
        media_type="image/png",
    )
    result = pipeline.extract(capture)
    assert not isinstance(result, ManualEntryFallback)
    return pipeline, store, actual_sink, result


def _confirm_all_request(candidate, *, clock: MutableClock) -> ConfirmationRequest:
    fields = iter_label_fields(candidate.extraction)
    decisions = tuple(
        FieldDecision(
            field_id=field.field_id,
            action=(
                FieldDecisionAction.CONFIRM
                if field.presence_state is PresenceState.PRESENT
                else FieldDecisionAction.CONFIRM_UNKNOWN
            ),
        )
        for field in fields
    )
    return ConfirmationRequest(
        expected_candidate_id=candidate.candidate_id,
        expected_revision=candidate.extraction.confirmation_revision,
        displayed_field_ids=tuple(field.field_id for field in fields),
        decisions=decisions,
        confirmed_at=clock(),
    )


def test_default_ttl_is_bounded_to_thirty_minutes() -> None:
    assert DEFAULT_TRANSIENT_IMAGE_TTL == timedelta(minutes=30)
    with pytest.raises(PhotoPipelineError):
        PhotoRecognitionPipeline(
            provider=FixtureProvider(),
            image_store=InMemoryTransientImageStore(),
            sink=MemorySink(),
            image_ttl=timedelta(minutes=31),
        )


def test_high_confidence_provider_output_still_requires_user_confirmation() -> None:
    clock = MutableClock()
    _, _, _, candidate = _candidate(clock=clock)

    assert candidate.extraction.record_state is RecordState.READY_FOR_USER_CONFIRMATION
    assert candidate.extraction.confirmation_revision == 0
    assert all(
        field.confirmation_state is FieldConfirmationState.UNCONFIRMED
        for field in iter_label_fields(candidate.extraction)
    )


def test_ambiguous_compound_routes_to_user_resolution_without_elemental_inference() -> None:
    clock = MutableClock()
    _, _, _, candidate = _candidate(
        clock=clock,
        provider=FixtureProvider("ambiguous_magnesium_citrate.json"),
    )

    assert candidate.extraction.record_state is RecordState.USER_RESOLUTION_REQUIRED
    row = candidate.extraction.rows[0]
    assert row.elemental_or_equivalent is None
    assert row.downstream_eligibility.value == "blocked_unresolved"


def test_provider_cannot_choose_confirmation_routing_state() -> None:
    clock = MutableClock()
    pipeline, store, _ = _pipeline(clock=clock, provider=InvalidStateProvider())
    capture = pipeline.capture(
        capture_id="invalid-provider-state",
        image=IMAGE_BYTES,
        media_type="image/png",
    )

    result = pipeline.extract(capture)

    assert isinstance(result, ManualEntryFallback)
    assert result.reason is ManualFallbackReason.PROVIDER_INVALID_OUTPUT
    with pytest.raises(TransientImageExpiredError):
        store.read(capture.image)


def test_provider_outage_degrades_to_manual_entry_and_deletes_image() -> None:
    clock = MutableClock()
    pipeline, store, _ = _pipeline(clock=clock, provider=UnavailableProvider())
    capture = pipeline.capture(
        capture_id="provider-outage",
        image=IMAGE_BYTES,
        media_type="image/png",
    )

    result = pipeline.extract(capture)

    assert isinstance(result, ManualEntryFallback)
    assert result.reason is ManualFallbackReason.PROVIDER_UNAVAILABLE
    assert result.record_state is RecordState.MANUAL_ENTRY_REQUIRED
    with pytest.raises(TransientImageExpiredError):
        store.read(capture.image)


def test_expired_source_requires_reupload_or_manual_entry() -> None:
    clock = MutableClock()
    pipeline, _, _ = _pipeline(clock=clock)
    capture = pipeline.capture(
        capture_id="expired-before-extraction",
        image=IMAGE_BYTES,
        media_type="image/png",
    )
    clock.advance(DEFAULT_TRANSIENT_IMAGE_TTL + timedelta(seconds=1))

    result = pipeline.extract(capture)

    assert isinstance(result, ManualEntryFallback)
    assert result.reason is ManualFallbackReason.SOURCE_EXPIRED


def test_project_candidate_identity_separates_captures_with_duplicate_provider_ids() -> None:
    clock = MutableClock()
    provider = FixtureProvider()
    pipeline, _, sink = _pipeline(clock=clock, provider=provider)
    first_capture = pipeline.capture(
        capture_id="capture-a",
        image=IMAGE_BYTES,
        media_type="image/png",
    )
    second_capture = pipeline.capture(
        capture_id="capture-b",
        image=IMAGE_BYTES,
        media_type="image/png",
    )

    first = pipeline.extract(first_capture)
    second = pipeline.extract(second_capture)

    assert not isinstance(first, ManualEntryFallback)
    assert not isinstance(second, ManualEntryFallback)
    assert first.extraction.extraction_id == second.extraction.extraction_id
    assert first.candidate_id != second.candidate_id

    first_record = pipeline.confirm_and_persist(
        first,
        _confirm_all_request(first, clock=clock),
    )
    second_record = pipeline.confirm_and_persist(
        second,
        _confirm_all_request(second, clock=clock),
    )

    assert isinstance(first_record, ConfirmedLabelRecord)
    assert isinstance(second_record, ConfirmedLabelRecord)
    assert first_record.idempotency_key != second_record.idempotency_key
    assert set(sink.records) == {
        first_record.idempotency_key,
        second_record.idempotency_key,
    }


def test_changed_reextraction_rejects_confirmation_bound_to_prior_candidate() -> None:
    clock = MutableClock()
    provider = ChangingCandidateProvider()
    pipeline, _, sink = _pipeline(clock=clock, provider=provider)
    capture = pipeline.capture(
        capture_id="same-capture",
        image=IMAGE_BYTES,
        media_type="image/png",
    )

    first = pipeline.extract(capture)
    assert not isinstance(first, ManualEntryFallback)
    stale_request = _confirm_all_request(first, clock=clock)

    second = pipeline.extract(capture)
    assert not isinstance(second, ManualEntryFallback)
    assert first.extraction.extraction_id == second.extraction.extraction_id
    assert first.extraction.confirmation_revision == second.extraction.confirmation_revision == 0
    assert tuple(field.field_id for field in iter_label_fields(first.extraction)) == tuple(
        field.field_id for field in iter_label_fields(second.extraction)
    )
    assert first.candidate_id != second.candidate_id

    with pytest.raises(StaleConfirmationError, match="candidate identity"):
        pipeline.confirm_and_persist(second, stale_request)

    assert sink.records == {}


def test_confirmation_rejects_stale_revision_and_incomplete_scope() -> None:
    clock = MutableClock()
    pipeline, _, _, candidate = _candidate(clock=clock)
    request = _confirm_all_request(candidate, clock=clock)

    with pytest.raises(StaleConfirmationError):
        pipeline.confirm_and_persist(
            candidate,
            ConfirmationRequest(
                expected_candidate_id=candidate.candidate_id,
                expected_revision=1,
                displayed_field_ids=request.displayed_field_ids,
                decisions=request.decisions,
                confirmed_at=clock(),
            ),
        )

    with pytest.raises(IncompleteConfirmationError):
        pipeline.confirm_and_persist(
            candidate,
            ConfirmationRequest(
                expected_candidate_id=candidate.candidate_id,
                expected_revision=0,
                displayed_field_ids=request.displayed_field_ids[:-1],
                decisions=request.decisions[:-1],
                confirmed_at=clock(),
            ),
        )


def test_confirmation_after_source_expiry_fails_closed() -> None:
    clock = MutableClock()
    pipeline, _, sink, candidate = _candidate(clock=clock)
    request = _confirm_all_request(candidate, clock=clock)
    clock.advance(DEFAULT_TRANSIENT_IMAGE_TTL + timedelta(seconds=1))

    result = pipeline.confirm_and_persist(candidate, request)

    assert isinstance(result, ManualEntryFallback)
    assert result.reason is ManualFallbackReason.SOURCE_EXPIRED
    assert sink.records == {}


def test_explicit_confirmation_persists_only_accepted_revision_and_deletes_pixels() -> None:
    clock = MutableClock()
    pipeline, store, sink, candidate = _candidate(clock=clock)

    record = pipeline.confirm_and_persist(
        candidate,
        _confirm_all_request(candidate, clock=clock),
    )

    assert isinstance(record, ConfirmedLabelRecord)
    assert record.extraction.record_state is RecordState.ACCEPTED_FOR_STORAGE
    assert record.extraction.confirmation_revision == 1
    assert sink.records == {record.idempotency_key: record}
    assert all(
        field.confirmation_state is FieldConfirmationState.USER_CONFIRMED
        for field in iter_label_fields(record.extraction)
    )
    with pytest.raises(TransientImageExpiredError):
        store.read(candidate.capture.image)


def test_user_correction_preserves_original_text_and_clears_provider_normalization() -> None:
    clock = MutableClock()
    pipeline, _, _, candidate = _candidate(clock=clock)
    fields = iter_label_fields(candidate.extraction)
    target = next(field for field in fields if field.field_id == "row:d3:quantity")
    decisions = []
    for field in fields:
        if field.field_id == target.field_id:
            decisions.append(
                FieldDecision(
                    field_id=field.field_id,
                    action=FieldDecisionAction.CORRECT,
                    corrected_raw_text="1200",
                )
            )
        else:
            decisions.append(
                FieldDecision(field_id=field.field_id, action=FieldDecisionAction.CONFIRM)
            )
    request = ConfirmationRequest(
        expected_candidate_id=candidate.candidate_id,
        expected_revision=0,
        displayed_field_ids=tuple(field.field_id for field in fields),
        decisions=tuple(decisions),
        confirmed_at=clock(),
    )

    record = pipeline.confirm_and_persist(candidate, request)

    assert isinstance(record, ConfirmedLabelRecord)
    corrected = next(
        field for field in iter_label_fields(record.extraction) if field.field_id == target.field_id
    )
    assert corrected.raw_text == "1200"
    assert corrected.normalized_candidate is None
    assert corrected.confidence is None
    assert corrected.confirmation_state is FieldConfirmationState.USER_CORRECTED
    assert corrected.corrections[0].original_raw_text == "1000"
    assert corrected.corrections[0].corrected_raw_text == "1200"


def test_exact_confirmation_retry_reuses_project_owned_idempotency_key() -> None:
    clock = MutableClock()
    sink = MemorySink(fail=True)
    pipeline, _, _, candidate = _candidate(clock=clock, sink=sink)
    request = _confirm_all_request(candidate, clock=clock)

    with pytest.raises(RuntimeError, match="persistence failed"):
        pipeline.confirm_and_persist(candidate, request)

    assert len(sink.attempted_keys) == 1
    first_key = sink.attempted_keys[0]
    assert first_key.startswith(f"{candidate.candidate_id}:confirmation:")

    sink.fail = False
    record = pipeline.confirm_and_persist(candidate, request)

    assert isinstance(record, ConfirmedLabelRecord)
    assert record.candidate_id == candidate.candidate_id
    assert record.idempotency_key == first_key
    assert sink.attempted_keys == [first_key, first_key]
    assert sink.records == {first_key: record}


def test_persistence_failure_retains_source_for_safe_retry() -> None:
    clock = MutableClock()
    failing_sink = MemorySink(fail=True)
    pipeline, store, _, candidate = _candidate(clock=clock, sink=failing_sink)

    with pytest.raises(RuntimeError, match="persistence failed"):
        pipeline.confirm_and_persist(
            candidate,
            _confirm_all_request(candidate, clock=clock),
        )

    assert store.read(candidate.capture.image) == IMAGE_BYTES
