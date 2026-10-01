from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class SupplementsStatus(StrEnum):
    EMPTY = "empty"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class SupplementListItemView:
    token: str
    revision: int
    name: str
    unit_label: str
    lifecycle_status: str
    plan_quantity: Decimal | None
    plan_bucket: str | None
    inventory_remaining_units: Decimal | None
    inventory_needs_reconciliation: bool


@dataclass(frozen=True, slots=True)
class SupplementsView:
    status: SupplementsStatus
    items: tuple[SupplementListItemView, ...] = ()
