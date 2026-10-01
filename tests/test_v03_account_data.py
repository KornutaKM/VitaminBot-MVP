from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from vitaminbot.application.account import AccountController
from vitaminbot.application.views.account import AccountDeletionStatus, AccountDeletionView
from vitaminbot.persistence import migrate
from vitaminbot.persistence.account import AccountStore
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.presentation.telegram.account import render_account_deletion


@pytest.fixture
def account_schema() -> Iterator[tuple[str, str]]:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for PostgreSQL account data tests")

    schema = f"v03_account_{uuid4().hex}"
    migrate(database_url, schema=schema)
    try:
        yield database_url, schema
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def _create_quick_supplement(
    database_url: str,
    schema: str,
    telegram_user_id: int,
) -> tuple[KIR116Store, str]:
    store = KIR116Store(database_url, schema=schema)
    user_id = store.ensure_user(telegram_user_id)
    draft = store.begin_quick(user_id, "account-test:begin")
    draft = store.set_manual_name(
        user_id,
        "account-test:name",
        "Private Magnesium Label",
    )
    supplement = store.confirm_quick_unit_and_begin_plan(
        user_id,
        "account-test:unit",
        draft.draft_id,
        draft.revision,
        "capsule",
    )
    return store, supplement.instance_id


def _connect(database_url: str, schema: str) -> psycopg.Connection[tuple[object, ...]]:
    conn: psycopg.Connection[tuple[object, ...]] = psycopg.connect(
        database_url,
        autocommit=True,
    )
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    return conn


def test_export_is_versioned_and_contains_user_owned_supplement(
    account_schema: tuple[str, str],
) -> None:
    database_url, schema = account_schema
    telegram_user_id = 801001
    _, instance_id = _create_quick_supplement(database_url, schema, telegram_user_id)

    controller = AccountController(AccountStore(database_url, schema=schema))
    exported = controller.export_data(
        telegram_user_id,
        now=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )

    assert exported is not None
    assert exported.filename == "vitaminbot-export-2026-10-01.json"
    document = json.loads(exported.payload)
    assert document["schema"] == "vitaminbot.account-export.v1"
    assert document["data"]["user"]["telegram_user_id"] == telegram_user_id
    assert document["data"]["supplements"][0]["instance_id"] == instance_id
    assert document["data"]["supplements"][0]["container_label"] == "Private Magnesium Label"


def test_delete_account_cascades_user_data_and_purges_manual_provenance(
    account_schema: tuple[str, str],
) -> None:
    database_url, schema = account_schema
    telegram_user_id = 801002
    supplement_store, _ = _create_quick_supplement(
        database_url,
        schema,
        telegram_user_id,
    )
    account_store = AccountStore(database_url, schema=schema)
    now = datetime.now(UTC)
    token = "a" * 24

    assert account_store.begin_deletion(
        telegram_user_id,
        token=token,
        expires_at=now + timedelta(minutes=15),
    )
    assert (
        account_store.delete_account(
            telegram_user_id,
            token=token,
            now=now,
        )
        == "deleted"
    )

    with _connect(database_url, schema) as conn:
        assert conn.execute(
            "SELECT count(*) FROM users WHERE telegram_user_id = %s",
            (telegram_user_id,),
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT count(*) FROM user_supplements WHERE instance_id LIKE 'instance:manual:%'"
        ).fetchone() == (0,)
        assert conn.execute(
            """
            SELECT count(*)
            FROM product_formulations
            WHERE formulation_id LIKE 'formulation:manual:%'
            """
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT count(*) FROM products WHERE product_id LIKE 'product:manual:%'"
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT count(*) FROM source_records WHERE source_id LIKE 'source:manual:%'"
        ).fetchone() == (0,)

    recreated_user_id = supplement_store.ensure_user(telegram_user_id)
    assert (
        account_store.delete_account(
            telegram_user_id,
            token=token,
            now=now + timedelta(minutes=1),
        )
        == "stale"
    )

    with _connect(database_url, schema) as conn:
        assert conn.execute(
            "SELECT user_id FROM users WHERE telegram_user_id = %s",
            (telegram_user_id,),
        ).fetchone() == (recreated_user_id,)


def test_deletion_confirmation_is_explicit_and_nonce_bound() -> None:
    token = "b" * 24
    screen = render_account_deletion(
        AccountDeletionView(
            status=AccountDeletionStatus.CONFIRM,
            token=token,
            expires_at=datetime(2026, 10, 1, 12, 15, tzinfo=UTC),
        )
    )

    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert callbacks == [f"ad:y:{token}", f"ad:n:{token}"]
    assert "/export" in screen.text

    stale = render_account_deletion(
        AccountDeletionView(status=AccountDeletionStatus.STALE)
    )
    assert "Ничего не удалено" in stale.text
    assert stale.rows == ()
