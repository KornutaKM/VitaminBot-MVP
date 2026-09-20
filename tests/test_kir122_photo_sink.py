from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from vitaminbot.application.kir122_photo import KIR122ConfirmedLabelSink
from vitaminbot.persistence import migrate
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir122 import KIR122Store
from vitaminbot.recognition import (
    PresenceState,
    RecordState,
    SourceAsset,
    validate_extraction_payload,
)
from vitaminbot.recognition.pipeline import (
    ConfirmationRequest,
    FieldDecision,
    FieldDecisionAction,
    InMemoryTransientImageStore,
    ManualEntryFallback,
    PhotoRecognitionPipeline,
    ProviderExtractionResult,
    ProviderRevision,
    RecognitionProvider,
    TransientImageExpiredError,
    iter_label_fields,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "recognition" / "vitamin_d_iu.json"
_IMAGE_BYTES = b"kir122-provider-neutral-photo-smoke"


class _FixtureProvider(RecognitionProvider):
    def extract(
        self,
        image: bytes,
        *,
        media_type: str,
        source_asset: SourceAsset,
    ) -> ProviderExtractionResult:
        assert image == _IMAGE_BYTES
        assert media_type == "image/png"
        raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        payload = cast(dict[str, object], raw)
        payload["source_assets"] = [source_asset.to_payload()]
        payload["record_state"] = RecordState.EXTRACTED_UNCONFIRMED.value
        payload["confirmation_revision"] = 0
        return ProviderExtractionResult(
            extraction=validate_extraction_payload(payload),
            revision=ProviderRevision(
                provider_key="fixture-only",
                model_revision="fixture-model-v1",
                adapter_revision="adapter-v1",
                prompt_revision="prompt-v1",
                schema_revision="1.0.0",
                preprocessing_revision="none-v1",
            ),
            raw_response_sha256="0" * 64,
        )


@pytest.fixture
def photo_stack() -> Iterator[tuple[str, UUID, KIR122Store]]:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for KIR-122 photo sink tests")

    schema = f"kir122_photo_{uuid4().hex}"
    migrate(database_url, schema=schema)
    base_store = KIR116Store(database_url, schema=schema)
    user_id = base_store.ensure_user(122003)
    try:
        yield schema, user_id, KIR122Store(database_url, schema=schema)
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def test_confirmed_photo_record_persists_idempotently_without_source_pixels(
    photo_stack: tuple[str, UUID, KIR122Store],
) -> None:
    schema, user_id, store = photo_stack
    clock_value = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    image_store = InMemoryTransientImageStore(clock=lambda: clock_value)
    sink = KIR122ConfirmedLabelSink(store, user_id)
    pipeline = PhotoRecognitionPipeline(
        provider=_FixtureProvider(),
        image_store=image_store,
        sink=sink,
        clock=lambda: clock_value,
    )

    capture = pipeline.capture(
        capture_id="capture-kir122",
        image=_IMAGE_BYTES,
        media_type="image/png",
    )
    candidate = pipeline.extract(capture)
    assert not isinstance(candidate, ManualEntryFallback)

    fields = iter_label_fields(candidate.extraction)
    request = ConfirmationRequest(
        expected_candidate_id=candidate.candidate_id,
        expected_revision=candidate.extraction.confirmation_revision,
        displayed_field_ids=tuple(field.field_id for field in fields),
        decisions=tuple(
            FieldDecision(
                field_id=field.field_id,
                action=(
                    FieldDecisionAction.CONFIRM
                    if field.presence_state is PresenceState.PRESENT
                    else FieldDecisionAction.CONFIRM_UNKNOWN
                ),
            )
            for field in fields
        ),
        confirmed_at=clock_value,
    )
    record = pipeline.confirm_and_persist(candidate, request)
    assert not isinstance(record, ManualEntryFallback)

    # The KIR-117 pipeline deletes transient pixels only after the durable sink succeeds.
    with pytest.raises(TransientImageExpiredError):
        image_store.read(capture.image)

    # An exact persistence retry is a no-op, not a duplicate row.
    sink.persist(record)

    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as conn:
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        row = conn.execute(
            """
            SELECT
                count(*) AS row_count,
                min(image_sha256) AS image_sha256,
                min(provider_key) AS provider_key
            FROM kir122_confirmed_label_records
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] == capture.image.sha256_hex
    assert row[2] == "fixture-only"
