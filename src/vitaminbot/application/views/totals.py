from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from vitaminbot.domain import Unit


class RegimenTotalsStatus(StrEnum):
    NO_SUPPLEMENTS = "no_supplements"
    NO_AGGREGATES = "no_aggregates"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class NutrientContributorView:
    tracked_instance_id: str
    name: str
    value: Decimal
    unit: Unit


@dataclass(frozen=True, slots=True)
class NutrientTotalsView:
    subject_id: str
    name: str
    total: Decimal | None
    unit: Unit | None
    is_complete: bool
    contributors: tuple[NutrientContributorView, ...]
    unresolved_contributor_count: int
    issue_codes: tuple[str, ...]
    suppressed_exact_repeat_count: int
    substance_key: str | None


@dataclass(frozen=True, slots=True)
class RegimenTotalsView:
    status: RegimenTotalsStatus
    nutrients: tuple[NutrientTotalsView, ...] = ()
    unresolved_contributor_count: int = 0
