"""Intake planning, Today, and history application boundary."""

from vitaminbot.application.kir120 import KIR120Controller
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
    "TodayActionResult",
    "TodayActionStatus",
    "IntakeController",
    "TodayOccurrenceState",
    "TodayOccurrenceView",
    "TodayStatus",
    "TodayView",
    "build_today_view",
]
