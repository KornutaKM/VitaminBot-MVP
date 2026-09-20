from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """Application settings loaded from the process environment."""

    app_env: str
    database_url: str | None
    redis_url: str
    telegram_bot_token: str | None

    @classmethod
    def from_environment(cls) -> Settings:
        """Build settings without embedding credentials in source code."""
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            database_url=os.getenv("DATABASE_URL"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        )
