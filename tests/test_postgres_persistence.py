from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from vitaminbot.persistence import migrate


@pytest.fixture
def postgres_schema() -> Iterator[tuple[str, str]]:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for PostgreSQL persistence tests")

    schema = f"kir112_{uuid4().hex}"
    migrate(database_url, schema=schema)
    try:
        yield database_url, schema
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema)
                )
            )


def _connect(database_url: str, schema: str) -> psycopg.Connection[tuple[object, ...]]:
    conn: psycopg.Connection[tuple[object, ...]] = psycopg.connect(
        database_url,
        autocommit=True,
    )
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    return conn


def test_migrations_are_reproducible_and_idempotent(
    postgres_schema: tuple[str, str],
) -> None:
    database_url, schema = postgres_schema

    assert migrate(database_url, schema=schema) == ()

    with _connect(database_url, schema) as conn:
        rows = conn.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert rows == [("0001", "initial")]


def test_core_constraints_preserve_domain_and_user_data_boundaries(
    postgres_schema: tuple[str, str],
) -> None:
    database_url, schema = postgres_schema
    user_id = uuid4()

    with _connect(database_url, schema) as conn:
        conn.execute(
            """
            INSERT INTO source_records (
                source_id,
                authority,
                source_type,
                title,
                stable_identifier,
                version,
                retrieved_on
            )
            VALUES
                (
                    'source:label:v1',
                    'Example manufacturer',
                    'product_label',
                    'Example product label',
                    'label:example-product',
                    '1',
                    DATE '2026-09-20'
                ),
                (
                    'source:user-confirmation',
                    'User declaration',
                    'user_declaration',
                    'Explicit intake confirmation',
                    'confirmation:explicit',
                    '1',
                    DATE '2026-09-20'
                )
            """
        )
        conn.execute(
            """
            INSERT INTO products (
                product_id,
                name,
                market_jurisdiction_status
            )
            VALUES ('product:1', 'Example product', 'unknown')
            """
        )
        conn.execute(
            """
            INSERT INTO product_formulations (formulation_id, product_id, version)
            VALUES ('formulation:1:v1', 'product:1', '1')
            """
        )
        conn.execute(
            """
            INSERT INTO formulation_sources (formulation_id, source_id)
            VALUES ('formulation:1:v1', 'source:label:v1')
            """
        )
        conn.execute(
            """
            INSERT INTO consumption_units (
                unit_id,
                formulation_id,
                label_name,
                source_id
            )
            VALUES (
                'consumption-unit:capsule',
                'formulation:1:v1',
                'capsule',
                'source:label:v1'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO product_servings (
                basis_id,
                formulation_id,
                basis_type,
                label_text,
                source_id,
                basis_quantity,
                basis_unit,
                consumption_unit_id
            )
            VALUES (
                'basis:serving',
                'formulation:1:v1',
                'per_label_portion',
                '2 capsules',
                'source:label:v1',
                2,
                'count',
                'consumption-unit:capsule'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO tracked_analytes (analyte_id, display_name)
            VALUES ('analyte:vitamin-d', 'Vitamin D')
            """
        )
        conn.execute(
            """
            INSERT INTO product_amounts (
                amount_id,
                formulation_id,
                subject_kind,
                analyte_id,
                source_id,
                resolution_status,
                evidence_status,
                raw_text
            )
            VALUES (
                'amount:unknown',
                'formulation:1:v1',
                'analyte',
                'analyte:vitamin-d',
                'source:label:v1',
                'unknown',
                'unknown',
                'Vitamin D amount unreadable'
            )
            """
        )

        amount = conn.execute(
            """
            SELECT value, unit, resolution_status, evidence_status
            FROM product_amounts
            WHERE amount_id = 'amount:unknown'
            """
        ).fetchone()
        assert amount == (None, None, "unknown", "unknown")

        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                """
                INSERT INTO product_amounts (
                    amount_id,
                    formulation_id,
                    subject_kind,
                    analyte_id,
                    source_id,
                    resolution_status,
                    evidence_status,
                    value,
                    unit,
                    amount_basis,
                    quantity_basis,
                    quantity_basis_id
                )
                VALUES (
                    'amount:invalid-resolved',
                    'formulation:1:v1',
                    'analyte',
                    'analyte:vitamin-d',
                    'source:label:v1',
                    'resolved',
                    'unknown',
                    1,
                    'ug',
                    'analyte',
                    'per_label_portion',
                    'basis:serving'
                )
                """
            )

        conn.execute(
            "INSERT INTO users (user_id, telegram_user_id) VALUES (%s, %s)",
            (user_id, 123456789),
        )
        conn.execute(
            """
            INSERT INTO user_profiles (user_id, timezone, locale)
            VALUES (%s, 'Europe/Helsinki', 'en')
            """,
            (user_id,),
        )
        conn.execute(
            """
            INSERT INTO user_supplements (
                instance_id,
                user_id,
                formulation_id,
                container_label
            )
            VALUES ('instance:1', %s, 'formulation:1:v1', 'opened bottle')
            """,
            (user_id,),
        )
        conn.execute(
            """
            INSERT INTO intake_plans (plan_id, version, tracked_instance_id)
            VALUES ('plan:1', '1', 'instance:1')
            """
        )
        conn.execute(
            """
            INSERT INTO planned_intake_events (
                plan_id,
                plan_version,
                event_id,
                consumption_unit_id,
                consumption_units,
                schedule_label
            )
            VALUES (
                'plan:1',
                '1',
                'planned:morning',
                'consumption-unit:capsule',
                1,
                'morning'
            )
            """
        )

        assert conn.execute("SELECT count(*) FROM intake_events").fetchone() == (0,)

        conn.execute(
            """
            INSERT INTO intake_events (
                event_id,
                tracked_instance_id,
                consumption_unit_id,
                consumption_units,
                consumed_at,
                confirmation_source_id,
                idempotency_key
            )
            VALUES (
                'intake:1',
                'instance:1',
                'consumption-unit:capsule',
                1,
                %s,
                'source:user-confirmation',
                'telegram-callback:update-1'
            )
            """,
            (datetime(2026, 9, 20, 8, 0, tzinfo=UTC),),
        )

        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(
                """
                INSERT INTO intake_events (
                    event_id,
                    tracked_instance_id,
                    consumption_unit_id,
                    consumption_units,
                    consumed_at,
                    confirmation_source_id,
                    idempotency_key
                )
                VALUES (
                    'intake:duplicate',
                    'instance:1',
                    'consumption-unit:capsule',
                    1,
                    %s,
                    'source:user-confirmation',
                    'telegram-callback:update-1'
                )
                """,
                (datetime(2026, 9, 20, 8, 0, tzinfo=UTC),),
            )

        conn.execute(
            """
            UPDATE intake_events
            SET entered_in_error_at = %s
            WHERE event_id = 'intake:1'
            """,
            (datetime(2026, 9, 20, 8, 5, tzinfo=UTC),),
        )
        conn.execute(
            """
            INSERT INTO intake_events (
                event_id,
                tracked_instance_id,
                consumption_unit_id,
                consumption_units,
                consumed_at,
                confirmation_source_id,
                idempotency_key,
                corrects_event_id
            )
            VALUES (
                'intake:2',
                'instance:1',
                'consumption-unit:capsule',
                2,
                %s,
                'source:user-confirmation',
                'correction:update-2',
                'intake:1'
            )
            """,
            (datetime(2026, 9, 20, 8, 0, tzinfo=UTC),),
        )

        assert conn.execute(
            """
            SELECT event_id, entered_in_error_at IS NOT NULL
            FROM intake_events
            ORDER BY event_id
            """
        ).fetchall() == [("intake:1", True), ("intake:2", False)]

        conn.execute(
            """
            INSERT INTO candidate_resolutions (
                candidate_set_id,
                user_id,
                confirmation_state,
                scientific_resolution_state
            )
            VALUES (
                'candidate-set:1',
                %s,
                'unconfirmed',
                'not_evaluated'
            )
            """,
            (user_id,),
        )
        conn.execute(
            """
            INSERT INTO entity_candidates (
                candidate_set_id,
                candidate_id,
                canonical_entity_id,
                source_id,
                state
            )
            VALUES
                (
                    'candidate-set:1',
                    'candidate:1',
                    'formulation:1:v1',
                    'source:label:v1',
                    'active'
                ),
                (
                    'candidate-set:1',
                    'candidate:2',
                    'formulation:other:v1',
                    'source:label:v1',
                    'active'
                )
            """
        )
        candidate_state = conn.execute(
            """
            SELECT confirmation_state, selected_candidate_id
            FROM candidate_resolutions
            WHERE candidate_set_id = 'candidate-set:1'
            """
        ).fetchone()
        assert candidate_state == ("unconfirmed", None)
        assert conn.execute(
            """
            SELECT count(*)
            FROM entity_candidates
            WHERE candidate_set_id = 'candidate-set:1'
            """
        ).fetchone() == (2,)

        conn.execute("DELETE FROM users WHERE user_id = %s", (user_id,))

        assert conn.execute("SELECT count(*) FROM user_profiles").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM user_supplements").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM intake_plans").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM intake_events").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM candidate_resolutions").fetchone() == (0,)

        assert conn.execute("SELECT count(*) FROM products").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM product_formulations").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM source_records").fetchone() == (2,)


def test_candidate_selection_requires_explicit_confirmation(
    postgres_schema: tuple[str, str],
) -> None:
    database_url, schema = postgres_schema
    user_id = uuid4()

    with _connect(database_url, schema) as conn:
        conn.execute(
            """
            INSERT INTO source_records (
                source_id,
                authority,
                source_type,
                title,
                stable_identifier,
                version,
                retrieved_on
            )
            VALUES (
                'source:candidate',
                'Catalog',
                'secondary_authoritative',
                'Catalog candidate source',
                'catalog:example',
                '1',
                DATE '2026-09-20'
            )
            """
        )
        conn.execute("INSERT INTO users (user_id) VALUES (%s)", (user_id,))
        conn.execute(
            """
            INSERT INTO candidate_resolutions (
                candidate_set_id,
                user_id,
                confirmation_state,
                scientific_resolution_state
            )
            VALUES ('candidate-set:2', %s, 'unconfirmed', 'unresolved')
            """,
            (user_id,),
        )
        conn.execute(
            """
            INSERT INTO entity_candidates (
                candidate_set_id,
                candidate_id,
                canonical_entity_id,
                source_id,
                state
            )
            VALUES (
                'candidate-set:2',
                'candidate:active',
                'formulation:a',
                'source:candidate',
                'active'
            )
            """
        )

        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                """
                UPDATE candidate_resolutions
                SET selected_candidate_id = 'candidate:active'
                WHERE candidate_set_id = 'candidate-set:2'
                """
            )

        with conn.transaction():
            conn.execute(
                """
                UPDATE candidate_resolutions
                SET confirmation_state = 'confirmed',
                    selected_candidate_id = 'candidate:active',
                    updated_at = CURRENT_TIMESTAMP
                WHERE candidate_set_id = 'candidate-set:2'
                """
            )

        assert conn.execute(
            """
            SELECT confirmation_state, selected_candidate_id
            FROM candidate_resolutions
            WHERE candidate_set_id = 'candidate-set:2'
            """
        ).fetchone() == ("confirmed", "candidate:active")
