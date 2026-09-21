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
from vitaminbot.application.safety_envelope import (
    SafetyEvidenceState,
    SafetyStatus,
)
from vitaminbot.persistence import migrate
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir120 import KIR120Store, RoutineTimes
from vitaminbot.persistence.kir122 import KIR122Store
from vitaminbot.telegram.presentation import (
    localize_operational_screen,
    project_v02_screen,
)


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
    base, schedule, vertical, _store = vertical_stack
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

    envelopes = vertical.safety_envelopes(telegram_user_id)
    assert envelopes
    assert all(item.status is SafetyStatus.CANNOT_ASSESS for item in envelopes)
    assert all(item.withheld_conclusion for item in envelopes)
    assert all(item.resolution_path for item in envelopes)
    assert all(item.non_droppable_warnings for item in envelopes)
    assert all(item.context_revision.startswith("kir122:") for item in envelopes)
    assert any(item.evidence_state is SafetyEvidenceState.MISSING for item in envelopes)

    safety = vertical.safety(telegram_user_id)
    assert "Статус: Не могу оценить" in safety.text
    assert "Вывод удержан:" in safety.text
    assert "взрослое значение по умолчанию не используется" in safety.text
    assert "Здесь нет персональной рекомендации по дозе." in safety.text
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
    localized_today = localize_operational_screen(vertical.decorate_operational_screen(today))
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
    localized_taken = localize_operational_screen(vertical.decorate_operational_screen(taken))
    assert "[принято]" in localized_taken.text

    history = schedule.history(telegram_user_id)
    localized_history = localize_operational_screen(vertical.decorate_operational_screen(history))
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
    projected = localize_operational_screen(vertical.decorate_operational_screen(raw))
    assert projected.text.startswith("VitaminBot")
    assert "Добавьте свои добавки" in projected.text
    assert "medical dose recommendations" not in projected.text
    assert _button(projected, "Добавить первую добавку") == "a"

    add_raw = base.callback(
        telegram_user_id,
        "a",
        action_key="cb:projection:add",
    )
    add = localize_operational_screen(vertical.decorate_operational_screen(add_raw))
    assert "Сейчас доступен ручной ввод" in add.text
    assert _button(add, "Ввести вручную") == "m"


def _confirm_composition(
    vertical: KIR122Controller,
    telegram_user_id: int,
    *,
    nutrient_label: str,
    amount: str,
    action_prefix: str,
) -> None:
    composition = vertical.composition(telegram_user_id)
    picker = vertical.callback(
        telegram_user_id,
        _button(composition, "Состав: Example Magnesium"),
        action_key=f"{action_prefix}:open",
    )
    amount_prompt = vertical.callback(
        telegram_user_id,
        _button(picker, nutrient_label),
        action_key=f"{action_prefix}:nutrient",
    )
    assert "не рекомендация по дозе" in amount_prompt.text
    review = vertical.text(
        telegram_user_id,
        amount,
        action_key=f"{action_prefix}:amount",
    )
    confirmed = vertical.callback(
        telegram_user_id,
        _button(review, "Подтвердить"),
        action_key=f"{action_prefix}:confirm",
    )
    assert "Состав подтверждён" in confirmed.text


def test_supplement_detail_composition_bridge_round_trips_real_callbacks_and_stays_stale(
    vertical_stack: tuple[
        KIR116Controller,
        KIR120Controller,
        KIR122Controller,
        KIR116Store,
    ],
) -> None:
    base, _, vertical, _store = vertical_stack
    telegram_user_id = 122003
    _create_clean_account(base, telegram_user_id)

    supplements = base.supplements(telegram_user_id)
    detail = base.callback(
        telegram_user_id,
        _button(supplements, "Open Example Magnesium"),
        action_key="cb:bridge:open-detail",
    )
    projected_detail = project_v02_screen(
        vertical.decorate_operational_screen(detail),
        surface="supplement",
    )

    composition_callback = _button(projected_detail, "Состав")
    picker = vertical.callback(
        telegram_user_id,
        composition_callback,
        action_key="cb:bridge:open-composition",
    )
    assert picker.text.startswith("Состав — Example Magnesium")

    back_callback = _button(picker, "Назад к добавке")
    round_trip_detail = base.callback(
        telegram_user_id,
        back_callback,
        action_key="cb:bridge:back-to-detail",
    )
    assert round_trip_detail.text.startswith("Example Magnesium")
    assert "Status: Confirmed manual entry" in round_trip_detail.text

    edit_name = base.callback(
        telegram_user_id,
        _button(round_trip_detail, "Edit name"),
        action_key="cb:bridge:edit-name",
    )
    assert "Send the new tracked supplement name" in edit_name.text
    base.text(
        telegram_user_id,
        "Example Magnesium revised",
        action_key="msg:bridge:rename",
    )

    stale = vertical.callback(
        telegram_user_id,
        composition_callback,
        action_key="cb:bridge:stale-composition",
    )
    assert "Экран устарел" in stale.text
    assert "не применил старое действие" in stale.text


@pytest.mark.parametrize(
    ("adversarial_name", "mutated_name"),
    (
        ("Morning — Formula", "Утро — Formula"),
        ("Timezone: Blend", "Часовой пояс: Blend"),
        ("Not set", "Не настроен"),
        ("Label serving: Formula", "Порция по этикетке: Formula"),
        ("Your plan: Formula", "Ваш план: Formula"),
    ),
)
def test_operational_localization_preserves_short_shell_tokens_in_product_identity(
    vertical_stack: tuple[
        KIR116Controller,
        KIR120Controller,
        KIR122Controller,
        KIR116Store,
    ],
    adversarial_name: str,
    mutated_name: str,
) -> None:
    base, schedule, vertical, _store = vertical_stack
    telegram_user_id = 122004
    _create_clean_account(base, telegram_user_id)

    supplements = base.supplements(telegram_user_id)
    detail = base.callback(
        telegram_user_id,
        _button(supplements, "Open Example Magnesium"),
        action_key=f"cb:short-localization:open:{adversarial_name}",
    )
    base.callback(
        telegram_user_id,
        _button(detail, "Edit name"),
        action_key=f"cb:short-localization:edit:{adversarial_name}",
    )
    renamed = base.text(
        telegram_user_id,
        adversarial_name,
        action_key=f"msg:short-localization:rename:{adversarial_name}",
    )

    projected_detail = project_v02_screen(
        vertical.decorate_operational_screen(renamed),
        surface="supplement",
    )
    identity_bytes = adversarial_name.encode()
    assert identity_bytes in projected_detail.text.encode()
    assert mutated_name.encode() not in projected_detail.text.encode()
    assert "Ваш план: Утро —" in projected_detail.text

    today = schedule.today(
        telegram_user_id,
        now=datetime(2026, 9, 20, 11, 0, tzinfo=UTC),
    )
    projected_today = project_v02_screen(
        vertical.decorate_operational_screen(today),
        surface="today",
    )
    assert f"• Утро — {adversarial_name}:".encode() in projected_today.text.encode()
    assert mutated_name.encode() not in projected_today.text.encode()
    assert "[ожидает]" in projected_today.text

    plan = schedule.plan(telegram_user_id)
    projected_plan = project_v02_screen(
        vertical.decorate_operational_screen(plan),
        surface="plan",
    )
    assert projected_plan.text.startswith("План")
    assert (
        f"Ваша настройка: {adversarial_name}:".encode()
        in projected_plan.text.encode()
    )
    assert mutated_name.encode() not in projected_plan.text.encode()
    assert " — Утро" in projected_plan.text
    assert "Это ваши повторяющиеся настройки режима." in projected_plan.text

    schedule.callback(
        telegram_user_id,
        _button(today, "Taken"),
        action_key=f"cb:short-localization:taken:{adversarial_name}",
        now=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
    )
    history = schedule.history(telegram_user_id)
    projected_history = project_v02_screen(
        vertical.decorate_operational_screen(history),
        surface="history",
    )
    assert projected_history.text.startswith("История")
    assert f"• {adversarial_name}:".encode() in projected_history.text.encode()
    assert mutated_name.encode() not in projected_history.text.encode()
    assert " — принято" in projected_history.text


def test_operational_localization_preserves_valid_dynamic_names_with_status_words(
    vertical_stack: tuple[
        KIR116Controller,
        KIR120Controller,
        KIR122Controller,
        KIR116Store,
    ],
) -> None:
    base, schedule, vertical, _store = vertical_stack
    telegram_user_id = 122004
    _create_clean_account(base, telegram_user_id)

    supplements = base.supplements(telegram_user_id)
    detail = base.callback(
        telegram_user_id,
        _button(supplements, "Open Example Magnesium"),
        action_key="cb:localization:open",
    )
    base.callback(
        telegram_user_id,
        _button(detail, "Edit name"),
        action_key="cb:localization:edit-name",
    )
    adversarial_name = "taken skip later formula"
    renamed = base.text(
        telegram_user_id,
        adversarial_name,
        action_key="msg:localization:rename",
    )
    assert f"\n\n{adversarial_name}\n\n" in renamed.text

    today = schedule.today(
        telegram_user_id,
        now=datetime(2026, 9, 20, 11, 0, tzinfo=UTC),
    )
    localized_today = localize_operational_screen(vertical.decorate_operational_screen(today))
    assert adversarial_name in localized_today.text
    assert "[ожидает]" in localized_today.text

    schedule.callback(
        telegram_user_id,
        _button(today, "Taken"),
        action_key="cb:localization:taken",
        now=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
    )
    history = schedule.history(telegram_user_id)
    localized_history = localize_operational_screen(vertical.decorate_operational_screen(history))
    assert adversarial_name in localized_history.text
    assert f"• {adversarial_name}:" in localized_history.text
    assert " — принято" in localized_history.text


def test_rule_sources_keep_full_accepted_provenance(
    vertical_stack: tuple[
        KIR116Controller,
        KIR120Controller,
        KIR122Controller,
        KIR116Store,
    ],
) -> None:
    base, _, vertical, store = vertical_stack
    telegram_user_id = 122005
    _create_clean_account(base, telegram_user_id)
    _confirm_composition(
        vertical,
        telegram_user_id,
        nutrient_label="Витамин D",
        amount="10 ug",
        action_prefix="cb:rule-provenance",
    )

    rules = vertical.rules(telegram_user_id)
    sources = vertical.callback(
        telegram_user_id,
        _callback_with_prefix(rules, "k122why:"),
        action_key="cb:rule-provenance:sources",
    )
    user_id = store.ensure_user(telegram_user_id)
    view = vertical._build_view(user_id)
    expected_sources = {
        source.source_key: source
        for result in view.rule_result.scheduling_results
        for source in result.source_provenance
    }
    assert expected_sources

    for source in expected_sources.values():
        assert source.title in sources.text
        assert source.authority in sources.text
        assert source.jurisdiction_note in sources.text
        assert source.version_label in sources.text
        assert source.retrieved_on.isoformat() in sources.text
        assert source.locator in sources.text
        assert source.source_url in sources.text


def test_reference_sources_keep_locator_and_matched_applicability_context(
    vertical_stack: tuple[
        KIR116Controller,
        KIR120Controller,
        KIR122Controller,
        KIR116Store,
    ],
) -> None:
    base, _, vertical, store = vertical_stack
    telegram_user_id = 122006
    _create_clean_account(base, telegram_user_id)
    _confirm_composition(
        vertical,
        telegram_user_id,
        nutrient_label="Витамин C",
        amount="100 mg",
        action_prefix="cb:reference-provenance",
    )

    user_id = store.ensure_user(telegram_user_id)
    view = vertical._build_view(user_id)
    envelopes = vertical._reference_envelopes(view)
    provenance = tuple(source for envelope in envelopes for source in envelope.provenance)
    assert provenance
    assert all(source.applicability_status == "match" for source in provenance)

    safety = vertical.safety(telegram_user_id)
    sources = vertical.callback(
        telegram_user_id,
        _callback_with_prefix(safety, "k122src:"),
        action_key="cb:reference-provenance:sources",
    )
    assert "применимость: запись совпала с текущим контекстом" in sources.text

    for source in provenance:
        assert source.title in sources.text
        assert source.source_url in sources.text
        assert source.version in sources.text
        assert source.source_locator in sources.text
        if source.jurisdiction is not None:
            assert source.jurisdiction in sources.text
        if source.reference_type is not None:
            assert source.reference_type in sources.text
        if source.scope_note is not None:
            assert source.scope_note in sources.text
        assert source.source_key not in sources.text
