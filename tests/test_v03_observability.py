from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import psycopg
import pytest

import vitaminbot.telegram.reminders as reminder_module
from vitaminbot.application.intake import TodayActionResult, TodayActionStatus
from vitaminbot.observability import LoggingMetricsSink, NULL_METRICS
from vitaminbot.persistence.kir120 import DeliveryClaim
from vitaminbot.telegram.bot import _callback
from vitaminbot.telegram.reminders import TelegramReminderRunner


class _RecordingMetrics:
    def __init__(self) -> None:
        self.counters: list[tuple[str, int]] = []
        self.observations: list[tuple[str, float]] = []

    def increment(self, name: str, value: int = 1) -> None:
        self.counters.append((name, value))

    def observe(self, name: str, value: float) -> None:
        self.observations.append((name, value))


class _ReminderStore:
    def __init__(self, claim: DeliveryClaim) -> None:
        self.claim = claim
        self.sent: list[str] = []
        self.failed: list[str] = []

    def materialize_all(self, now: datetime) -> tuple[str, ...]:
        del now
        return ()

    def claim_due_reminders(
        self,
        now: datetime,
        execution_key: str,
    ) -> tuple[DeliveryClaim, ...]:
        del now, execution_key
        return (self.claim,)

    def validate_claim(
        self,
        delivery_id: str,
        now: datetime,
    ) -> DeliveryClaim | None:
        del now
        return self.claim if delivery_id == self.claim.delivery_id else None

    def mark_delivery_failed(
        self,
        delivery_id: str,
        failure_code: str,
        completed_at: datetime,
    ) -> None:
        del failure_code, completed_at
        self.failed.append(delivery_id)

    def mark_delivery_sent(
        self,
        delivery_id: str,
        telegram_message_id: str,
        completed_at: datetime,
    ) -> None:
        del telegram_message_id, completed_at
        self.sent.append(delivery_id)


class _SuccessfulBot:
    async def send_message(self, **kwargs: object) -> object:
        del kwargs
        return SimpleNamespace(message_id=9001)


class _FailingBot:
    async def send_message(self, **kwargs: object) -> object:
        del kwargs
        raise RuntimeError("telegram unavailable")


def _claim(now: datetime) -> DeliveryClaim:
    return DeliveryClaim(
        delivery_id="delivery-observability",
        occurrence_id="occ-observability",
        occurrence_revision=4,
        telegram_user_id=700001,
        name="Private supplement name",
        quantity=Decimal("2"),
        unit_label="capsule",
        schedule_label="morning",
        due_at=now - timedelta(seconds=45),
        later_count=0,
    )


def test_logging_metrics_are_numeric_and_do_not_accept_context_fields() -> None:
    logger = logging.getLogger("vitaminbot.tests.metrics")
    sink = LoggingMetricsSink(logger)
    logger.setLevel(logging.INFO)

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    capture = _Capture()
    logger.addHandler(capture)
    try:
        sink.increment("reminders_due", 3)
        sink.observe("reminder_lag_seconds", 12.5)
    finally:
        logger.removeHandler(capture)

    assert len(records) == 2
    payloads = []
    for record in records:
        message = record.getMessage()
        assert message.startswith("vitaminbot_metric ")
        payload = json.loads(message.removeprefix("vitaminbot_metric "))
        assert set(payload) == {"kind", "metric", "value"}
        payloads.append(payload)

    assert payloads[0] == {
        "kind": "counter",
        "metric": "reminders_due",
        "value": 3.0,
    }
    assert payloads[1] == {
        "kind": "gauge",
        "metric": "reminder_lag_seconds",
        "value": 12.5,
    }


def test_reminder_runner_emits_due_sent_and_lag_without_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    claim = _claim(now)
    store = _ReminderStore(claim)
    metrics = _RecordingMetrics()

    class _FixedClock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            del tz
            return now

    monkeypatch.setattr(reminder_module, "datetime", _FixedClock)
    runner = TelegramReminderRunner(store, metrics=metrics)  # type: ignore[arg-type]
    delivered = asyncio.run(runner.run_once(_SuccessfulBot(), now=now))  # type: ignore[arg-type]

    assert delivered == 1
    assert store.sent == [claim.delivery_id]
    assert metrics.counters == [("reminders_due", 1), ("reminders_sent", 1)]
    assert metrics.observations == [("reminder_lag_seconds", 45.0)]


def test_reminder_runner_emits_failed_delivery_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    claim = _claim(now)
    store = _ReminderStore(claim)
    metrics = _RecordingMetrics()

    class _FixedClock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            del tz
            return now

    monkeypatch.setattr(reminder_module, "datetime", _FixedClock)
    runner = TelegramReminderRunner(store, metrics=metrics)  # type: ignore[arg-type]
    delivered = asyncio.run(runner.run_once(_FailingBot(), now=now))  # type: ignore[arg-type]

    assert delivered == 0
    assert store.failed == [claim.delivery_id]
    assert metrics.counters == [("reminders_due", 1), ("reminders_failed", 1)]


def test_worker_counts_database_cycle_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = _RecordingMetrics()

    class _DatabaseFailureStore:
        def materialize_all(self, now: datetime) -> tuple[str, ...]:
            del now
            raise psycopg.OperationalError("database unavailable")

    async def _cancel_after_cycle(seconds: float) -> None:
        del seconds
        raise asyncio.CancelledError

    monkeypatch.setattr(reminder_module.asyncio, "sleep", _cancel_after_cycle)
    runner = TelegramReminderRunner(
        _DatabaseFailureStore(),  # type: ignore[arg-type]
        metrics=metrics,
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(runner.run_forever(_SuccessfulBot()))  # type: ignore[arg-type]

    assert metrics.counters == [("db_transaction_errors", 1)]


def test_stale_today_callback_increments_only_numeric_metric() -> None:
    metrics = _RecordingMetrics()

    class _ScheduleController:
        def apply_today_action_view(
            self,
            telegram_user_id: int,
            data: str,
            *,
            action_key: str,
        ) -> TodayActionResult:
            del telegram_user_id, data, action_key
            return TodayActionResult(status=TodayActionStatus.STALE)

    class _Query:
        id = "query-1"
        data = "k120t:occurrence:3"

        def __init__(self) -> None:
            self.rendered_text: str | None = None

        async def answer(self) -> None:
            return None

        async def edit_message_text(
            self,
            text: str,
            *,
            reply_markup: object = None,
        ) -> None:
            del reply_markup
            self.rendered_text = text

    query = _Query()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=700002),
        callback_query=query,
        effective_chat=None,
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "kir120_controller": _ScheduleController(),
                "metrics": metrics,
            }
        ),
        bot=SimpleNamespace(),
    )

    asyncio.run(_callback(update, context))  # type: ignore[arg-type]

    assert metrics.counters == [("stale_callback_count", 1)]
    assert query.rendered_text is not None
    assert "Повторная отметка о приёме не записана." in query.rendered_text


def test_null_metrics_sink_is_safe_default() -> None:
    NULL_METRICS.increment("reminders_failed", 2)
    NULL_METRICS.observe("reminder_lag_seconds", 0.0)
