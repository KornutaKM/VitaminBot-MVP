"""Just-in-time applicability context application boundary."""

from vitaminbot.application.kir174 import (
    ApplicabilityField,
    BoundApplicabilityContext,
    KIR174Controller,
)

ApplicabilityController = KIR174Controller

__all__ = [
    "ApplicabilityController",
    "ApplicabilityField",
    "BoundApplicabilityContext",
]
