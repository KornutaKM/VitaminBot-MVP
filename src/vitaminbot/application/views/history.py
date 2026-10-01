from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class HistoryStatus(StrEnum):
    EMPTY = "empty"
    READY = "ready"


class HistoryActionStatus(StrEnum):
    PREVIEW = "preview"
    APPLIED = "applied"
    STALE = "stale"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class HistoryEntryView:
    occurrence_id: str
    occurrence_revision: int
    action_kind: str
    name: str
    quantity: Decimal
    unit_label: str
    created_at: datetime
    entered_in_error: bool
    correctable: bool


@dataclass(frozen=True, slots=True)
class HistoryView:
    status: HistoryStatus
    entries: tuple[HistoryEntryView, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoryCorrectionPreview:
    occurrence_id: str
    expected_revision: int
    name: str
    state: str


@dataclass(frozen=True, slots=True)
class HistoryActionResult:
    status: HistoryActionStatus
    view: HistoryView | None = None
    preview: HistoryCorrectionPreview | None = None
