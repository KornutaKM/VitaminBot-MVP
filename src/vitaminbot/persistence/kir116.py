from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


_COUNT_UNIT_LABELS = frozenset({"capsule", "tablet", "softgel", "scoop", "drop"})


class StoreError(RuntimeError):
    """Base error for KIR-116 persistence operations."""


class InvalidTransition(StoreError):
    """Raised when an input does not match the durable interaction state."""


class StaleAction(StoreError):
    """Raised when a callback targets an obsolete revision."""


class RecordNotFound(StoreError):
    """Raised when a user-owned record does not exist."""


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    timezone: str | None
    locale: str | None
    version: int


@dataclass(frozen=True, slots=True)
class ManualDraft:
    draft_id: str
    product_name: str | None
    unit_label: str | None
    units_per_serving: Decimal | None
    revision: int


@dataclass(frozen=True, slots=True)
class BotSession:
    state: str
    draft_id: str | None
    target_instance_id: str | None
    pending_text: str | None
    pending_quantity: Decimal | None
    expected_revision: int | None
    revision: int


@dataclass(frozen=True, slots=True)
class SupplementRecord:
    instance_id: str
    name: str
    revision: int
    formulation_id: str
    unit_id: str
    unit_label: str
    units_per_serving: Decimal
    plan_quantity: Decimal | None
    plan_bucket: str | None
    plan_unit_label: str | None
    plan_revision: int | None


class KIR116Store:
    """PostgreSQL repository for the Telegram/manual-entry MVP slice."""

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
    def _claim_action(
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        action_key: str,
        action_type: str,
    ) -> tuple[bool, str | None]:
        row = conn.execute(
            """
            INSERT INTO bot_action_receipts (user_id, action_key, action_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, action_key) DO NOTHING
            RETURNING result_ref
            """,
            (user_id, action_key, action_type),
        ).fetchone()
        if row is not None:
            return True, row["result_ref"]

        existing = conn.execute(
            """
            SELECT result_ref
            FROM bot_action_receipts
            WHERE user_id = %s AND action_key = %s
            """,
            (user_id, action_key),
        ).fetchone()
        return False, None if existing is None else existing["result_ref"]

    @staticmethod
    def _complete_action(
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        action_key: str,
        result_ref: str | None,
    ) -> None:
        conn.execute(
            """
            UPDATE bot_action_receipts
            SET result_ref = %s
            WHERE user_id = %s AND action_key = %s
            """,
            (result_ref, user_id, action_key),
        )

    @staticmethod
    def _session_from_row(row: dict[str, Any] | None) -> BotSession | None:
        if row is None or row["state"] == "idle":
            return None
        return BotSession(
            state=row["state"],
            draft_id=row["draft_id"],
            target_instance_id=row["target_instance_id"],
            pending_text=row["pending_text"],
            pending_quantity=row["pending_quantity"],
            expected_revision=row["expected_revision"],
            revision=row["revision"],
        )

    @staticmethod
    def _draft_from_row(row: dict[str, Any]) -> ManualDraft:
        return ManualDraft(
            draft_id=row["draft_id"],
            product_name=row["product_name"],
            unit_label=row["unit_label"],
            units_per_serving=row["units_per_serving"],
            revision=row["revision"],
        )

    @staticmethod
    def _supplement_from_row(row: dict[str, Any]) -> SupplementRecord:
        return SupplementRecord(
            instance_id=row["instance_id"],
            name=row["container_label"],
            revision=row["revision"],
            formulation_id=row["formulation_id"],
            unit_id=row["unit_id"],
            unit_label=row["unit_label"],
            units_per_serving=row["units_per_serving"],
            plan_quantity=row["plan_quantity"],
            plan_bucket=row["plan_bucket"],
            plan_unit_label=row["plan_unit_label"],
            plan_revision=row["plan_revision"],
        )

    @staticmethod
    def _upsert_session(
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        *,
        state: str,
        draft_id: str | None = None,
        target_instance_id: str | None = None,
        pending_text: str | None = None,
        pending_quantity: Decimal | None = None,
        expected_revision: int | None = None,
    ) -> BotSession:
        row = conn.execute(
            """
            INSERT INTO bot_sessions (
                user_id,
                state,
                draft_id,
                target_instance_id,
                pending_text,
                pending_quantity,
                expected_revision
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET state = EXCLUDED.state,
                draft_id = EXCLUDED.draft_id,
                target_instance_id = EXCLUDED.target_instance_id,
                pending_text = EXCLUDED.pending_text,
                pending_quantity = EXCLUDED.pending_quantity,
                expected_revision = EXCLUDED.expected_revision,
                revision = bot_sessions.revision + 1,
                updated_at = CURRENT_TIMESTAMP
            RETURNING
                state,
                draft_id,
                target_instance_id,
                pending_text,
                pending_quantity,
                expected_revision,
                revision
            """,
            (
                user_id,
                state,
                draft_id,
                target_instance_id,
                pending_text,
                pending_quantity,
                expected_revision,
            ),
        ).fetchone()
        assert row is not None
        session = KIR116Store._session_from_row(row)
        assert session is not None
        return session

    @staticmethod
    def _clear_session(conn: psycopg.Connection[dict[str, Any]], user_id: UUID) -> None:
        conn.execute(
            """
            INSERT INTO bot_sessions (user_id, state)
            VALUES (%s, 'idle')
            ON CONFLICT (user_id) DO UPDATE
            SET state = 'idle',
                draft_id = NULL,
                target_instance_id = NULL,
                pending_text = NULL,
                pending_quantity = NULL,
                expected_revision = NULL,
                revision = bot_sessions.revision + 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id,),
        )

    def ensure_user(self, telegram_user_id: int) -> UUID:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO users (user_id, telegram_user_id)
                VALUES (%s, %s)
                ON CONFLICT (telegram_user_id) DO UPDATE
                SET updated_at = CURRENT_TIMESTAMP
                RETURNING user_id
                """,
                (uuid4(), telegram_user_id),
            ).fetchone()
            assert row is not None
            raw_user_id = row["user_id"]
            if not isinstance(raw_user_id, UUID):
                raise StoreError("database returned an invalid user_id type")
            return raw_user_id

    def profile(self, user_id: UUID) -> ProfileRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT timezone, locale, profile_version
                FROM user_profiles
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return ProfileRecord(timezone=None, locale=None, version=0)
        return ProfileRecord(
            timezone=row["timezone"],
            locale=row["locale"],
            version=row["profile_version"],
        )

    def get_session(self, user_id: UUID) -> BotSession | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    state,
                    draft_id,
                    target_instance_id,
                    pending_text,
                    pending_quantity,
                    expected_revision,
                    revision
                FROM bot_sessions
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
        return self._session_from_row(row)

    def get_draft(self, user_id: UUID) -> ManualDraft | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT draft_id, product_name, unit_label, units_per_serving, revision
                FROM manual_supplement_drafts
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
        return None if row is None else self._draft_from_row(row)

    def begin_manual(self, user_id: UUID, action_key: str) -> ManualDraft:
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "begin_manual")
            existing = conn.execute(
                """
                SELECT draft_id, product_name, unit_label, units_per_serving, revision
                FROM manual_supplement_drafts
                WHERE user_id = %s
                FOR UPDATE
                """,
                (user_id,),
            ).fetchone()
            if existing is not None:
                draft = self._draft_from_row(existing)
            else:
                draft_id = uuid4().hex[:16]
                row = conn.execute(
                    """
                    INSERT INTO manual_supplement_drafts (draft_id, user_id)
                    VALUES (%s, %s)
                    RETURNING draft_id, product_name, unit_label, units_per_serving, revision
                    """,
                    (draft_id, user_id),
                ).fetchone()
                assert row is not None
                draft = self._draft_from_row(row)

            if claimed:
                if draft.product_name is None:
                    state = "manual_name"
                elif draft.unit_label is None:
                    state = "manual_unit"
                elif draft.units_per_serving is None:
                    state = "manual_serving_quantity"
                else:
                    state = "manual_review"
                self._upsert_session(
                    conn,
                    user_id,
                    state=state,
                    draft_id=draft.draft_id,
                    expected_revision=draft.revision,
                )
                self._complete_action(conn, user_id, action_key, draft.draft_id)
            return draft

    def set_manual_name(self, user_id: UUID, action_key: str, name: str) -> ManualDraft:
        with self._connect() as conn:
            claimed, result_ref = self._claim_action(conn, user_id, action_key, "manual_name")
            if not claimed:
                draft = self._draft_by_ref(conn, user_id, result_ref)
                if draft is None:
                    draft = self._draft_for_user(conn, user_id)
                if draft is None:
                    raise InvalidTransition("manual draft is no longer active")
                return draft

            session = self._locked_session(conn, user_id, "manual_name")
            assert session.draft_id is not None
            row = conn.execute(
                """
                UPDATE manual_supplement_drafts
                SET product_name = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE draft_id = %s
                  AND user_id = %s
                  AND revision = %s
                RETURNING draft_id, product_name, unit_label, units_per_serving, revision
                """,
                (name, session.draft_id, user_id, session.expected_revision),
            ).fetchone()
            if row is None:
                raise StaleAction("manual draft changed before name was saved")
            draft = self._draft_from_row(row)
            self._upsert_session(
                conn,
                user_id,
                state="manual_unit",
                draft_id=draft.draft_id,
                expected_revision=draft.revision,
            )
            self._complete_action(conn, user_id, action_key, draft.draft_id)
            return draft

    def set_manual_unit(
        self,
        user_id: UUID,
        action_key: str,
        draft_id: str,
        expected_revision: int,
        unit_label: str,
    ) -> ManualDraft:
        if unit_label not in _COUNT_UNIT_LABELS:
            raise ValueError("manual entry supports count-based product units only")
        with self._connect() as conn:
            claimed, result_ref = self._claim_action(conn, user_id, action_key, "manual_unit")
            if not claimed:
                draft = self._draft_by_ref(conn, user_id, result_ref)
                if draft is None:
                    draft = self._draft_for_user(conn, user_id)
                if draft is None:
                    raise InvalidTransition("manual draft is no longer active")
                return draft

            session = self._locked_session(conn, user_id, "manual_unit")
            if session.draft_id != draft_id or session.expected_revision != expected_revision:
                raise StaleAction("manual unit callback is stale")
            row = conn.execute(
                """
                UPDATE manual_supplement_drafts
                SET unit_label = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE draft_id = %s
                  AND user_id = %s
                  AND revision = %s
                RETURNING draft_id, product_name, unit_label, units_per_serving, revision
                """,
                (unit_label, draft_id, user_id, expected_revision),
            ).fetchone()
            if row is None:
                raise StaleAction("manual draft changed before unit was saved")
            draft = self._draft_from_row(row)
            self._upsert_session(
                conn,
                user_id,
                state="manual_serving_quantity",
                draft_id=draft.draft_id,
                expected_revision=draft.revision,
            )
            self._complete_action(conn, user_id, action_key, draft.draft_id)
            return draft

    def set_manual_serving_quantity(
        self,
        user_id: UUID,
        action_key: str,
        quantity: Decimal,
    ) -> ManualDraft:
        with self._connect() as conn:
            claimed, result_ref = self._claim_action(
                conn, user_id, action_key, "manual_serving_quantity"
            )
            if not claimed:
                draft = self._draft_by_ref(conn, user_id, result_ref)
                if draft is None:
                    draft = self._draft_for_user(conn, user_id)
                if draft is None:
                    raise InvalidTransition("manual draft is no longer active")
                return draft

            session = self._locked_session(conn, user_id, "manual_serving_quantity")
            assert session.draft_id is not None
            row = conn.execute(
                """
                UPDATE manual_supplement_drafts
                SET units_per_serving = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE draft_id = %s
                  AND user_id = %s
                  AND revision = %s
                RETURNING draft_id, product_name, unit_label, units_per_serving, revision
                """,
                (quantity, session.draft_id, user_id, session.expected_revision),
            ).fetchone()
            if row is None:
                raise StaleAction("manual draft changed before serving was saved")
            draft = self._draft_from_row(row)
            self._upsert_session(
                conn,
                user_id,
                state="manual_review",
                draft_id=draft.draft_id,
                expected_revision=draft.revision,
            )
            self._complete_action(conn, user_id, action_key, draft.draft_id)
            return draft

    def restart_manual_edit(
        self,
        user_id: UUID,
        action_key: str,
        draft_id: str,
        expected_revision: int,
    ) -> ManualDraft:
        with self._connect() as conn:
            claimed, result_ref = self._claim_action(
                conn, user_id, action_key, "restart_manual_edit"
            )
            draft = self._draft_by_ref(conn, user_id, draft_id)
            if draft is None:
                if not claimed and result_ref is not None:
                    duplicate = self._draft_by_ref(conn, user_id, result_ref)
                    if duplicate is not None:
                        return duplicate
                raise InvalidTransition("manual draft is no longer active")
            if draft.revision != expected_revision:
                raise StaleAction("manual edit callback is stale")
            if claimed:
                self._upsert_session(
                    conn,
                    user_id,
                    state="manual_name",
                    draft_id=draft.draft_id,
                    expected_revision=draft.revision,
                )
                self._complete_action(conn, user_id, action_key, draft.draft_id)
            return draft

    def confirm_manual(
        self,
        user_id: UUID,
        action_key: str,
        draft_id: str,
        expected_revision: int,
    ) -> SupplementRecord:
        with self._connect() as conn:
            claimed, result_ref = self._claim_action(conn, user_id, action_key, "confirm_manual")
            if not claimed and result_ref is not None:
                return self._supplement_by_id(conn, user_id, result_ref)

            row = conn.execute(
                """
                SELECT draft_id, product_name, unit_label, units_per_serving, revision
                FROM manual_supplement_drafts
                WHERE draft_id = %s AND user_id = %s
                FOR UPDATE
                """,
                (draft_id, user_id),
            ).fetchone()
            if row is None:
                raise InvalidTransition("manual draft is no longer active")
            draft = self._draft_from_row(row)
            if draft.revision != expected_revision:
                raise StaleAction("manual confirmation callback is stale")
            if (
                draft.product_name is None
                or draft.unit_label is None
                or draft.units_per_serving is None
            ):
                raise InvalidTransition("manual draft is incomplete")

            token = draft.draft_id
            source_id = f"source:manual:{token}"
            product_id = f"product:manual:{token}"
            formulation_id = f"formulation:manual:{token}"
            unit_id = f"unit:manual:{token}"
            basis_id = f"basis:manual:{token}"
            instance_id = f"instance:manual:{token}"

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
                    %s,
                    'User declaration',
                    'user_declaration',
                    'Manual supplement entry',
                    %s,
                    '1',
                    CURRENT_DATE
                )
                """,
                (source_id, f"manual-entry:{token}"),
            )
            conn.execute(
                """
                INSERT INTO products (
                    product_id,
                    name,
                    market_jurisdiction_status
                )
                VALUES (%s, 'Manual supplement record', 'unknown')
                """,
                (product_id,),
            )
            conn.execute(
                """
                INSERT INTO product_formulations (formulation_id, product_id, version)
                VALUES (%s, %s, '1')
                """,
                (formulation_id, product_id),
            )
            conn.execute(
                """
                INSERT INTO formulation_sources (formulation_id, source_id)
                VALUES (%s, %s)
                """,
                (formulation_id, source_id),
            )
            conn.execute(
                """
                INSERT INTO consumption_units (
                    unit_id,
                    formulation_id,
                    label_name,
                    source_id
                )
                VALUES (%s, %s, %s, %s)
                """,
                (unit_id, formulation_id, draft.unit_label, source_id),
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
                    %s,
                    %s,
                    'per_label_portion',
                    %s,
                    %s,
                    %s,
                    'count',
                    %s
                )
                """,
                (
                    basis_id,
                    formulation_id,
                    f"{draft.units_per_serving} {draft.unit_label}",
                    source_id,
                    draft.units_per_serving,
                    unit_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO user_supplements (
                    instance_id,
                    user_id,
                    formulation_id,
                    container_label,
                    current_consumption_unit_id,
                    current_serving_basis_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    instance_id,
                    user_id,
                    formulation_id,
                    draft.product_name,
                    unit_id,
                    basis_id,
                ),
            )
            self._clear_session(conn, user_id)
            conn.execute(
                "DELETE FROM manual_supplement_drafts WHERE draft_id = %s",
                (draft_id,),
            )
            self._complete_action(conn, user_id, action_key, instance_id)
            return self._supplement_by_id(conn, user_id, instance_id)

    def list_supplements(self, user_id: UUID) -> tuple[SupplementRecord, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                self._supplement_query() + " ORDER BY us.created_at, us.instance_id",
                (user_id,),
            ).fetchall()
        return tuple(self._supplement_from_row(row) for row in rows)

    def supplement(self, user_id: UUID, instance_id: str) -> SupplementRecord:
        with self._connect() as conn:
            return self._supplement_by_id(conn, user_id, instance_id)

    def begin_plan(
        self,
        user_id: UUID,
        action_key: str,
        instance_id: str,
        expected_revision: int,
    ) -> BotSession:
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "begin_plan")
            supplement = self._locked_supplement(conn, user_id, instance_id)
            if supplement.revision != expected_revision:
                raise StaleAction("supplement changed before plan editing")
            if not claimed:
                session = self._session_for_user(conn, user_id)
                if session is None:
                    raise InvalidTransition("plan session is no longer active")
                return session
            session = self._upsert_session(
                conn,
                user_id,
                state="plan_quantity",
                target_instance_id=instance_id,
                expected_revision=expected_revision,
            )
            self._complete_action(conn, user_id, action_key, instance_id)
            return session

    def set_plan_quantity(
        self,
        user_id: UUID,
        action_key: str,
        quantity: Decimal,
    ) -> BotSession:
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "plan_quantity")
            session = self._locked_session(conn, user_id, "plan_quantity")
            if not claimed:
                current = self._session_for_user(conn, user_id)
                return current or session
            updated = self._upsert_session(
                conn,
                user_id,
                state="plan_bucket",
                target_instance_id=session.target_instance_id,
                pending_quantity=quantity,
                expected_revision=session.expected_revision,
            )
            self._complete_action(conn, user_id, action_key, session.target_instance_id)
            return updated

    def save_plan(
        self,
        user_id: UUID,
        action_key: str,
        bucket: str,
        expected_session_revision: int,
    ) -> SupplementRecord:
        with self._connect() as conn:
            claimed, result_ref = self._claim_action(conn, user_id, action_key, "save_plan")
            if not claimed and result_ref is not None:
                return self._supplement_by_id(conn, user_id, result_ref)

            session = self._locked_session(conn, user_id, "plan_bucket")
            if session.revision != expected_session_revision:
                raise StaleAction("plan bucket callback is stale")
            if session.target_instance_id is None or session.pending_quantity is None:
                raise InvalidTransition("plan session is incomplete")
            supplement = self._locked_supplement(conn, user_id, session.target_instance_id)
            if supplement.revision != session.expected_revision:
                raise StaleAction("supplement changed before plan was saved")

            head = conn.execute(
                """
                SELECT plan_id, plan_version, revision
                FROM intake_plan_heads
                WHERE tracked_instance_id = %s
                FOR UPDATE
                """,
                (supplement.instance_id,),
            ).fetchone()
            next_revision = 1 if head is None else int(head["revision"]) + 1
            plan_id = f"plan:{supplement.instance_id}" if head is None else str(head["plan_id"])
            plan_version = str(next_revision)
            conn.execute(
                """
                INSERT INTO intake_plans (
                    plan_id,
                    version,
                    tracked_instance_id,
                    formulation_id
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    plan_id,
                    plan_version,
                    supplement.instance_id,
                    supplement.formulation_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO planned_intake_events (
                    plan_id,
                    plan_version,
                    formulation_id,
                    event_id,
                    consumption_unit_id,
                    consumption_units,
                    schedule_label
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    plan_id,
                    plan_version,
                    supplement.formulation_id,
                    f"routine:{bucket}",
                    supplement.unit_id,
                    session.pending_quantity,
                    bucket,
                ),
            )
            conn.execute(
                """
                INSERT INTO intake_plan_heads (
                    tracked_instance_id,
                    plan_id,
                    plan_version,
                    revision
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tracked_instance_id) DO UPDATE
                SET plan_id = EXCLUDED.plan_id,
                    plan_version = EXCLUDED.plan_version,
                    revision = EXCLUDED.revision,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    supplement.instance_id,
                    plan_id,
                    plan_version,
                    next_revision,
                ),
            )
            self._clear_session(conn, user_id)
            self._complete_action(conn, user_id, action_key, supplement.instance_id)
            return self._supplement_by_id(conn, user_id, supplement.instance_id)

    def begin_profile_edit(
        self,
        user_id: UUID,
        action_key: str,
        field: str,
        expected_version: int,
    ) -> BotSession:
        if field not in {"timezone", "locale"}:
            raise ValueError("unsupported profile field")
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, f"profile_{field}_begin")
            current = conn.execute(
                """
                SELECT profile_version
                FROM user_profiles
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
            current_version = 0 if current is None else int(current["profile_version"])
            if current_version != expected_version:
                raise StaleAction("profile changed before editing started")
            if not claimed:
                session = self._session_for_user(conn, user_id)
                if session is None:
                    raise InvalidTransition("profile edit is no longer active")
                return session
            session = self._upsert_session(
                conn,
                user_id,
                state=f"profile_{field}",
                expected_revision=expected_version,
            )
            self._complete_action(conn, user_id, action_key, field)
            return session

    def save_profile_field(
        self,
        user_id: UUID,
        action_key: str,
        field: str,
        value: str,
    ) -> ProfileRecord:
        if field not in {"timezone", "locale"}:
            raise ValueError("unsupported profile field")
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, f"profile_{field}_save")
            session = self._locked_session(conn, user_id, f"profile_{field}")
            if not claimed:
                return self._profile_in_connection(conn, user_id)

            expected = session.expected_revision
            if expected == 0:
                if field == "timezone":
                    row = conn.execute(
                        """
                        INSERT INTO user_profiles (user_id, timezone, profile_version)
                        VALUES (%s, %s, 1)
                        ON CONFLICT (user_id) DO NOTHING
                        RETURNING timezone, locale, profile_version
                        """,
                        (user_id, value),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        INSERT INTO user_profiles (user_id, locale, profile_version)
                        VALUES (%s, %s, 1)
                        ON CONFLICT (user_id) DO NOTHING
                        RETURNING timezone, locale, profile_version
                        """,
                        (user_id, value),
                    ).fetchone()
            else:
                query = sql.SQL(
                    """
                    UPDATE user_profiles
                    SET {field} = %s,
                        profile_version = profile_version + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                      AND profile_version = %s
                    RETURNING timezone, locale, profile_version
                    """
                ).format(field=sql.Identifier(field))
                row = conn.execute(query, (value, user_id, expected)).fetchone()

            if row is None:
                raise StaleAction("profile changed before the value was saved")
            self._clear_session(conn, user_id)
            self._complete_action(conn, user_id, action_key, field)
            return ProfileRecord(
                timezone=row["timezone"],
                locale=row["locale"],
                version=row["profile_version"],
            )

    def begin_edit_name(
        self,
        user_id: UUID,
        action_key: str,
        instance_id: str,
        expected_revision: int,
    ) -> BotSession:
        return self._begin_supplement_edit(
            user_id,
            action_key,
            instance_id,
            expected_revision,
            "edit_name",
        )

    def save_edit_name(
        self,
        user_id: UUID,
        action_key: str,
        name: str,
    ) -> SupplementRecord:
        with self._connect() as conn:
            claimed, result_ref = self._claim_action(conn, user_id, action_key, "edit_name_save")
            if not claimed and result_ref is not None:
                return self._supplement_by_id(conn, user_id, result_ref)
            session = self._locked_session(conn, user_id, "edit_name")
            assert session.target_instance_id is not None
            row = conn.execute(
                """
                UPDATE user_supplements
                SET container_label = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE instance_id = %s
                  AND user_id = %s
                  AND revision = %s
                RETURNING instance_id
                """,
                (
                    name,
                    session.target_instance_id,
                    user_id,
                    session.expected_revision,
                ),
            ).fetchone()
            if row is None:
                raise StaleAction("supplement changed before name was saved")
            self._clear_session(conn, user_id)
            self._complete_action(conn, user_id, action_key, row["instance_id"])
            return self._supplement_by_id(conn, user_id, row["instance_id"])

    def begin_edit_serving(
        self,
        user_id: UUID,
        action_key: str,
        instance_id: str,
        expected_revision: int,
    ) -> BotSession:
        return self._begin_supplement_edit(
            user_id,
            action_key,
            instance_id,
            expected_revision,
            "edit_serving_unit",
        )

    def set_edit_serving_unit(
        self,
        user_id: UUID,
        action_key: str,
        unit_label: str,
        expected_session_revision: int,
    ) -> BotSession:
        if unit_label not in _COUNT_UNIT_LABELS:
            raise ValueError("serving edit supports count-based product units only")
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "edit_serving_unit")
            session = self._locked_session(conn, user_id, "edit_serving_unit")
            if session.revision != expected_session_revision:
                raise StaleAction("serving-unit callback is stale")
            if not claimed:
                current = self._session_for_user(conn, user_id)
                return current or session
            updated = self._upsert_session(
                conn,
                user_id,
                state="edit_serving_quantity",
                target_instance_id=session.target_instance_id,
                pending_text=unit_label,
                expected_revision=session.expected_revision,
            )
            self._complete_action(conn, user_id, action_key, session.target_instance_id)
            return updated

    def save_edit_serving_quantity(
        self,
        user_id: UUID,
        action_key: str,
        quantity: Decimal,
    ) -> SupplementRecord:
        with self._connect() as conn:
            claimed, result_ref = self._claim_action(
                conn, user_id, action_key, "edit_serving_quantity"
            )
            if not claimed and result_ref is not None:
                return self._supplement_by_id(conn, user_id, result_ref)
            session = self._locked_session(conn, user_id, "edit_serving_quantity")
            if (
                session.target_instance_id is None
                or session.pending_text is None
                or session.expected_revision is None
            ):
                raise InvalidTransition("serving edit is incomplete")
            if session.pending_text not in _COUNT_UNIT_LABELS:
                raise ValueError("serving edit supports count-based product units only")

            supplement = self._locked_supplement(conn, user_id, session.target_instance_id)
            if supplement.revision != session.expected_revision:
                raise StaleAction("supplement changed before serving was saved")

            source = conn.execute(
                """
                SELECT source_id
                FROM consumption_units
                WHERE formulation_id = %s AND unit_id = %s
                """,
                (supplement.formulation_id, supplement.unit_id),
            ).fetchone()
            if source is None:
                raise InvalidTransition("current serving provenance is missing")

            next_revision = supplement.revision + 1
            token = supplement.instance_id.removeprefix("instance:manual:")
            new_unit_id = f"unit:manual:{token}:r{next_revision}"
            new_basis_id = f"basis:manual:{token}:r{next_revision}"

            conn.execute(
                """
                INSERT INTO consumption_units (
                    unit_id,
                    formulation_id,
                    label_name,
                    source_id
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    new_unit_id,
                    supplement.formulation_id,
                    session.pending_text,
                    source["source_id"],
                ),
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
                    %s,
                    %s,
                    'per_label_portion',
                    %s,
                    %s,
                    %s,
                    'count',
                    %s
                )
                """,
                (
                    new_basis_id,
                    supplement.formulation_id,
                    f"{quantity} {session.pending_text}",
                    source["source_id"],
                    quantity,
                    new_unit_id,
                ),
            )
            row = conn.execute(
                """
                UPDATE user_supplements
                SET current_consumption_unit_id = %s,
                    current_serving_basis_id = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE instance_id = %s
                  AND user_id = %s
                  AND revision = %s
                RETURNING instance_id
                """,
                (
                    new_unit_id,
                    new_basis_id,
                    supplement.instance_id,
                    user_id,
                    session.expected_revision,
                ),
            ).fetchone()
            if row is None:
                raise StaleAction("supplement changed before serving was saved")
            self._clear_session(conn, user_id)
            self._complete_action(conn, user_id, action_key, supplement.instance_id)
            return self._supplement_by_id(conn, user_id, supplement.instance_id)

    def remove_supplement(
        self,
        user_id: UUID,
        action_key: str,
        instance_id: str,
        expected_revision: int,
    ) -> bool:
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "remove_supplement")
            if not claimed:
                existing = conn.execute(
                    """
                    SELECT 1
                    FROM user_supplements
                    WHERE user_id = %s AND instance_id = %s
                    """,
                    (user_id, instance_id),
                ).fetchone()
                return existing is None

            row = conn.execute(
                """
                SELECT
                    us.formulation_id,
                    pf.product_id,
                    fs.source_id
                FROM user_supplements AS us
                JOIN product_formulations AS pf
                  ON pf.formulation_id = us.formulation_id
                JOIN formulation_sources AS fs
                  ON fs.formulation_id = pf.formulation_id
                WHERE us.user_id = %s
                  AND us.instance_id = %s
                  AND us.revision = %s
                FOR UPDATE
                """,
                (user_id, instance_id, expected_revision),
            ).fetchone()
            if row is None:
                current = conn.execute(
                    """
                    SELECT 1
                    FROM user_supplements
                    WHERE user_id = %s AND instance_id = %s
                    """,
                    (user_id, instance_id),
                ).fetchone()
                if current is None:
                    return True
                raise StaleAction("supplement changed before removal")

            formulation_id = str(row["formulation_id"])
            product_id = str(row["product_id"])
            source_id = str(row["source_id"])
            if not formulation_id.startswith("formulation:manual:"):
                raise InvalidTransition(
                    "KIR-116 only removes supplements created by the manual flow"
                )

            conn.execute(
                "DELETE FROM user_supplements WHERE user_id = %s AND instance_id = %s",
                (user_id, instance_id),
            )
            conn.execute(
                "DELETE FROM product_formulations WHERE formulation_id = %s",
                (formulation_id,),
            )
            conn.execute(
                """
                DELETE FROM products
                WHERE product_id = %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM product_formulations
                      WHERE product_id = %s
                  )
                """,
                (product_id, product_id),
            )
            conn.execute(
                """
                DELETE FROM source_records
                WHERE source_id = %s
                  AND source_type = 'user_declaration'
                """,
                (source_id,),
            )
            self._complete_action(conn, user_id, action_key, instance_id)
            return True

    def cancel_pending(self, user_id: UUID) -> None:
        with self._connect() as conn:
            session = self._session_for_user(conn, user_id)
            draft_id = None if session is None else session.draft_id
            self._clear_session(conn, user_id)
            if draft_id is not None:
                conn.execute(
                    """
                    DELETE FROM manual_supplement_drafts
                    WHERE user_id = %s AND draft_id = %s
                    """,
                    (user_id, draft_id),
                )

    def _begin_supplement_edit(
        self,
        user_id: UUID,
        action_key: str,
        instance_id: str,
        expected_revision: int,
        state: str,
    ) -> BotSession:
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, state)
            supplement = self._locked_supplement(conn, user_id, instance_id)
            if supplement.revision != expected_revision:
                raise StaleAction("supplement edit callback is stale")
            if not claimed:
                session = self._session_for_user(conn, user_id)
                if session is None:
                    raise InvalidTransition("supplement edit is no longer active")
                return session
            session = self._upsert_session(
                conn,
                user_id,
                state=state,
                target_instance_id=instance_id,
                expected_revision=expected_revision,
            )
            self._complete_action(conn, user_id, action_key, instance_id)
            return session

    def _locked_session(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        expected_state: str,
    ) -> BotSession:
        row = conn.execute(
            """
            SELECT
                state,
                draft_id,
                target_instance_id,
                pending_text,
                pending_quantity,
                expected_revision,
                revision
            FROM bot_sessions
            WHERE user_id = %s
            FOR UPDATE
            """,
            (user_id,),
        ).fetchone()
        session = self._session_from_row(row)
        if session is None or session.state != expected_state:
            raise InvalidTransition(f"expected interaction state {expected_state}")
        return session

    def _session_for_user(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
    ) -> BotSession | None:
        row = conn.execute(
            """
            SELECT
                state,
                draft_id,
                target_instance_id,
                pending_text,
                pending_quantity,
                expected_revision,
                revision
            FROM bot_sessions
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
        return self._session_from_row(row)

    def _draft_for_user(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
    ) -> ManualDraft | None:
        row = conn.execute(
            """
            SELECT draft_id, product_name, unit_label, units_per_serving, revision
            FROM manual_supplement_drafts
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
        return None if row is None else self._draft_from_row(row)

    def _draft_by_ref(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        draft_id: str | None,
    ) -> ManualDraft | None:
        if draft_id is None:
            return None
        row = conn.execute(
            """
            SELECT draft_id, product_name, unit_label, units_per_serving, revision
            FROM manual_supplement_drafts
            WHERE user_id = %s AND draft_id = %s
            """,
            (user_id, draft_id),
        ).fetchone()
        return None if row is None else self._draft_from_row(row)

    def _profile_in_connection(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
    ) -> ProfileRecord:
        row = conn.execute(
            """
            SELECT timezone, locale, profile_version
            FROM user_profiles
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return ProfileRecord(timezone=None, locale=None, version=0)
        return ProfileRecord(
            timezone=row["timezone"],
            locale=row["locale"],
            version=row["profile_version"],
        )

    def _locked_supplement(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        instance_id: str,
    ) -> SupplementRecord:
        row = conn.execute(
            self._supplement_query() + " AND us.instance_id = %s FOR UPDATE OF us",
            (user_id, instance_id),
        ).fetchone()
        if row is None:
            raise RecordNotFound("supplement not found")
        return self._supplement_from_row(row)

    def _supplement_by_id(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        instance_id: str,
    ) -> SupplementRecord:
        row = conn.execute(
            self._supplement_query() + " AND us.instance_id = %s",
            (user_id, instance_id),
        ).fetchone()
        if row is None:
            raise RecordNotFound("supplement not found")
        return self._supplement_from_row(row)

    @staticmethod
    def _supplement_query() -> str:
        query = """
            SELECT
                us.instance_id,
                us.container_label,
                us.revision,
                us.formulation_id,
                unit.unit_id,
                unit.label_name AS unit_label,
                serving.basis_quantity AS units_per_serving,
                planned.consumption_units AS plan_quantity,
                planned.schedule_label AS plan_bucket,
                plan_unit.label_name AS plan_unit_label,
                head.revision AS plan_revision
            FROM user_supplements AS us
            JOIN consumption_units AS unit
              ON unit.formulation_id = us.formulation_id
             AND unit.unit_id = us.current_consumption_unit_id
            JOIN product_servings AS serving
              ON serving.formulation_id = us.formulation_id
             AND serving.basis_id = us.current_serving_basis_id
             AND serving.consumption_unit_id = unit.unit_id
            LEFT JOIN intake_plan_heads AS head
              ON head.tracked_instance_id = us.instance_id
            LEFT JOIN planned_intake_events AS planned
              ON planned.plan_id = head.plan_id
             AND planned.plan_version = head.plan_version
            LEFT JOIN consumption_units AS plan_unit
              ON plan_unit.formulation_id = planned.formulation_id
             AND plan_unit.unit_id = planned.consumption_unit_id
            WHERE us.user_id = %s
        """
        return query
