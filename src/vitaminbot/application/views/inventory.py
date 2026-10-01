from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InventoryEditStep(StrEnum):
    QUANTITY = "quantity"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    STALE = "stale"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class InventoryEditView:
    step: InventoryEditStep
    name: str | None = None
    unit_label: str | None = None
    supplement_instance_id: str | None = None
    supplement_revision: int | None = None
