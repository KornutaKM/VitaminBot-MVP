from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from vitaminbot.persistence import PostgresUnitOfWork, migrate


@pytest.fixture
def uow_schema() -> Iterator[tuple[str, str]]:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for PostgreSQL UnitOfWork tests")

    schema = f"v03_uow_{uuid4().hex}"
    migrate(database_url, schema=schema)
    try:
        yield database_url, schema
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def _user_count(database_url: str, schema: str, telegram_user_id: int) -> int:
    with psycopg.connect(database_url) as conn:
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        row = conn.execute(
            "SELECT count(*) FROM users WHERE telegram_user_id = %s",
            (telegram_user_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def test_unit_of_work_rolls_back_cross_repository_changes_without_commit(
    uow_schema: tuple[str, str],
) -> None:
    database_url, schema = uow_schema
    telegram_user_id = 811001

    with PostgresUnitOfWork(database_url, schema=schema) as uow:
        user_id = uow.supplements.ensure_user(telegram_user_id)
        assert uow.intake.ensure_user(telegram_user_id) == user_id
        assert uow.applicability.profile(user_id).revision == 0
        assert uow.nutrition.session(user_id) is None

    assert _user_count(database_url, schema, telegram_user_id) == 0


def test_unit_of_work_commits_one_shared_transaction(
    uow_schema: tuple[str, str],
) -> None:
    database_url, schema = uow_schema
    telegram_user_id = 811002

    with PostgresUnitOfWork(database_url, schema=schema) as uow:
        user_id = uow.supplements.ensure_user(telegram_user_id)
        assert uow.intake.ensure_user(telegram_user_id) == user_id
        assert uow.applicability.profile(user_id).revision == 0
        assert uow.nutrition.session(user_id) is None
        uow.commit()

    assert _user_count(database_url, schema, telegram_user_id) == 1


def test_unit_of_work_rolls_back_on_exception_even_without_explicit_rollback(
    uow_schema: tuple[str, str],
) -> None:
    database_url, schema = uow_schema
    telegram_user_id = 811003

    with pytest.raises(RuntimeError, match="abort transaction"):
        with PostgresUnitOfWork(database_url, schema=schema) as uow:
            uow.supplements.ensure_user(telegram_user_id)
            raise RuntimeError("abort transaction")

    assert _user_count(database_url, schema, telegram_user_id) == 0
