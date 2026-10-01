"""Confirmed composition, daily totals, and nutrient-reference application boundary."""

from vitaminbot.application.kir122 import KIR122Controller, VerticalView
from vitaminbot.application.kir146 import KIR146Controller, NutrientCardRenderer

NutritionController = KIR122Controller
NutrientReferenceController = KIR146Controller

__all__ = [
    "NutrientReferenceController",
    "NutrientCardRenderer",
    "NutritionController",
    "VerticalView",
]
