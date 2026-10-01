from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from vitaminbot.application.kir116 import KIR116Controller, Screen
from vitaminbot.application.supplements import QuickAddStep
from vitaminbot.persistence import migrate
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.telegram.bot import build_application


@pytest.fixture
def kir116_controller() -> Iterator[tuple[KIR116Controller, KIR116Store, str, str]]:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for KIR-116 integration tests")

    schema = f"kir116_{uuid4().hex}"
    migrate(database_url, schema=schema)
    store = KIR116Store(database_url, schema=schema)
    controller = KIR116Controller(store)
    try:
        yield controller, store, database_url, schema
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def _button(screen: Screen, label: str) -> str:
    for row in screen.rows:
        for button in row:
            if button.label == label:
                return button.callback_data
    raise AssertionError(f"button not found: {label}")


def _all_callback_data(screen: Screen) -> tuple[str, ...]:
    return tuple(button.callback_data for row in screen.rows for button in row)


def test_primary_manual_entry_plan_profile_edit_and_remove_flow(
    kir116_controller: tuple[KIR116Controller, KIR116Store, str, str],
) -> None:
    controller, store, database_url, schema = kir116_controller
    telegram_user_id = 101001

    welcome = controller.start(telegram_user_id)
    assert "medical dose recommendations" in welcome.text
    assert _button(welcome, "Add first supplement") == "a"

    add = controller.callback(
        telegram_user_id,
        "a",
        action_key="cb:add",
    )
    assert "Manual entry is available" in add.text
    assert all("Photo" not in button.label for row in add.rows for button in row)

    manual = controller.callback(
        telegram_user_id,
        _button(add, "Enter manually"),
        action_key="cb:manual",
    )
    assert "Send the supplement name" in manual.text

    unit = controller.text(
        telegram_user_id,
        "Example Magnesium",
        action_key="msg:name",
    )
    assert "Product unit" in unit.text

    # Duplicate Telegram delivery must not advance the draft a second time.
    duplicate_name = controller.text(
        telegram_user_id,
        "Example Magnesium",
        action_key="msg:name",
    )
    assert "Product unit" in duplicate_name.text

    serving_prompt = controller.callback(
        telegram_user_id,
        _button(unit, "Capsule"),
        action_key="cb:unit",
    )
    assert "How many capsule units" in serving_prompt.text

    invalid_quantity = controller.text(
        telegram_user_id,
        "0",
        action_key="msg:invalid-serving",
    )
    assert "greater than zero" in invalid_quantity.text

    review = controller.text(
        telegram_user_id,
        "2",
        action_key="msg:serving",
    )
    assert "Review manual entry" in review.text
    assert "Source: You entered these facts manually." in review.text
    assert "does not mean the supplement is safe" in review.text

    confirmed = controller.callback(
        telegram_user_id,
        _button(review, "Confirm entry"),
        action_key="cb:confirm",
    )
    assert "Manual entry confirmed" in confirmed.text
    assert "Your plan: Not set" in confirmed.text

    # Duplicate callback delivery returns the same confirmed record, not a second supplement.
    confirmed_again = controller.callback(
        telegram_user_id,
        _button(review, "Confirm entry"),
        action_key="cb:confirm",
    )
    assert "Example Magnesium" in confirmed_again.text
    user_id = store.ensure_user(telegram_user_id)
    assert len(store.list_supplements(user_id)) == 1

    plan_prompt = controller.callback(
        telegram_user_id,
        _button(confirmed, "Add / edit plan"),
        action_key="cb:plan-start",
    )
    assert "your plan, not a medical dose recommendation" in plan_prompt.text

    bucket = controller.text(
        telegram_user_id,
        "1.5",
        action_key="msg:plan-quantity",
    )
    assert "routine labels only" in bucket.text

    planned = controller.callback(
        telegram_user_id,
        _button(bucket, "Morning"),
        action_key="cb:plan-save",
    )
    assert "Plan saved" in planned.text
    assert "Morning — 1.5 capsule" in planned.text

    planned_again = controller.callback(
        telegram_user_id,
        _button(bucket, "Morning"),
        action_key="cb:plan-save",
    )
    assert "Morning — 1.5 capsule" in planned_again.text

    profile = controller.profile(telegram_user_id)
    assert "Timezone: Not set" in profile.text
    timezone_prompt = controller.callback(
        telegram_user_id,
        _button(profile, "Edit timezone"),
        action_key="cb:profile-timezone",
    )
    assert "IANA timezone" in timezone_prompt.text

    invalid_timezone = controller.text(
        telegram_user_id,
        "Not/AZone",
        action_key="msg:timezone-invalid",
    )
    assert "don’t recognize" in invalid_timezone.text

    updated_profile = controller.text(
        telegram_user_id,
        "Europe/Helsinki",
        action_key="msg:timezone",
    )
    assert "Timezone: Europe/Helsinki" in updated_profile.text

    locale_prompt = controller.callback(
        telegram_user_id,
        _button(updated_profile, "Edit locale"),
        action_key="cb:profile-locale",
    )
    assert "presentation only" in locale_prompt.text
    final_profile = controller.text(
        telegram_user_id,
        "fi-FI",
        action_key="msg:locale",
    )
    assert "Locale: fi-FI" in final_profile.text

    current = controller.supplements(telegram_user_id)
    detail = controller.callback(
        telegram_user_id,
        _all_callback_data(current)[0],
        action_key="cb:open",
    )
    old_open_callback = _button(current, "Open Example Magnesium")

    edit_name = controller.callback(
        telegram_user_id,
        _button(detail, "Edit name"),
        action_key="cb:edit-name",
    )
    assert "Send the new tracked supplement name" in edit_name.text
    renamed = controller.text(
        telegram_user_id,
        "Magnesium Evening Bottle",
        action_key="msg:rename",
    )
    assert "Name updated" in renamed.text

    stale = controller.callback(
        telegram_user_id,
        old_open_callback,
        action_key="cb:stale-open",
    )
    assert "out of date" in stale.text

    serving_edit = controller.callback(
        telegram_user_id,
        _button(renamed, "Edit serving"),
        action_key="cb:edit-serving",
    )
    new_quantity_prompt = controller.callback(
        telegram_user_id,
        _button(serving_edit, "Tablet"),
        action_key="cb:edit-unit",
    )
    assert "How many of these units" in new_quantity_prompt.text
    serving_updated = controller.text(
        telegram_user_id,
        "1",
        action_key="msg:edit-serving-quantity",
    )
    assert "Label serving: 1 tablet" in serving_updated.text

    remove_prompt = controller.callback(
        telegram_user_id,
        _button(serving_updated, "Remove supplement…"),
        action_key="cb:remove-prompt",
    )
    assert "saved plan" in remove_prompt.text
    assert "linked intake history" in remove_prompt.text

    removed = controller.callback(
        telegram_user_id,
        _button(remove_prompt, "Remove supplement"),
        action_key="cb:remove-confirm",
    )
    assert "Supplement removed" in removed.text
    assert store.list_supplements(user_id) == ()

    with psycopg.connect(database_url) as conn:
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        assert conn.execute("SELECT count(*) FROM products").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM product_formulations").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM source_records").fetchone() == (0,)


def test_pending_manual_state_survives_controller_restart(
    kir116_controller: tuple[KIR116Controller, KIR116Store, str, str],
) -> None:
    controller, store, _, _ = kir116_controller
    telegram_user_id = 202002

    controller.start(telegram_user_id)
    controller.callback(telegram_user_id, "m", action_key="cb:manual-restart")
    controller.text(
        telegram_user_id,
        "Restart-safe supplement",
        action_key="msg:restart-name",
    )

    restarted = KIR116Controller(store)
    user_id = store.ensure_user(telegram_user_id)
    session = store.get_session(user_id)
    assert session is not None
    assert session.state == "manual_unit"

    resumed = restarted.text(
        telegram_user_id,
        "ignored free text",
        action_key="msg:ignored",
    )
    assert "Product unit" in resumed.text


def test_callback_payloads_are_opaque_and_bounded(
    kir116_controller: tuple[KIR116Controller, KIR116Store, str, str],
) -> None:
    controller, store, _, _ = kir116_controller
    telegram_user_id = 303003

    controller.start(telegram_user_id)
    controller.callback(telegram_user_id, "m", action_key="cb:manual-payload")
    controller.text(
        telegram_user_id,
        "Private Supplement Name",
        action_key="msg:payload-name",
    )
    user_id = store.ensure_user(telegram_user_id)
    draft = store.get_draft(user_id)
    assert draft is not None
    unit_screen = controller._manual_unit_screen(draft)  # noqa: SLF001

    for payload in _all_callback_data(unit_screen):
        assert len(payload.encode("utf-8")) <= 64
        assert "Private Supplement Name" not in payload


def test_telegram_application_registers_bot_native_handlers(
    kir116_controller: tuple[KIR116Controller, KIR116Store, str, str],
) -> None:
    controller, _, _, _ = kir116_controller
    application = build_application(
        "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
        controller,
    )

    assert application.bot_data["kir116_controller"] is controller
    assert 0 in application.handlers
    assert len(application.handlers[0]) == 8


def test_cancelled_plan_callback_cannot_apply_to_new_session(
    kir116_controller: tuple[KIR116Controller, KIR116Store, str, str],
) -> None:
    controller, _, _, _ = kir116_controller
    telegram_user_id = 404004

    controller.start(telegram_user_id)
    controller.callback(telegram_user_id, "m", action_key="cb:aba-manual")
    unit = controller.text(
        telegram_user_id,
        "ABA supplement",
        action_key="msg:aba-name",
    )
    serving = controller.callback(
        telegram_user_id,
        _button(unit, "Capsule"),
        action_key="cb:aba-unit",
    )
    assert "How many capsule units" in serving.text
    review = controller.text(
        telegram_user_id,
        "1",
        action_key="msg:aba-serving",
    )
    confirmed = controller.callback(
        telegram_user_id,
        _button(review, "Confirm entry"),
        action_key="cb:aba-confirm",
    )

    controller.callback(
        telegram_user_id,
        _button(confirmed, "Add / edit plan"),
        action_key="cb:aba-plan-one",
    )
    first_bucket = controller.text(
        telegram_user_id,
        "1",
        action_key="msg:aba-plan-one",
    )
    stale_bucket_callback = _button(first_bucket, "Morning")

    controller.cancel(telegram_user_id)

    current = controller.supplements(telegram_user_id)
    detail = controller.callback(
        telegram_user_id,
        _all_callback_data(current)[0],
        action_key="cb:aba-open",
    )
    controller.callback(
        telegram_user_id,
        _button(detail, "Add / edit plan"),
        action_key="cb:aba-plan-two",
    )
    second_bucket = controller.text(
        telegram_user_id,
        "2",
        action_key="msg:aba-plan-two",
    )
    assert _button(second_bucket, "Morning") != stale_bucket_callback

    stale = controller.callback(
        telegram_user_id,
        stale_bucket_callback,
        action_key="cb:aba-stale",
    )
    assert "out of date" in stale.text

    current_after_stale = controller.supplements(telegram_user_id)
    assert "no plan yet" in current_after_stale.text


def test_serving_edit_versions_semantics_and_preserves_existing_plan(
    kir116_controller: tuple[KIR116Controller, KIR116Store, str, str],
) -> None:
    controller, store, database_url, schema = kir116_controller
    telegram_user_id = 505005

    controller.start(telegram_user_id)
    controller.callback(telegram_user_id, "m", action_key="sem:manual")
    unit_screen = controller.text(
        telegram_user_id,
        "Versioned serving supplement",
        action_key="sem:name",
    )
    serving_prompt = controller.callback(
        telegram_user_id,
        _button(unit_screen, "Capsule"),
        action_key="sem:unit",
    )
    assert "How many capsule units" in serving_prompt.text
    review = controller.text(
        telegram_user_id,
        "2",
        action_key="sem:serving",
    )
    confirmed = controller.callback(
        telegram_user_id,
        _button(review, "Confirm entry"),
        action_key="sem:confirm",
    )
    plan_prompt = controller.callback(
        telegram_user_id,
        _button(confirmed, "Add / edit plan"),
        action_key="sem:plan-start",
    )
    assert "your plan, not a medical dose recommendation" in plan_prompt.text
    bucket = controller.text(
        telegram_user_id,
        "1.5",
        action_key="sem:plan-quantity",
    )
    planned = controller.callback(
        telegram_user_id,
        _button(bucket, "Morning"),
        action_key="sem:plan-save",
    )
    assert "Morning — 1.5 capsule" in planned.text

    user_id = store.ensure_user(telegram_user_id)
    before = store.list_supplements(user_id)[0]
    old_unit_id = before.unit_id

    edit = controller.callback(
        telegram_user_id,
        _button(planned, "Edit serving"),
        action_key="sem:edit-serving",
    )
    assert all(button.label != "mL" for row in edit.rows for button in row)
    quantity_prompt = controller.callback(
        telegram_user_id,
        _button(edit, "Tablet"),
        action_key="sem:edit-unit",
    )
    assert "How many of these units" in quantity_prompt.text
    updated = controller.text(
        telegram_user_id,
        "1",
        action_key="sem:edit-quantity",
    )

    assert "Label serving: 1 tablet" in updated.text
    assert "Morning — 1.5 capsule" in updated.text
    assert "keeps the previous product-unit meaning (capsule)" in updated.text

    after = store.list_supplements(user_id)[0]
    assert after.unit_id != old_unit_id
    assert after.unit_label == "tablet"
    assert after.plan_unit_label == "capsule"

    with psycopg.connect(database_url) as conn:
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        current = conn.execute(
            """
            SELECT
                us.current_consumption_unit_id,
                current_unit.label_name,
                current_serving.basis_quantity,
                current_serving.basis_unit
            FROM user_supplements AS us
            JOIN consumption_units AS current_unit
              ON current_unit.formulation_id = us.formulation_id
             AND current_unit.unit_id = us.current_consumption_unit_id
            JOIN product_servings AS current_serving
              ON current_serving.formulation_id = us.formulation_id
             AND current_serving.basis_id = us.current_serving_basis_id
            WHERE us.instance_id = %s
            """,
            (after.instance_id,),
        ).fetchone()
        assert current == (after.unit_id, "tablet", Decimal("1"), "count")

        saved_plan = conn.execute(
            """
            SELECT
                planned.consumption_unit_id,
                plan_unit.label_name,
                planned.consumption_units
            FROM intake_plan_heads AS head
            JOIN planned_intake_events AS planned
              ON planned.plan_id = head.plan_id
             AND planned.plan_version = head.plan_version
            JOIN consumption_units AS plan_unit
              ON plan_unit.formulation_id = planned.formulation_id
             AND plan_unit.unit_id = planned.consumption_unit_id
            WHERE head.tracked_instance_id = %s
            """,
            (after.instance_id,),
        ).fetchone()
        assert saved_plan == (old_unit_id, "capsule", Decimal("1.5"))

        assert conn.execute(
            """
            SELECT count(*)
            FROM consumption_units
            WHERE formulation_id = %s
            """,
            (after.formulation_id,),
        ).fetchone() == (2,)


def test_ml_is_hidden_and_rejected_before_count_persistence(
    kir116_controller: tuple[KIR116Controller, KIR116Store, str, str],
) -> None:
    controller, store, _, _ = kir116_controller
    telegram_user_id = 606006

    controller.start(telegram_user_id)
    controller.callback(telegram_user_id, "m", action_key="ml:manual")
    unit_screen = controller.text(
        telegram_user_id,
        "Liquid-form candidate",
        action_key="ml:name",
    )
    assert all(button.label != "mL" for row in unit_screen.rows for button in row)

    user_id = store.ensure_user(telegram_user_id)
    draft = store.get_draft(user_id)
    assert draft is not None
    assert draft.unit_label is None

    with pytest.raises(ValueError, match="count-based product units only"):
        store.set_manual_unit(
            user_id,
            "ml:direct-store-attempt",
            draft.draft_id,
            draft.revision,
            "mL",
        )

    unchanged = store.get_draft(user_id)
    assert unchanged is not None
    assert unchanged.unit_label is None


def test_quick_add_uses_consumption_unit_basis_and_saves_plan_once(
    kir116_controller: tuple[KIR116Controller, KIR116Store, str, str],
) -> None:
    controller, store, database_url, schema = kir116_controller
    telegram_user_id = 101020

    start = controller.quick_add_start(
        telegram_user_id,
        action_key="quick:start",
    )
    assert start.step is QuickAddStep.NAME

    unit = controller.quick_add_text(
        telegram_user_id,
        "Magnesium Citrate",
        action_key="quick:name",
    )
    assert unit.step is QuickAddStep.UNIT
    assert unit.draft_id is not None
    assert unit.revision is not None

    quantity = controller.quick_add_callback(
        telegram_user_id,
        f"qau:{unit.draft_id}:{unit.revision}:c",
        action_key="quick:unit",
    )
    assert quantity.step is QuickAddStep.QUANTITY
    assert quantity.unit_label == "capsule"

    duplicate_unit = controller.quick_add_callback(
        telegram_user_id,
        f"qau:{unit.draft_id}:{unit.revision}:c",
        action_key="quick:unit",
    )
    assert duplicate_unit.step is QuickAddStep.QUANTITY

    bucket = controller.quick_add_callback(
        telegram_user_id,
        "qaq:2",
        action_key="quick:quantity",
    )
    assert bucket.step is QuickAddStep.BUCKET
    assert bucket.quantity == Decimal("2")
    assert bucket.revision is not None

    complete = controller.quick_add_callback(
        telegram_user_id,
        f"qab:e:{bucket.revision}",
        action_key="quick:bucket",
    )
    assert complete.step is QuickAddStep.COMPLETE
    assert complete.name == "Magnesium Citrate"
    assert complete.quantity == Decimal("2")
    assert complete.bucket == "evening"

    complete_again = controller.quick_add_callback(
        telegram_user_id,
        f"qab:e:{bucket.revision}",
        action_key="quick:bucket",
    )
    assert complete_again.step is QuickAddStep.COMPLETE

    user_id = store.ensure_user(telegram_user_id)
    records = store.list_supplements(user_id)
    assert len(records) == 1
    record = records[0]
    assert record.serving_basis_type == "per_consumption_unit"
    assert record.units_per_serving == Decimal("1")
    assert record.plan_quantity == Decimal("2")
    assert record.plan_bucket == "evening"

    with psycopg.connect(database_url) as conn:
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        basis = conn.execute(
            """
            SELECT basis_type, basis_quantity, label_text
            FROM product_servings
            WHERE formulation_id = %s
            """,
            (record.formulation_id,),
        ).fetchone()
        assert basis is not None
        assert basis[0] == "per_consumption_unit"
        assert basis[1] == Decimal("1")
        assert "tracked unit" in basis[2]
        assert conn.execute("SELECT count(*) FROM intake_plan_heads").fetchone() == (1,)
