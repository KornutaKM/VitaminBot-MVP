"""Intake planning, Today, and history application boundary."""

from vitaminbot.application.kir120 import KIR120Controller
from vitaminbot.application.views.adherence import (
    AdherenceStatus,
    AdherenceView,
    AdherenceWindowView,
)
from vitaminbot.application.views.history import (
    HistoryActionResult,
    HistoryActionStatus,
    HistoryCorrectionPreview,
    HistoryEntryView,
    HistoryStatus,
    HistoryView,
)
from vitaminbot.application.views.plan import (
    PlanActionResult,
    PlanActionStatus,
    PlanItemView,
    PlanStatus,
    PlanTimeEditView,
    PlanTimeInputError,
    PlanView,
)
from vitaminbot.application.views.today import (
    TodayActionResult,
    TodayActionStatus,
    TodayOccurrenceState,
    TodayOccurrenceView,
    TodayStatus,
    TodayView,
    build_today_view,
)

IntakeController = KIR120Controller

__all__ = [
    "AdherenceStatus",
    "AdherenceView",
    "AdherenceWindowView",
    "TodayActionResult",
    "TodayActionStatus",
    "HistoryActionResult",
    "HistoryActionStatus",
    "HistoryCorrectionPreview",
    "HistoryEntryView",
    "HistoryStatus",
    "HistoryView",
    "IntakeController",
    "PlanActionResult",
    "PlanActionStatus",
    "PlanItemView",
    "PlanStatus",
    "PlanTimeEditView",
    "PlanTimeInputError",
    "PlanView",
    "TodayOccurrenceState",
    "TodayOccurrenceView",
    "TodayStatus",
    "TodayView",
    "build_today_view",
]
