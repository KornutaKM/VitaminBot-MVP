from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from enum import StrEnum

from vitaminbot.persistence.kir120 import OccurrenceRecord


class TodayStatus(StrEnum):
    READY = "ready"
    MISSING_TIMEZONE = "missing_timezone"
    AMBIGUOUS_LOCAL_TIME = "ambiguous_local_time"
    INVALID_SCHEDULE = "invalid_schedule"


class TodayActionStatus(StrEnum):
    APPLIED = "applied"
    STALE = "stale"
    INVALID = "invalid"


class TodayOccurrenceState(StrEnum):
    PENDING = "pending"
    TAKEN = "taken"
    SKIPPED = "skipped"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True, slots=True)
class TodayOccurrenceView:
    occurrence_id: str
    revision: int
    name: str
    quantity: Decimal
    unit_label: str
    schedule_kind: str
    schedule_label: str
    scheduled_local_time: time
    state: TodayOccurrenceState
    can_take: bool
    can_later: bool
    can_skip: bool
    can_explain: bool


@dataclass(frozen=True, slots=True)
class TodayView:
    status: TodayStatus
    local_date: date | None = None
    occurrences: tuple[TodayOccurrenceView, ...] = ()


@dataclass(frozen=True, slots=True)
class TodayActionResult:
    status: TodayActionStatus
    view: TodayView | None = None


def build_today_view(occurrences: tuple[OccurrenceRecord, ...]) -> TodayView:
    local_dates = {occurrence.local_date for occurrence in occurrences}
    if len(local_dates) > 1:
        raise ValueError("Today occurrences must belong to one local date")

    views = tuple(_occurrence_view(occurrence) for occurrence in occurrences)
    local_date = next(iter(local_dates), None)
    return TodayView(
        status=TodayStatus.READY,
        local_date=local_date,
        occurrences=views,
    )


def _occurrence_view(occurrence: OccurrenceRecord) -> TodayOccurrenceView:
    state = TodayOccurrenceState(occurrence.state)
    actionable = state in {
        TodayOccurrenceState.PENDING,
        TodayOccurrenceState.NEEDS_REVIEW,
    }
    return TodayOccurrenceView(
        occurrence_id=occurrence.occurrence_id,
        revision=occurrence.revision,
        name=occurrence.name,
        quantity=occurrence.quantity,
        unit_label=occurrence.unit_label,
        schedule_kind=occurrence.schedule_kind,
        schedule_label=occurrence.schedule_label,
        scheduled_local_time=occurrence.scheduled_local_time,
        state=state,
        can_take=actionable,
        can_later=state is TodayOccurrenceState.PENDING and occurrence.later_count == 0,
        can_skip=actionable,
        can_explain=True,
    )
