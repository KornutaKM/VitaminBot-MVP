from __future__ import annotations

import asyncio

from telegram import Bot

from vitaminbot.config import Settings
from vitaminbot.persistence.kir120 import KIR120Store, RoutineTimes
from vitaminbot.telegram.reminders import TelegramReminderRunner


def build_runner(settings: Settings) -> TelegramReminderRunner:
    if settings.database_url is None:
        raise ValueError("DATABASE_URL is required")

    routine_times = RoutineTimes.from_strings(
        settings.reminder_morning_time,
        settings.reminder_day_time,
        settings.reminder_evening_time,
    )
    store = KIR120Store(
        settings.database_url,
        routine_times=routine_times,
    )
    return TelegramReminderRunner(
        store,
        poll_seconds=settings.reminder_poll_seconds,
    )


async def run_worker(settings: Settings) -> None:
    if settings.telegram_bot_token is None:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")

    runner = build_runner(settings)
    async with Bot(settings.telegram_bot_token) as bot:
        await runner.run_forever(bot)


def main() -> None:
    settings = Settings.from_environment()
    if settings.telegram_bot_token is None:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL is required")

    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
