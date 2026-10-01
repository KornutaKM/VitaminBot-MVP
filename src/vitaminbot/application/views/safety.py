from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from vitaminbot.application.safety_envelope import (
    SafetyEvidenceState,
    SafetyStatus,
)


@dataclass(frozen=True, slots=True)
class SafetyContributorView:
    name: str
    normalized_amount: str


@dataclass(frozen=True, slots=True)
class SafetyEntryView:
    subject_name: str
    status: SafetyStatus
    classification: str
    known_facts: tuple[str, ...]
    unknown_facts: tuple[str, ...]
    withheld_conclusion: str | None
    warnings: tuple[str, ...]
    resolution_path: str | None
    escalation_path: str | None
    reference_type: str | None
    relation: str | None
    evidence_state: SafetyEvidenceState
    contributors: tuple[SafetyContributorView, ...]


@dataclass(frozen=True, slots=True)
class SafetyView:
    entries: tuple[SafetyEntryView, ...]
    source_revision: str
    has_applicability_profile: bool
    iron_scope_token: str | None = None


class SafetySourcesStatus(StrEnum):
    READY = "ready"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class SafetySourceView:
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
    sources: tuple[SafetySourceView, ...] = ()
