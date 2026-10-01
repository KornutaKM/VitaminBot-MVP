from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class SupplementDetailStatus(StrEnum):
    READY = "ready"
    STALE = "stale"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class SupplementDetailView:
    status: SupplementDetailStatus
    instance_id: str | None = None
    revision: int | None = None
    name: str | None = None
    unit_label: str | None = None
    serving_basis_type: str | None = None
    units_per_serving: Decimal | None = None
    plan_quantity: Decimal | None = None
    plan_bucket: str | None = None
    plan_unit_label: str | None = None
