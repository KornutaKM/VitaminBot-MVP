from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class CompositionStep(StrEnum):
    EMPTY = "empty"
    LIST = "list"
    SERVING_QUANTITY = "serving_quantity"
    NUTRIENT = "nutrient"
    AMOUNT = "amount"
    REVIEW = "review"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    STALE = "stale"
    DUPLICATE = "duplicate"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class CompositionSupplementView:
    instance_id: str
    token: str
    revision: int
    name: str
    unit_label: str
    serving_basis_type: str
    confirmed_count: int


@dataclass(frozen=True, slots=True)
class CompositionNutrientOption:
    substance_key: str
    name: str


@dataclass(frozen=True, slots=True)
class CompositionView:
    step: CompositionStep
    supplements: tuple[CompositionSupplementView, ...] = ()
    instance_id: str | None = None
    supplement_token: str | None = None
    supplement_revision: int | None = None
    name: str | None = None
    unit_label: str | None = None
    nutrients: tuple[CompositionNutrientOption, ...] = ()
    substance_key: str | None = None
    nutrient_name: str | None = None
    value: Decimal | None = None
    unit: str | None = None
    session_revision: int | None = None
    input_error: bool = False
