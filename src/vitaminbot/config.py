from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Application settings loaded from the process environment."""

    app_env: str
    database_url: str | None
    redis_url: str
    telegram_bot_token: str | None
    reminder_morning_time: str
    reminder_day_time: str
    reminder_evening_time: str
    reminder_later_minutes: int
    reminder_poll_seconds: int

    @classmethod
    def from_environment(cls) -> Settings:
        """Build settings without embedding credentials in source code."""
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            database_url=os.getenv("DATABASE_URL"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            reminder_morning_time=os.getenv("REMINDER_MORNING_TIME", "08:00"),
            reminder_day_time=os.getenv("REMINDER_DAY_TIME", "13:00"),
            reminder_evening_time=os.getenv("REMINDER_EVENING_TIME", "19:00"),
            reminder_later_minutes=_positive_int_env("REMINDER_LATER_MINUTES", 30),
            reminder_poll_seconds=_positive_int_env("REMINDER_POLL_SECONDS", 30),
        )
