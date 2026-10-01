"""Supplement onboarding and lifecycle application boundary.

This module provides semantic imports while the accepted implementation is
migrated out of ticket-oriented modules.
"""

from vitaminbot.application.kir116 import Button, KIR116Controller, Screen
from vitaminbot.application.views.add import QuickAddStep, QuickAddView

SupplementController = KIR116Controller

__all__ = [
    "Button",
    "QuickAddStep",
    "QuickAddView",
    "Screen",
    "SupplementController",
]
