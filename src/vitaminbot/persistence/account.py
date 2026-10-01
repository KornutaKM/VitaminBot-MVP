from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

DeletionOutcome = Literal["deleted", "stale", "not_found"]


class AccountStore:
    """Persistence boundary for user-owned export and account deletion."""

    def __init__(self, database_url: str, *, schema: str = "public") -> None:
        self._database_url = database_url
        self._schema = schema

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        conn: psycopg.Connection[dict[str, Any]] = psycopg.connect(
            self._database_url,
            row_factory=dict_row,
        )
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self._schema)))
        return conn

    @staticmethod
    def _rows(
        conn: psycopg.Connection[dict[str, Any]],
        query: str,
        params: tuple[object, ...],
    ) -> list[dict[str, Any]]:
        return list(conn.execute(query, params).fetchall())

    @staticmethod
    def _row(
        conn: psycopg.Connection[dict[str, Any]],
        query: str,
        params: tuple[object, ...],
    ) -> dict[str, Any] | None:
        return conn.execute(query, params).fetchone()

    def export_snapshot(self, telegram_user_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            user = self._row(
                conn,
                """
                SELECT user_id, telegram_user_id, created_at, updated_at
                FROM users
                WHERE telegram_user_id = %s
                """,
                (telegram_user_id,),
            )
            if user is None:
                return None

            user_id = user["user_id"]
            if not isinstance(user_id, UUID):
                raise RuntimeError("database returned an invalid user_id type")
            p = (user_id,)

            profile = self._row(
                conn,
                """
                SELECT timezone, locale, profile_version, created_at, updated_at
                FROM user_profiles
                WHERE user_id = %s
                """,
                p,
            )
            applicability = self._row(
                conn,
                """
                SELECT
                    completed_months,
                    completed_years,
                    sex_applicability,
                    life_stage,
                    physiological_condition,
                    revision,
                    updated_at
                FROM user_applicability_profiles
                WHERE user_id = %s
                """,
                p,
            )
            supplements = self._rows(
                conn,
                """
                SELECT
                    us.instance_id,
                    us.formulation_id,
                    us.container_label,
                    us.current_consumption_unit_id,
                    us.current_serving_basis_id,
                    us.revision,
                    us.lifecycle_status,
                    us.paused_at,
                    us.created_at,
                    us.updated_at,
                    inventory.remaining_units,
                    inventory.consumption_unit_id AS inventory_unit_id,
                    inventory.needs_reconciliation,
                    inventory.revision AS inventory_revision,
                    inventory.updated_at AS inventory_updated_at
                FROM user_supplements AS us
                LEFT JOIN supplement_inventory AS inventory
                  ON inventory.tracked_instance_id = us.instance_id
                WHERE us.user_id = %s
                ORDER BY us.created_at, us.instance_id
                """,
                p,
            )
            plans = self._rows(
                conn,
                """
                SELECT plan.*
                FROM intake_plans AS plan
                JOIN user_supplements AS us
                  ON us.instance_id = plan.tracked_instance_id
                WHERE us.user_id = %s
                ORDER BY plan.created_at, plan.plan_id, plan.version
                """,
                p,
            )
            planned_events = self._rows(
                conn,
                """
                SELECT event.*
                FROM planned_intake_events AS event
                JOIN intake_plans AS plan
                  ON plan.plan_id = event.plan_id
                 AND plan.version = event.plan_version
                JOIN user_supplements AS us
                  ON us.instance_id = plan.tracked_instance_id
                WHERE us.user_id = %s
                ORDER BY event.created_at, event.event_id
                """,
                p,
            )
            intake_events = self._rows(
                conn,
                """
                SELECT event.*
                FROM intake_events AS event
                JOIN user_supplements AS us
                  ON us.instance_id = event.tracked_instance_id
                WHERE us.user_id = %s
                ORDER BY event.consumed_at, event.event_id
                """,
                p,
            )
            occurrences = self._rows(
                conn,
                """
                SELECT occurrence.*
                FROM reminder_occurrences AS occurrence
                WHERE occurrence.user_id = %s
                ORDER BY occurrence.scheduled_at, occurrence.occurrence_id
                """,
                p,
            )
            deliveries = self._rows(
                conn,
                """
                SELECT delivery.*
                FROM reminder_delivery_attempts AS delivery
                JOIN reminder_occurrences AS occurrence
                  ON occurrence.occurrence_id = delivery.occurrence_id
                WHERE occurrence.user_id = %s
                ORDER BY delivery.claimed_at, delivery.delivery_id
                """,
                p,
            )
            occurrence_actions = self._rows(
                conn,
                """
                SELECT action.*
                FROM occurrence_actions AS action
                JOIN reminder_occurrences AS occurrence
                  ON occurrence.occurrence_id = action.occurrence_id
                WHERE occurrence.user_id = %s
                ORDER BY action.created_at, action.action_id
                """,
                p,
            )
            inventory_events = self._rows(
                conn,
                """
                SELECT event.*
                FROM inventory_events AS event
                JOIN user_supplements AS us
                  ON us.instance_id = event.tracked_instance_id
                WHERE us.user_id = %s
                ORDER BY event.created_at, event.event_id
                """,
                p,
            )
            manual_amounts = self._rows(
                conn,
                """
                SELECT *
                FROM kir122_manual_amounts
                WHERE user_id = %s
                ORDER BY tracked_instance_id, substance_key
                """,
                p,
            )
            confirmed_labels = self._rows(
                conn,
                """
                SELECT *
                FROM kir122_confirmed_label_records
                WHERE user_id = %s
                ORDER BY confirmed_at, candidate_id
                """,
                p,
            )
            iron_applicability = self._rows(
                conn,
                """
                SELECT scope_key, under_medical_supervision, revision, updated_at
                FROM iron_exposure_applicability
                WHERE user_id = %s
                ORDER BY scope_key
                """,
                p,
            )
            candidate_resolutions = self._rows(
                conn,
                """
                SELECT *
                FROM candidate_resolutions
                WHERE user_id = %s
                ORDER BY created_at, candidate_set_id
                """,
                p,
            )
            entity_candidates = self._rows(
                conn,
                """
                SELECT candidate.*
                FROM entity_candidates AS candidate
                JOIN candidate_resolutions AS resolution
                  ON resolution.candidate_set_id = candidate.candidate_set_id
                WHERE resolution.user_id = %s
                ORDER BY candidate.candidate_set_id, candidate.candidate_id
                """,
                p,
            )
            draft = self._row(
                conn,
                """
                SELECT *
                FROM manual_supplement_drafts
                WHERE user_id = %s
                """,
                p,
            )
            bot_session = self._row(
                conn,
                """
                SELECT *
                FROM bot_sessions
                WHERE user_id = %s
                """,
                p,
            )
            composition_session = self._row(
                conn,
                """
                SELECT *
                FROM kir122_composition_sessions
                WHERE user_id = %s
                """,
                p,
            )

            return {
                "user": user,
                "profile": profile,
                "applicability": applicability,
                "iron_exposure_applicability": iron_applicability,
                "supplements": supplements,
                "plans": plans,
                "planned_intake_events": planned_events,
                "intake_events": intake_events,
                "reminder_occurrences": occurrences,
                "reminder_delivery_attempts": deliveries,
                "occurrence_actions": occurrence_actions,
                "inventory_events": inventory_events,
                "manual_composition_amounts": manual_amounts,
                "confirmed_label_records": confirmed_labels,
                "candidate_resolutions": candidate_resolutions,
                "entity_candidates": entity_candidates,
                "active_manual_draft": draft,
                "active_bot_session": bot_session,
                "active_composition_session": composition_session,
            }

    def begin_deletion(
        self,
        telegram_user_id: int,
        *,
        token: str,
        expires_at: datetime,
    ) -> bool:
        with self._connect() as conn:
            user = self._row(
                conn,
                """
                SELECT user_id
                FROM users
                WHERE telegram_user_id = %s
                FOR UPDATE
                """,
                (telegram_user_id,),
            )
            if user is None:
                return False
            user_id = user["user_id"]
            conn.execute(
                """
                INSERT INTO account_deletion_intents (token, user_id, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET token = EXCLUDED.token,
                    expires_at = EXCLUDED.expires_at,
                    created_at = CURRENT_TIMESTAMP
                """,
                (token, user_id, expires_at),
            )
            return True

    def cancel_deletion(self, telegram_user_id: int, *, token: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                DELETE FROM account_deletion_intents AS intent
                USING users
                WHERE intent.user_id = users.user_id
                  AND users.telegram_user_id = %s
                  AND intent.token = %s
                RETURNING intent.token
                """,
                (telegram_user_id, token),
            ).fetchone()
            return row is not None

    def delete_account(
        self,
        telegram_user_id: int,
        *,
        token: str,
        now: datetime,
    ) -> DeletionOutcome:
        with self._connect() as conn:
            user = self._row(
                conn,
                """
                SELECT user_id
                FROM users
                WHERE telegram_user_id = %s
                FOR UPDATE
                """,
                (telegram_user_id,),
            )
            if user is None:
                return "not_found"

            user_id = user["user_id"]
            if not isinstance(user_id, UUID):
                raise RuntimeError("database returned an invalid user_id type")

            intent = self._row(
                conn,
                """
                SELECT expires_at
                FROM account_deletion_intents
                WHERE user_id = %s
                  AND token = %s
                FOR UPDATE
                """,
                (user_id, token),
            )
            if intent is None:
                return "stale"
            expires_at = intent["expires_at"]
            if not isinstance(expires_at, datetime):
                raise RuntimeError("database returned an invalid deletion expiry type")
            if expires_at <= now:
                conn.execute(
                    "DELETE FROM account_deletion_intents WHERE user_id = %s",
                    (user_id,),
                )
                return "stale"

            manual_records = self._rows(
                conn,
                """
                SELECT DISTINCT
                    us.formulation_id,
                    formulation.product_id,
                    source.source_id
                FROM user_supplements AS us
                JOIN product_formulations AS formulation
                  ON formulation.formulation_id = us.formulation_id
                JOIN formulation_sources AS source
                  ON source.formulation_id = formulation.formulation_id
                WHERE us.user_id = %s
                  AND us.formulation_id LIKE 'formulation:manual:%%'
                  AND source.source_id LIKE 'source:manual:%%'
                """,
                (user_id,),
            )

            conn.execute("DELETE FROM users WHERE user_id = %s", (user_id,))

            formulation_ids = {str(row["formulation_id"]) for row in manual_records}
            product_ids = {str(row["product_id"]) for row in manual_records}
            source_ids = {str(row["source_id"]) for row in manual_records}

            for formulation_id in formulation_ids:
                conn.execute(
                    """
                    DELETE FROM product_formulations AS formulation
                    WHERE formulation.formulation_id = %s
                      AND NOT EXISTS (
                          SELECT 1
                          FROM user_supplements
                          WHERE formulation_id = formulation.formulation_id
                      )
                    """,
                    (formulation_id,),
                )

            for product_id in product_ids:
                conn.execute(
                    """
                    DELETE FROM products AS product
                    WHERE product.product_id = %s
                      AND NOT EXISTS (
                          SELECT 1
                          FROM product_formulations
                          WHERE product_id = product.product_id
                      )
                    """,
                    (product_id,),
                )

            for source_id in source_ids:
                conn.execute(
                    """
                    DELETE FROM source_records AS source
                    WHERE source.source_id = %s
                      AND source.source_type = 'user_declaration'
                      AND NOT EXISTS (
                          SELECT 1 FROM formulation_sources WHERE source_id = source.source_id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM supply_relationships WHERE source_id = source.source_id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM consumption_units WHERE source_id = source.source_id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM product_servings WHERE source_id = source.source_id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM product_amounts WHERE source_id = source.source_id
                      )
                      AND NOT EXISTS (
                          SELECT 1
                          FROM product_amounts
                          WHERE derivation_authority_source_id = source.source_id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM entity_candidates WHERE source_id = source.source_id
                      )
                    """,
                    (source_id,),
                )

            return "deleted"
