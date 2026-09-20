from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from vitaminbot.application.kir116 import KIR116Controller, Screen
from vitaminbot.application.kir122 import KIR122AnalysisService, KIR122Controller
from vitaminbot.domain import Unit
from vitaminbot.persistence import migrate
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir122 import KIR122Store


@pytest.fixture
def kir122_system() -> Iterator[
    tuple[KIR116Controller, KIR122Controller, KIR122AnalysisService, KIR122Store, str, str]
]:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for KIR-122 integration tests")

    schema = f"kir122_{uuid4().hex}"
    migrate(database_url, schema=schema)
    kir116 = KIR116Controller(KIR116Store(database_url, schema=schema))
    store = KIR122Store(database_url, schema=schema)
    analysis = KIR122AnalysisService(store)
    controller = KIR122Controller(store, analysis)
    try:
        yield kir116, controller, analysis, store, database_url, schema
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def _button(screen: Screen, label: str) -> str:
    for row in screen.rows:
        for button in row:
            if button.label == label:
                return button.callback_data
    raise AssertionError(f"button not found: {label}")


def _prepare_planned_manual(
    kir116: KIR116Controller,
    telegram_user_id: int,
    *,
    name: str,
    quantity: str,
) -> str:
    kir116.start(telegram_user_id)
    name_prompt = kir116.callback(
        telegram_user_id,
        "m",
        action_key=f"{telegram_user_id}:manual",
    )
    assert "supplement name" in name_prompt.text.lower()
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
    assert "capsule" in serving.text.lower()
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
    kir116.callback(
        telegram_user_id,
        _button(confirmed, "Add / edit plan"),
        action_key=f"{telegram_user_id}:plan",
    )
    bucket = kir116.text(
        telegram_user_id,
        quantity,
        action_key=f"{telegram_user_id}:plan-quantity",
    )
    planned = kir116.callback(
        telegram_user_id,
        _button(bucket, "Morning"),
        action_key=f"{telegram_user_id}:plan-save",
    )
    assert name in planned.text
    return name


def _add_magnesium_amount(
    controller: KIR122Controller,
    telegram_user_id: int,
    *,
    amount: str = "200",
) -> Screen:
    choose = controller.choose_supplement(telegram_user_id)
    start = controller.callback(
        telegram_user_id,
        choose.rows[0][0].callback_data,
        action_key=f"{telegram_user_id}:nutrient-start",
    )
    assert "Состав с этикетки" in start.text
    value_prompt = controller.text(
        telegram_user_id,
        "Магний",
        action_key=f"{telegram_user_id}:nutrient-name",
    )
    assert "Магний" in value_prompt.text
    unit = controller.text(
        telegram_user_id,
        amount,
        action_key=f"{telegram_user_id}:nutrient-value",
    )
    review = controller.callback(
        telegram_user_id,
        _button(unit, "mg"),
        action_key=f"{telegram_user_id}:nutrient-unit",
    )
    assert f"Магний: {amount} mg" in review.text
    return review


def test_clean_manual_path_produces_snapshot_bound_daily_total(
    kir122_system: tuple[
        KIR116Controller,
        KIR122Controller,
        KIR122AnalysisService,
        KIR122Store,
        str,
        str,
    ],
) -> None:
    kir116, controller, analysis, store, database_url, schema = kir122_system
    telegram_user_id = 122001
    _prepare_planned_manual(
        kir116,
        telegram_user_id,
        name="Example Magnesium",
        quantity="2",
    )

    review = _add_magnesium_amount(controller, telegram_user_id)
    confirm_callback = _button(review, "Подтвердить строку")
    totals = controller.callback(
        telegram_user_id,
        confirm_callback,
        action_key=f"{telegram_user_id}:nutrient-confirm",
    )
    assert "Магний: 400000 µg / день" in totals.text
    assert "Example Magnesium" in totals.text
    assert "не персональная рекомендация дозы" in totals.text

    # Telegram duplicate delivery reuses the action receipt and cannot duplicate the amount.
    duplicate = controller.callback(
        telegram_user_id,
        confirm_callback,
        action_key=f"{telegram_user_id}:nutrient-confirm",
    )
    assert "Магний: 400000 µg / день" in duplicate.text

    user_id = store.ensure_user(telegram_user_id)
    snapshot = store.snapshot(user_id)
    assert len(snapshot.supplements) == 1
    assert len(snapshot.supplements[0].amounts) == 1

    projection = analysis.analyze(telegram_user_id)
    aggregate = projection.aggregation.aggregates[0]
    assert aggregate.known_total == Decimal("400000")
    assert aggregate.unit is Unit.MICROGRAM
    assert aggregate.is_complete is True

    card_context = analysis.card_context(telegram_user_id, "magnesium")
    assert card_context.context_revision == snapshot.context_revision
    assert card_context.confirmed_amount is not None
    assert card_context.confirmed_amount.value == Decimal("400000")
    assert card_context.confirmed_amount.unit is Unit.MICROGRAM

    with psycopg.connect(database_url) as conn:
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        assert conn.execute("SELECT count(*) FROM product_amounts").fetchone() == (1,)


def test_plan_change_changes_context_revision_and_recomputes_total(
    kir122_system: tuple[
        KIR116Controller,
        KIR122Controller,
        KIR122AnalysisService,
        KIR122Store,
        str,
        str,
    ],
) -> None:
    kir116, controller, analysis, _, _, _ = kir122_system
    telegram_user_id = 122002
    _prepare_planned_manual(
        kir116,
        telegram_user_id,
        name="Revision Magnesium",
        quantity="1",
    )
    review = _add_magnesium_amount(controller, telegram_user_id, amount="100")
    controller.callback(
        telegram_user_id,
        _button(review, "Подтвердить строку"),
        action_key=f"{telegram_user_id}:nutrient-confirm",
    )

    before = analysis.analyze(telegram_user_id)
    assert before.aggregation.aggregates[0].known_total == Decimal("100000")

    listed = kir116.supplements(telegram_user_id)
    detail = kir116.callback(
        telegram_user_id,
        listed.rows[0][0].callback_data,
        action_key=f"{telegram_user_id}:open",
    )
    quantity_prompt = kir116.callback(
        telegram_user_id,
        _button(detail, "Add / edit plan"),
        action_key=f"{telegram_user_id}:plan-edit",
    )
    assert "product units" in quantity_prompt.text.lower()
    bucket = kir116.text(
        telegram_user_id,
        "3",
        action_key=f"{telegram_user_id}:plan-quantity-2",
    )
    kir116.callback(
        telegram_user_id,
        _button(bucket, "Morning"),
        action_key=f"{telegram_user_id}:plan-save-2",
    )

    after = analysis.analyze(telegram_user_id)
    assert before.snapshot.context_revision != after.snapshot.context_revision
    assert after.aggregation.aggregates[0].known_total == Decimal("300000")


def test_unconfirmed_or_missing_amount_is_never_presented_as_zero(
    kir122_system: tuple[
        KIR116Controller,
        KIR122Controller,
        KIR122AnalysisService,
        KIR122Store,
        str,
        str,
    ],
) -> None:
    kir116, controller, analysis, _, _, _ = kir122_system
    telegram_user_id = 122003
    _prepare_planned_manual(
        kir116,
        telegram_user_id,
        name="No composition yet",
        quantity="1",
    )

    screen = controller.substances(telegram_user_id)
    assert "Подтверждённых строк состава" in screen.text
    assert "не считаются нулём" in screen.text
    assert analysis.analyze(telegram_user_id).aggregation.aggregates == ()


def test_unknown_nutrient_fails_closed_without_persistence(
    kir122_system: tuple[
        KIR116Controller,
        KIR122Controller,
        KIR122AnalysisService,
        KIR122Store,
        str,
        str,
    ],
) -> None:
    kir116, controller, _, store, _, _ = kir122_system
    telegram_user_id = 122004
    _prepare_planned_manual(
        kir116,
        telegram_user_id,
        name="Unknown label",
        quantity="1",
    )
    choose = controller.choose_supplement(telegram_user_id)
    controller.callback(
        telegram_user_id,
        choose.rows[0][0].callback_data,
        action_key=f"{telegram_user_id}:nutrient-start",
    )
    failed = controller.text(
        telegram_user_id,
        "Mystery nutrient X",
        action_key=f"{telegram_user_id}:unknown",
    )
    assert "не могу однозначно сопоставить" in failed.text
    snapshot = store.snapshot(store.ensure_user(telegram_user_id))
    assert snapshot.supplements[0].amounts == ()
