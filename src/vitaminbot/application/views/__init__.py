"""Structured application-layer view models."""

from vitaminbot.application.views.adherence import (
    AdherenceStatus,
    AdherenceView,
    AdherenceWindowView,
)
from vitaminbot.application.views.add import QuickAddStep, QuickAddView
from vitaminbot.application.views.inventory import InventoryEditStep, InventoryEditView
from vitaminbot.application.views.supplement import (
    SupplementDetailStatus,
    SupplementDetailView,
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

__all__ = [
    "AdherenceStatus",
    "AdherenceView",
    "AdherenceWindowView",
    "InventoryEditStep",
    "InventoryEditView",
    "QuickAddStep",
    "QuickAddView",
    "SupplementDetailStatus",
    "SupplementDetailView",
    "TodayActionResult",
    "TodayActionStatus",
    "TodayOccurrenceState",
    "TodayOccurrenceView",
    "TodayStatus",
    "TodayView",
    "build_today_view",
]
