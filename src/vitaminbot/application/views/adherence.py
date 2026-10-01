from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class AdherenceStatus(StrEnum):
    READY = "ready"
    MISSING_TIMEZONE = "missing_timezone"
    INVALID_SCHEDULE = "invalid_schedule"


@dataclass(frozen=True, slots=True)
class AdherenceWindowView:
    days: int
    start_date: date
    end_date: date
    planned: int
    taken: int
    skipped: int
    unresolved: int


@dataclass(frozen=True, slots=True)
class AdherenceView:
    status: AdherenceStatus
    windows: tuple[AdherenceWindowView, ...] = ()
