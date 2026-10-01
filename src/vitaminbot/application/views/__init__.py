"""Structured application-layer view models."""

from vitaminbot.application.views.account import (
    AccountDeletionStatus,
    AccountDeletionView,
    AccountExport,
)
from vitaminbot.application.views.add import QuickAddStep, QuickAddView
from vitaminbot.application.views.adherence import (
    AdherenceStatus,
    AdherenceView,
    AdherenceWindowView,
)
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
from vitaminbot.application.views.totals import (
    NutrientContributorView,
    NutrientTotalsView,
    RegimenTotalsStatus,
    RegimenTotalsView,
)

__all__ = [
    "AccountDeletionStatus",
    "AccountDeletionView",
    "AccountExport",
    "AdherenceStatus",
    "AdherenceView",
    "AdherenceWindowView",
    "InventoryEditStep",
    "InventoryEditView",
    "NutrientContributorView",
    "NutrientTotalsView",
    "QuickAddStep",
    "QuickAddView",
    "RegimenTotalsStatus",
    "RegimenTotalsView",
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
