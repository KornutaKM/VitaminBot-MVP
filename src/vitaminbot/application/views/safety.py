from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from vitaminbot.application.safety_envelope import SafetyEnvelope


@dataclass(frozen=True, slots=True)
class SafetyView:
    envelopes: tuple[SafetyEnvelope, ...]
    context_revision: str
    show_applicability_profile: bool
    iron_scope_token: str | None = None


class SafetySourcesStatus(StrEnum):
    READY = "ready"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class SafetySourceItem:
    source_key: str
    title: str
    source_url: str
    version: str
    source_locator: str
    jurisdiction: str | None
    reference_type: str | None
    applicability_status: str | None
    scope_note: str | None


@dataclass(frozen=True, slots=True)
class SafetySourcesView:
    status: SafetySourcesStatus
    dataset_version: str
    sources: tuple[SafetySourceItem, ...] = ()
