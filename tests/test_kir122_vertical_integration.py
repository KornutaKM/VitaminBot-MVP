from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from vitaminbot.application.kir116 import KIR116Controller, Screen
from vitaminbot.application.kir120 import KIR120Controller
from vitaminbot.application.kir122 import KIR122Controller
from vitaminbot.persistence import migrate
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir120 import KIR120Store, RoutineTimes
from vitaminbot.persistence.kir122 import KIR122Store
from vitaminbot.telegram.presentation import localize_operational_screen


@pytest.fixture
def vertical_stack() -> Iterator[
    tuple[KIR116Controller, KIR120Controller, KIR122Controller, KIR116Store]
]:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for KIR-122 integration tests")

    schema = f"kir122_{uuid4().hex}"
    migrate(database_url, schema=schema)
    base_store = KIR116Store(database_url, schema=schema)
    base = KIR116Controller(base_store)
    schedule = KIR120Controller(
        KIR120Store(
            database_url,
            schema=schema,
            routine_times=RoutineTimes.from_strings("08:00", "13:00", "20:00"),
        )
    )
    vertical = KIR122Controller(
        base_store=base_store,
        store=KIR122Store(database_url, schema=schema),
    )
    try:
        yield base, schedule, vertical, base_store
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def _button(screen: Screen, label: str) -> str:
    for row in screen.rows:
        for button in row:
            if button.label == label:
                return button.callback_data
    raise AssertionError(f"button not found: {label}")


def _callback_with_prefix(screen: Screen, prefix: str) -> str:
    for row in screen.rows:
        for button in row:
            if button.callback_data.startswith(prefix):
                return button.callback_data
    raise AssertionError(f"callback not found: {prefix}")


def _create_clean_account(
    base: KIR116Controller,
    telegram_user_id: int,
) -> None:
    start = base.start(telegram_user_id)
    add = base.callback(
        telegram_user_id,
        _button(start, "Add first supplement"),
        action_key="cb:start:add",
    )
    manual = base.callback(
        telegram_user_id,
        _button(add, "Enter manually"),
        action_key="cb:add:manual",
    )
    assert "Send the supplement name" in manual.text

    units = base.text(
        telegram_user_id,
        "Example Magnesium",
        action_key="msg:supplement-name",
    )
    serving = base.callback(
        telegram_user_id,
        _button(units, "Capsule"),
        action_key="cb:unit:capsule",
    )
    assert "How many capsule units" in serving.text

    review = base.text(
        telegram_user_id,
        "2",
        action_key="msg:serving-quantity",
    )
    confirmed = base.callback(
        telegram_user_id,
        _button(review, "Confirm entry"),
        action_key="cb:confirm-supplement",
    )
    plan_prompt = base.callback(
        telegram_user_id,
        _button(confirmed, "Add / edit plan"),
        action_key="cb:begin-plan",
    )
    assert "your plan, not a medical dose recommendation" in plan_prompt.text

    bucket = base.text(
        telegram_user_id,
        "1.5",
        action_key="msg:plan-quantity",
    )
    base.callback(
        telegram_user_id,
        _button(bucket, "Morning"),
        action_key="cb:save-plan",
    )

    profile = base.profile(telegram_user_id)
    base.callback(
        telegram_user_id,
        _button(profile, "Edit timezone"),
        action_key="cb:timezone",
    )
    updated = base.text(
        telegram_user_id,
        "Europe/London",
        action_key="msg:timezone",
    )
    assert "Timezone: Europe/London" in updated.text


def test_clean_account_vertical_flow_is_snapshot_bound_and_fail_closed(
    vertical_stack: tuple[
        KIR116Controller,
        KIR120Controller,
        KIR122Controller,
        KIR116Store,
    ],
) -> None:
    base, schedule, vertical, store = vertical_stack
    telegram_user_id = 122001
    _create_clean_account(base, telegram_user_id)

    composition = vertical.composition(telegram_user_id)
    picker = vertical.callback(
        telegram_user_id,
        _button(composition, "Состав: Example Magnesium"),
        action_key="cb:composition:open",
    )
    amount_prompt = vertical.callback(
        telegram_user_id,
        _button(picker, "Магний"),
        action_key="cb:composition:magnesium",
    )
    assert "не рекомендация по дозе" in amount_prompt.text

    review = vertical.text(
        telegram_user_id,
        "100 mg",
        action_key="msg:composition:amount",
    )
    assert "не означает «безопасно»" in review.text
    confirm_callback = _button(review, "Подтвердить")

    confirmed = vertical.callback(
        telegram_user_id,
        confirm_callback,
        action_key="cb:composition:confirm",
    )
    assert "Состав подтверждён" in confirmed.text
    assert "не вывод о безопасности" in confirmed.text

    # Duplicate Telegram callback delivery returns the same committed fact.
    duplicate = vertical.callback(
        telegram_user_id,
        confirm_callback,
        action_key="cb:composition:confirm",
    )
    assert "Состав подтверждён" in duplicate.text
    user_id = store.ensure_user(telegram_user_id)
    listed = vertical.composition(telegram_user_id)
    assert "1 подтверждено" in listed.text

    totals = vertical.totals(telegram_user_id)
    # 100 mg per two-capsule label serving => 50 mg/capsule; plan is 1.5 capsules/day.
    # KIR-114 canonicalizes mass aggregates to micrograms.
    assert "Магний: 75000 мкг" in totals.text
    assert "Example Magnesium: 75000 мкг" in totals.text
    assert "Неизвестное значение не считается нулём" not in totals.text

    rules = vertical.rules(telegram_user_id)
    assert "Это не подтверждение совместимости или безопасности" in rules.text
    assert "Отсутствие правила не означает, что сочетание безопасно" in rules.text
    assert "биологическое преимущество" in rules.text

    safety = vertical.safety(telegram_user_id)
    assert "Не могу оценить" in safety.text
    assert "не заменено взрослым значением" in safety.text
    assert "персональной рекомендации по дозе" in safety.text
    assert "безопасно для вас" not in safety.text.lower()

    # Why/Sources actions are bound to the exact immutable snapshot revision.
    old_sources = _callback_with_prefix(safety, "k122src:")
    current_plan = schedule.plan(telegram_user_id)
    day_callback = _callback_with_prefix(current_plan, "k120b:")
    day_parts = day_callback.split(":")
    day_callback = ":".join((*day_parts[:3], "d"))
    schedule.callback(
        telegram_user_id,
        day_callback,
        action_key="cb:schedule:move-to-day",
        now=datetime(2026, 9, 20, 7, 0, tzinfo=UTC),
    )
    stale = vertical.callback(
        telegram_user_id,
        old_sources,
        action_key="cb:old-sources",
    )
    assert "Экран устарел" in stale.text
    assert "не переименовал старый расчёт как новый" in stale.text

    today = schedule.today(
        telegram_user_id,
        now=datetime(2026, 9, 20, 11, 0, tzinfo=UTC),
    )
    localized_today = localize_operational_screen(
        vertical.decorate_operational_screen(today)
    )
    assert localized_today.text.startswith("Сегодня")
    assert "Example Magnesium" in localized_today.text
    assert "[ожидает]" in localized_today.text
    assert "Today" not in localized_today.text

    taken = schedule.callback(
        telegram_user_id,
        _button(today, "Taken"),
        action_key="cb:today:taken",
        now=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
    )
    localized_taken = localize_operational_screen(
        vertical.decorate_operational_screen(taken)
    )
    assert "[принято]" in localized_taken.text

    history = schedule.history(telegram_user_id)
    localized_history = localize_operational_screen(
        vertical.decorate_operational_screen(history)
    )
    assert localized_history.text.startswith("История")
    assert "принято" in localized_history.text
    assert "Доставка напоминания не доказывает приём" in localized_history.text


def test_operational_projection_is_russian_first_without_changing_callbacks(
    vertical_stack: tuple[
        KIR116Controller,
        KIR120Controller,
        KIR122Controller,
        KIR116Store,
    ],
) -> None:
    base, _, vertical, _ = vertical_stack
    telegram_user_id = 122002

    raw = base.start(telegram_user_id)
    projected = localize_operational_screen(
        vertical.decorate_operational_screen(raw)
    )
    assert projected.text.startswith("VitaminBot")
    assert "Добавьте свои добавки" in projected.text
    assert "medical dose recommendations" not in projected.text
    assert _button(projected, "Добавить первую добавку") == "a"

    add_raw = base.callback(
        telegram_user_id,
        "a",
        action_key="cb:projection:add",
    )
    add = localize_operational_screen(
        vertical.decorate_operational_screen(add_raw)
    )
    assert "Сейчас доступен ручной ввод" in add.text
    assert _button(add, "Ввести вручную") == "m"
