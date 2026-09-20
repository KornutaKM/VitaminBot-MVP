from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

import vitaminbot.telegram.reminders as reminder_module
from vitaminbot.application.kir116 import KIR116Controller, Screen
from vitaminbot.application.kir120 import KIR120Controller
from vitaminbot.persistence import migrate
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir120 import (
    AmbiguousLocalTime,
    InvalidOccurrenceState,
    KIR120Store,
    NonexistentLocalTime,
    RoutineTimes,
)
from vitaminbot.telegram.bot import build_application
from vitaminbot.telegram.reminders import TelegramReminderRunner


@pytest.fixture
def kir120_system() -> Iterator[tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str]]:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for KIR-120 integration tests")

    schema = f"kir120_{uuid4().hex}"
    migrate(database_url, schema=schema)
    kir116_store = KIR116Store(database_url, schema=schema)
    kir116 = KIR116Controller(kir116_store)
    kir120_store = KIR120Store(
        database_url,
        schema=schema,
        routine_times=RoutineTimes.from_strings("08:00", "13:00", "19:00"),
    )
    kir120 = KIR120Controller(
        kir120_store,
        later_delay=timedelta(minutes=30),
    )
    try:
        yield kir116, kir120, kir120_store, database_url, schema
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def _button(screen: Screen, label: str) -> str:
    for row in screen.rows:
        for button in row:
            if button.label == label:
                return button.callback_data
    raise AssertionError(f"button not found: {label}")


def _prepare_planned_user(
    kir116: KIR116Controller,
    store: KIR120Store,
    telegram_user_id: int,
    *,
    quantity: str = "2",
    name: str = "Example supplement",
) -> UUID:
    kir116.start(telegram_user_id)
    kir116.callback(telegram_user_id, "m", action_key=f"{telegram_user_id}:manual")
    unit = kir116.text(
        telegram_user_id,
        name,
        action_key=f"{telegram_user_id}:name",
    )
    serving = kir116.callback(
        telegram_user_id,
        _button(unit, "Capsule"),
        action_key=f"{telegram_user_id}:unit",
    )
    assert "How many capsule units" in serving.text
    review = kir116.text(
        telegram_user_id,
        "1",
        action_key=f"{telegram_user_id}:serving",
    )
    confirmed = kir116.callback(
        telegram_user_id,
        _button(review, "Confirm entry"),
        action_key=f"{telegram_user_id}:confirm",
    )
    plan = kir116.callback(
        telegram_user_id,
        _button(confirmed, "Add / edit plan"),
        action_key=f"{telegram_user_id}:plan",
    )
    assert "your plan, not a medical dose recommendation" in plan.text
    bucket = kir116.text(
        telegram_user_id,
        quantity,
        action_key=f"{telegram_user_id}:plan-quantity",
    )
    kir116.callback(
        telegram_user_id,
        _button(bucket, "Morning"),
        action_key=f"{telegram_user_id}:plan-save",
    )

    profile = kir116.profile(telegram_user_id)
    timezone_prompt = kir116.callback(
        telegram_user_id,
        _button(profile, "Edit timezone"),
        action_key=f"{telegram_user_id}:timezone-start",
    )
    assert "IANA timezone" in timezone_prompt.text
    updated = kir116.text(
        telegram_user_id,
        "Europe/Helsinki",
        action_key=f"{telegram_user_id}:timezone-save",
    )
    assert "Europe/Helsinki" in updated.text
    return store.ensure_user(telegram_user_id)


def _connect(
    database_url: str,
    schema: str,
) -> psycopg.Connection[tuple[object, ...]]:
    conn: psycopg.Connection[tuple[object, ...]] = psycopg.connect(
        database_url,
        autocommit=True,
    )
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    return conn


def test_today_delivery_and_taken_are_separate_and_idempotent(
    kir120_system: tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str],
) -> None:
    kir116, controller, store, database_url, schema = kir120_system
    telegram_user_id = 701001
    user_id = _prepare_planned_user(kir116, store, telegram_user_id)
    now = datetime(2026, 9, 20, 6, 0, tzinfo=UTC)

    screen = controller.today(telegram_user_id, now=now)
    assert "Today" in screen.text
    assert "2 capsule [pending]" in screen.text
    first = store.today(user_id, now)
    second = store.today(user_id, now)
    assert len(first) == 1
    assert first[0].occurrence_id == second[0].occurrence_id
    occurrence = first[0]

    claims = store.claim_due_reminders(now, "cycle:one")
    assert len(claims) == 1
    assert store.claim_due_reminders(now, "cycle:one") == ()
    validated = store.validate_claim(claims[0].delivery_id, now)
    assert validated is not None
    store.mark_delivery_sent(claims[0].delivery_id, "telegram-message-1", now)

    after_delivery = store.occurrence(user_id, occurrence.occurrence_id)
    assert after_delivery.state == "pending"

    taken = store.take(
        user_id,
        occurrence.occurrence_id,
        after_delivery.revision,
        "action:taken:one",
        now,
    )
    duplicate = store.take(
        user_id,
        occurrence.occurrence_id,
        after_delivery.revision,
        "action:taken:one",
        now,
    )
    assert taken.state == "taken"
    assert duplicate.revision == taken.revision
    assert store.claim_due_reminders(now + timedelta(minutes=1), "cycle:after-taken") == ()

    with _connect(database_url, schema) as conn:
        assert conn.execute("SELECT count(*) FROM intake_events").fetchone() == (1,)
        assert conn.execute(
            """
            SELECT event.consumption_units
            FROM intake_plan_heads AS head
            JOIN planned_intake_events AS event
              ON event.plan_id = head.plan_id
             AND event.plan_version = head.plan_version
            WHERE head.tracked_instance_id = %s
            """,
            (occurrence.instance_id,),
        ).fetchone() == (2,)


def test_later_is_one_off_bounded_and_never_mutates_template_amount(
    kir120_system: tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str],
) -> None:
    kir116, _, store, database_url, schema = kir120_system
    telegram_user_id = 701002
    user_id = _prepare_planned_user(
        kir116,
        store,
        telegram_user_id,
        quantity="1.5",
    )
    now = datetime(2026, 9, 20, 6, 0, tzinfo=UTC)
    occurrence = store.today(user_id, now)[0]
    later_until = now + timedelta(minutes=30)

    moved = store.later(
        user_id,
        occurrence.occurrence_id,
        occurrence.revision,
        "action:later:one",
        now,
        later_until,
    )
    assert moved.state == "pending"
    assert moved.later_count == 1
    assert moved.due_at == later_until
    assert store.claim_due_reminders(now + timedelta(minutes=10), "cycle:not-due") == ()

    with pytest.raises(InvalidOccurrenceState):
        store.later(
            user_id,
            occurrence.occurrence_id,
            moved.revision,
            "action:later:two",
            now + timedelta(minutes=31),
            now + timedelta(minutes=60),
        )

    claims = store.claim_due_reminders(later_until, "cycle:later-due")
    assert len(claims) == 1
    skipped = store.skip(
        user_id,
        occurrence.occurrence_id,
        moved.revision,
        "action:skip:one",
        later_until,
    )
    assert skipped.state == "skipped"
    assert store.validate_claim(claims[0].delivery_id, later_until) is None

    with _connect(database_url, schema) as conn:
        assert conn.execute("SELECT count(*) FROM intake_events").fetchone() == (0,)
        assert conn.execute(
            """
            SELECT event.consumption_units
            FROM intake_plan_heads AS head
            JOIN planned_intake_events AS event
              ON event.plan_id = head.plan_id
             AND event.plan_version = head.plan_version
            WHERE head.tracked_instance_id = %s
            """,
            (occurrence.instance_id,),
        ).fetchone() == (Decimal("1.5"),)


def test_restart_recovery_is_bounded_and_unknown_send_is_not_auto_retried(
    kir120_system: tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str],
) -> None:
    kir116, _, store, database_url, schema = kir120_system
    telegram_user_id = 701003
    user_id = _prepare_planned_user(kir116, store, telegram_user_id)
    now = datetime(2026, 9, 20, 6, 0, tzinfo=UTC)
    occurrence = store.today(user_id, now)[0]

    first = store.claim_due_reminders(
        now,
        "cycle:restart-a",
        lease=timedelta(minutes=2),
    )
    assert len(first) == 1

    restarted = KIR120Store(
        database_url,
        schema=schema,
        routine_times=RoutineTimes.from_strings("08:00", "13:00", "19:00"),
    )
    assert (
        restarted.claim_due_reminders(
            now + timedelta(seconds=30),
            "cycle:restart-b",
        )
        == ()
    )

    assert (
        restarted.claim_due_reminders(
            now + timedelta(minutes=3),
            "cycle:restart-c",
        )
        == ()
    )

    with _connect(database_url, schema) as conn:
        assert conn.execute(
            """
            SELECT status
            FROM reminder_delivery_attempts
            WHERE delivery_id = %s
            """,
            (first[0].delivery_id,),
        ).fetchone() == ("uncertain",)
        assert conn.execute(
            """
            SELECT state
            FROM reminder_occurrences
            WHERE occurrence_id = %s
            """,
            (occurrence.occurrence_id,),
        ).fetchone() == ("pending",)


def test_explicit_time_preserves_amount_and_dst_edges_fail_closed(
    kir120_system: tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str],
) -> None:
    kir116, _, store, database_url, schema = kir120_system
    telegram_user_id = 701004
    user_id = _prepare_planned_user(kir116, store, telegram_user_id, quantity="2")
    template = store.list_templates(user_id)[0]

    store.begin_explicit_time_edit(
        user_id,
        "explicit:begin",
        template.instance_id,
        template.plan_revision,
    )
    updated = store.save_explicit_time(
        user_id,
        "explicit:save",
        time(3, 30),
    )
    assert updated.schedule_kind == "explicit_time"
    assert updated.local_time == time(3, 30)
    assert updated.quantity == Decimal("2")

    with pytest.raises(AmbiguousLocalTime):
        store.materialize_user_date(user_id, date(2026, 10, 25))
    with pytest.raises(NonexistentLocalTime):
        store.materialize_user_date(user_id, date(2026, 3, 29))

    with _connect(database_url, schema) as conn:
        rows = conn.execute(
            """
            SELECT plan_version, consumption_units
            FROM planned_intake_events
            WHERE plan_id = %s
            ORDER BY plan_version
            """,
            (updated.plan_id,),
        ).fetchall()
    assert rows == [("1", Decimal("2")), ("2", Decimal("2"))]


def test_taken_correction_marks_intake_entered_in_error_and_requires_review(
    kir120_system: tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str],
) -> None:
    kir116, controller, store, database_url, schema = kir120_system
    telegram_user_id = 701005
    user_id = _prepare_planned_user(kir116, store, telegram_user_id)
    now = datetime(2026, 9, 20, 6, 0, tzinfo=UTC)
    occurrence = store.today(user_id, now)[0]

    taken = store.take(
        user_id,
        occurrence.occurrence_id,
        occurrence.revision,
        "correction:taken",
        now,
    )
    corrected = store.correct_latest(
        user_id,
        occurrence.occurrence_id,
        taken.revision,
        "correction:undo",
        now + timedelta(minutes=1),
    )
    assert corrected.state == "needs_review"
    assert store.claim_due_reminders(now + timedelta(minutes=2), "cycle:corrected") == ()

    history = store.history(user_id)
    assert any(entry.action_kind == "correction" for entry in history)
    assert any(entry.action_kind == "taken" and entry.entered_in_error for entry in history)
    history_screen = controller.history(telegram_user_id)
    assert "entered in error" in history_screen.text

    with _connect(database_url, schema) as conn:
        assert conn.execute(
            "SELECT entered_in_error_at IS NOT NULL FROM intake_events"
        ).fetchone() == (True,)


def test_controller_stale_callbacks_fail_closed_and_why_is_preference_only(
    kir120_system: tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str],
) -> None:
    kir116, controller, store, database_url, schema = kir120_system
    telegram_user_id = 701006
    user_id = _prepare_planned_user(kir116, store, telegram_user_id)
    now = datetime(2026, 9, 20, 6, 0, tzinfo=UTC)

    today = controller.today(telegram_user_id, now=now)
    all_callbacks = [button.callback_data for row in today.rows for button in row]
    assert all(len(value.encode("utf-8")) <= 64 for value in all_callbacks)
    assert all("Example supplement" not in value for value in all_callbacks)

    why_callback = next(value for value in all_callbacks if value.startswith("k120w:"))
    why = controller.callback(
        telegram_user_id,
        why_callback,
        action_key="controller:why",
        now=now,
    )
    assert "Timing source: Your preference." in why.text
    assert "No evidence-backed planning note is attached" in why.text

    taken_callback = next(value for value in all_callbacks if value.startswith("k120t:"))
    controller.callback(
        telegram_user_id,
        taken_callback,
        action_key="controller:taken",
        now=now,
    )
    stale = controller.callback(
        telegram_user_id,
        taken_callback,
        action_key="controller:stale-second-action",
        now=now,
    )
    assert "out of date or no longer valid" in stale.text

    with _connect(database_url, schema) as conn:
        assert conn.execute("SELECT count(*) FROM intake_events").fetchone() == (1,)
    assert store.occurrences_for_date(user_id, date(2026, 9, 20))[0].state == "taken"


def test_today_requires_explicit_timezone_and_bot_registers_kir120_commands(
    kir120_system: tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str],
) -> None:
    kir116, controller, store, _, _ = kir120_system
    telegram_user_id = 701007
    store.ensure_user(telegram_user_id)

    screen = controller.today(
        telegram_user_id,
        now=datetime(2026, 9, 20, 6, 0, tzinfo=UTC),
    )
    assert "needs your timezone" in screen.text
    assert _button(screen, "Open profile") == "pf"

    application = build_application(
        "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
        kir116,
        controller,
    )
    assert application.bot_data["kir116_controller"] is kir116
    assert application.bot_data["kir120_controller"] is controller
    assert len(application.handlers[0]) == 11


class _RecordingBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> object:
        self.sent.append(dict(kwargs))

        class _Message:
            message_id = 9001

        return _Message()


def test_runner_reminder_delivery_is_russian_first(
    kir120_system: tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kir116, _, store, _, _ = kir120_system
    telegram_user_id = 701010
    _prepare_planned_user(kir116, store, telegram_user_id)
    now = datetime(2026, 9, 20, 6, 0, tzinfo=UTC)

    class _FixedClock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return now

    monkeypatch.setattr(reminder_module, "datetime", _FixedClock)
    bot = _RecordingBot()
    delivered = asyncio.run(TelegramReminderRunner(store).run_once(bot, now=now))

    assert delivered == 1
    assert len(bot.sent) == 1
    payload = bot.sent[0]
    text = payload["text"]
    assert isinstance(text, str)
    assert text.startswith("Напоминание")
    assert "Example supplement: 2 капсула" in text
    assert "Количество взято из вашего подтверждённого плана." in text
    assert "Доставка напоминания не означает, что приём состоялся." in text
    assert "Reminder" not in text

    markup = payload["reply_markup"]
    rows = getattr(markup, "inline_keyboard")
    buttons = [button for row in rows for button in row]
    labels = [button.text for button in buttons]
    assert any(label.startswith("Принято · ") for label in labels)
    assert "Позже" in labels
    assert "Пропустить" in labels
    assert any(label.startswith("Почему? · ") for label in labels)

    callbacks = [button.callback_data for button in buttons]
    assert any(value.startswith("k120t:") for value in callbacks)
    assert any(value.startswith("k120l:") for value in callbacks)
    assert any(value.startswith("k120s:") for value in callbacks)
    assert any(value.startswith("k120w:") for value in callbacks)


@pytest.mark.parametrize("late_action", ["skip", "take_then_correct"])
def test_runner_revalidates_group_after_initial_grouping_before_send(
    kir120_system: tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str],
    monkeypatch: pytest.MonkeyPatch,
    late_action: str,
) -> None:
    kir116, _, store, _, _ = kir120_system
    telegram_user_id = 701008
    user_id = _prepare_planned_user(kir116, store, telegram_user_id)
    now = datetime.now(UTC)
    occurrence = store.today(user_id, now)[0]
    original_validate = store.validate_claim
    validation_calls = 0

    def validate_with_late_action(delivery_id: str, validation_now: datetime) -> object:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 2:
            current = store.occurrence(user_id, occurrence.occurrence_id)
            if late_action == "skip":
                store.skip(
                    user_id,
                    occurrence.occurrence_id,
                    current.revision,
                    "race:skip",
                    validation_now,
                )
            else:
                taken = store.take(
                    user_id,
                    occurrence.occurrence_id,
                    current.revision,
                    "race:taken",
                    validation_now,
                )
                store.correct_latest(
                    user_id,
                    occurrence.occurrence_id,
                    taken.revision,
                    "race:correction",
                    validation_now,
                )
        return original_validate(delivery_id, validation_now)

    monkeypatch.setattr(store, "validate_claim", validate_with_late_action)
    bot = _RecordingBot()
    delivered = asyncio.run(TelegramReminderRunner(store).run_once(bot, now=now))

    assert validation_calls == 2
    assert delivered == 0
    assert bot.sent == []


def test_runner_suppresses_group_when_claim_lease_expires_before_send(
    kir120_system: tuple[KIR116Controller, KIR120Controller, KIR120Store, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kir116, _, store, database_url, schema = kir120_system
    telegram_user_id = 701009
    user_id = _prepare_planned_user(kir116, store, telegram_user_id)
    now = datetime.now(UTC)
    occurrence = store.today(user_id, now)[0]

    class _ExpiredClock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return now + timedelta(minutes=3)

    monkeypatch.setattr(reminder_module, "datetime", _ExpiredClock)
    bot = _RecordingBot()
    delivered = asyncio.run(TelegramReminderRunner(store).run_once(bot, now=now))

    assert delivered == 0
    assert bot.sent == []
    with _connect(database_url, schema) as conn:
        assert conn.execute(
            """
            SELECT status
            FROM reminder_delivery_attempts
            WHERE occurrence_id = %s
            """,
            (occurrence.occurrence_id,),
        ).fetchone() == ("cancelled",)
