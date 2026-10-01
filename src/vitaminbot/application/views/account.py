from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AccountDeletionStatus(StrEnum):
    CONFIRM = "confirm"
    DELETED = "deleted"
    CANCELLED = "cancelled"
    STALE = "stale"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class AccountDeletionView:
    status: AccountDeletionStatus
    token: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccountExport:
    filename: str
    payload: bytes
