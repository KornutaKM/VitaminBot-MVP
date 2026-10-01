from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from enum import StrEnum


class PlanStatus(StrEnum):
    EMPTY = "empty"
    READY = "ready"


class PlanActionStatus(StrEnum):
    APPLIED = "applied"
    INPUT_REQUIRED = "input_required"
    CANCELLED = "cancelled"
    STALE = "stale"
    INVALID = "invalid"


class PlanTimeInputError(StrEnum):
    INVALID_FORMAT = "invalid_format"


@dataclass(frozen=True, slots=True)
class PlanItemView:
    instance_id: str
    name: str
    plan_revision: int
    quantity: Decimal
    unit_label: str
    schedule_kind: str
    schedule_label: str | None
    local_time: time | None


@dataclass(frozen=True, slots=True)
class PlanView:
    status: PlanStatus
    items: tuple[PlanItemView, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanTimeEditView:
    instance_id: str
    name: str
    expected_plan_revision: int
    error: PlanTimeInputError | None = None


@dataclass(frozen=True, slots=True)
class PlanActionResult:
    status: PlanActionStatus
    view: PlanView | None = None
    edit: PlanTimeEditView | None = None
