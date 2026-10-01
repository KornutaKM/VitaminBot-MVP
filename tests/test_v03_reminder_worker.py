from __future__ import annotations

import asyncio

import pytest

import vitaminbot.telegram.reminder_worker as worker_module
from vitaminbot.config import Settings
from vitaminbot.telegram.reminder_worker import build_runner, run_worker


def _settings(*, token: str | None = "test-token", database_url: str | None = "postgresql://test") -> Settings:
    return Settings(
        app_env="test",
        database_url=database_url,
        redis_url="redis://unused",
        telegram_bot_token=token,
        reminder_morning_time="08:00",
        reminder_day_time="13:00",
        reminder_evening_time="19:00",
        reminder_later_minutes=30,
        reminder_poll_seconds=17,
    )


def test_build_runner_uses_worker_poll_interval_without_connecting() -> None:
    runner = build_runner(_settings())

    assert runner._poll_seconds == 17


def test_build_runner_requires_database_url() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        build_runner(_settings(database_url=None))


def test_run_worker_owns_bot_lifecycle_and_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class _Bot:
        def __init__(self, token: str) -> None:
            assert token == "test-token"

        async def __aenter__(self) -> _Bot:
            events.append("bot-enter")
            return self

        async def __aexit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            events.append("bot-exit")

    class _Runner:
        async def run_forever(self, bot: object) -> None:
            assert isinstance(bot, _Bot)
            events.append("runner")

    monkeypatch.setattr(worker_module, "Bot", _Bot)
    monkeypatch.setattr(worker_module, "build_runner", lambda settings: _Runner())

    asyncio.run(run_worker(_settings()))

    assert events == ["bot-enter", "runner", "bot-exit"]


def test_run_worker_requires_bot_token() -> None:
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN is required"):
        asyncio.run(run_worker(_settings(token=None)))
