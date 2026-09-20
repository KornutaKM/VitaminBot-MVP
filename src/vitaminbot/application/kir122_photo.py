from __future__ import annotations

from uuid import UUID

from vitaminbot.persistence.kir122 import KIR122Store
from vitaminbot.recognition.pipeline import ConfirmedLabelRecord


class KIR122ConfirmedLabelSink:
    """User-bound durable sink for accepted KIR-117 confirmed label records."""

    def __init__(self, store: KIR122Store, user_id: UUID) -> None:
        self._store = store
        self._user_id = user_id

    def persist(self, record: ConfirmedLabelRecord) -> None:
        provider = record.provenance.provider
        self._store.persist_confirmed_label(
            self._user_id,
            idempotency_key=record.idempotency_key,
            candidate_id=record.candidate_id,
            extraction_payload=record.extraction.to_payload(),
            provider_key=provider.provider_key,
            model_revision=provider.model_revision,
            adapter_revision=provider.adapter_revision,
            prompt_revision=provider.prompt_revision,
            schema_revision=provider.schema_revision,
            preprocessing_revision=provider.preprocessing_revision,
            image_sha256=record.provenance.image_sha256,
            raw_response_sha256=record.provenance.raw_response_sha256,
            requested_at=record.provenance.requested_at,
            completed_at=record.provenance.completed_at,
            confirmed_at=record.confirmed_at,
        )
