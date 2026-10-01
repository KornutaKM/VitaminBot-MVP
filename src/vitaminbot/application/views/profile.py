from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class ProfileView:
    timezone: str | None
    locale: str | None
    revision: int
    show_applicability_context: bool = False


class ProfileEditStep(StrEnum):
    TIMEZONE = "timezone"
    LOCALE = "locale"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    STALE = "stale"
    INVALID = "invalid"


class ProfileInputError(StrEnum):
    INVALID_TIMEZONE = "invalid_timezone"
    INVALID_LOCALE = "invalid_locale"


@dataclass(frozen=True, slots=True)
class ProfileEditView:
    step: ProfileEditStep
    profile: ProfileView | None = None
    expected_revision: int | None = None
    error: ProfileInputError | None = None
