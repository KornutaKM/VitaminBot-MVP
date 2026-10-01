from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class QuickAddStep(StrEnum):
    NAME = "name"
    UNIT = "unit"
    QUANTITY = "quantity"
    BUCKET = "bucket"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    STALE = "stale"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class QuickAddView:
    step: QuickAddStep
    name: str | None = None
    unit_label: str | None = None
    quantity: Decimal | None = None
    bucket: str | None = None
    draft_id: str | None = None
    revision: int | None = None
    supplement_instance_id: str | None = None
    supplement_revision: int | None = None
