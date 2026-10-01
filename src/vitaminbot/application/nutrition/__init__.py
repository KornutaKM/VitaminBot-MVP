"""Confirmed composition, daily totals, and nutrient-reference application boundary."""

from vitaminbot.application.kir122 import KIR122Controller, VerticalView
from vitaminbot.application.kir146 import KIR146Controller, NutrientCardRenderer
from vitaminbot.application.views.composition import (
    CompositionNutrientOption,
    CompositionStep,
    CompositionSupplementView,
    CompositionView,
)
from vitaminbot.application.views.safety import (
    SafetyContributorView,
    SafetyEntryView,
    SafetySourcesStatus,
    SafetySourceView,
    SafetySourcesView,
    SafetyView,
)
from vitaminbot.application.views.totals import (
    NutrientContributorView,
    NutrientTotalsView,
    RegimenTotalsStatus,
    RegimenTotalsView,
)

NutritionController = KIR122Controller
NutrientReferenceController = KIR146Controller

__all__ = [
    "CompositionNutrientOption",
    "CompositionStep",
    "CompositionSupplementView",
    "CompositionView",
    "NutrientContributorView",
    "NutrientReferenceController",
    "NutrientTotalsView",
    "NutrientCardRenderer",
    "NutritionController",
    "RegimenTotalsStatus",
    "RegimenTotalsView",
    "SafetyContributorView",
    "SafetyEntryView",
    "SafetySourcesStatus",
    "SafetySourceView",
    "SafetySourcesView",
    "SafetyView",
    "VerticalView",
]
