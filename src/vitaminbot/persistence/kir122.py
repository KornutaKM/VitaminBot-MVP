from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg import IsolationLevel, sql
from psycopg.rows import dict_row


class KIR122StoreError(RuntimeError):
    """Base error for KIR-122 persistence and snapshot operations."""


class StaleCompositionAction(KIR122StoreError):
    """Raised when a composition action targets stale product/serving state."""


class InvalidCompositionState(KIR122StoreError):
    """Raised when composition input does not match the durable session state."""


class DuplicateCompositionFact(KIR122StoreError):
    """Raised instead of silently replacing an already confirmed manual fact."""


@dataclass(frozen=True, slots=True)
class CompositionSession:
    state: str
    tracked_instance_id: str
    formulation_id: str
    serving_basis_id: str
    consumption_unit_id: str
    expected_supplement_revision: int
    substance_key: str
    analyte_id: str
    display_name: str
    pending_value: Decimal | None
    pending_unit: str | None
    revision: int


@dataclass(frozen=True, slots=True)
class ManualAmountRecord:
    amount_id: str
    tracked_instance_id: str
    formulation_id: str
    substance_key: str
    analyte_id: str
    value: Decimal
    unit: str
    serving_basis_id: str


@dataclass(frozen=True, slots=True)
class SnapshotAmount:
    amount_id: str
    subject_kind: str
    subject_id: str
    source_id: str
    source_version: str
    source_superseded_by: str | None
    resolution_status: str
    evidence_status: str
    value: Decimal | None
    unit: str | None
    amount_basis: str | None
    quantity_basis: str | None
    quantity_basis_id: str | None
    equivalence_basis: str | None
    raw_text: str | None


@dataclass(frozen=True, slots=True)
class SnapshotEvent:
    event_id: str
    consumption_unit_id: str
    consumption_units: Decimal
    schedule_label: str | None
    schedule_kind: str
    local_time: str | None


@dataclass(frozen=True, slots=True)
class SnapshotSupplement:
    instance_id: str
    name: str
    supplement_revision: int
    product_id: str
    formulation_id: str
    formulation_version: str
    unit_id: str
    unit_label: str
    serving_basis_id: str
    serving_basis_type: str
    serving_label_text: str
    serving_quantity: Decimal | None
    serving_unit: str | None
    serving_source_id: str
    plan_id: str | None
    plan_version: str | None
    plan_head_revision: int | None
    events: tuple[SnapshotEvent, ...]
    amounts: tuple[SnapshotAmount, ...]


@dataclass(frozen=True, slots=True)
class VerticalSnapshot:
    user_id: UUID
    profile_version: int
    timezone: str | None
    locale: str | None
    context_revision: str
    supplements: tuple[SnapshotSupplement, ...]


class KIR122Store:
    """PostgreSQL boundary for composition capture and immutable vertical snapshots."""

    def __init__(self, database_url: str, *, schema: str = "public") -> None:
        self._database_url = database_url
        self._schema = schema

    def _connect(self, *, repeatable_read: bool = False) -> psycopg.Connection[dict[str, Any]]:
        conn: psycopg.Connection[dict[str, Any]] = psycopg.connect(
            self._database_url,
            row_factory=dict_row,
        )
        if repeatable_read:
            conn.isolation_level = IsolationLevel.REPEATABLE_READ
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
    def _session_from_row(row: dict[str, Any] | None) -> CompositionSession | None:
        if row is None:
            return None
        return CompositionSession(
            state=str(row["state"]),
            tracked_instance_id=str(row["tracked_instance_id"]),
            formulation_id=str(row["formulation_id"]),
            serving_basis_id=str(row["serving_basis_id"]),
            consumption_unit_id=str(row["consumption_unit_id"]),
            expected_supplement_revision=int(row["expected_supplement_revision"]),
            substance_key=str(row["substance_key"]),
            analyte_id=str(row["analyte_id"]),
            display_name=str(row["display_name"]),
            pending_value=row["pending_value"],
            pending_unit=row["pending_unit"],
            revision=int(row["revision"]),
        )

    def session(self, user_id: UUID) -> CompositionSession | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    state,
                    tracked_instance_id,
                    formulation_id,
                    serving_basis_id,
                    consumption_unit_id,
                    expected_supplement_revision,
                    substance_key,
                    analyte_id,
                    display_name,
                    pending_value,
                    pending_unit,
                    revision
                FROM kir122_composition_sessions
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
        return self._session_from_row(row)

    def begin_amount(
        self,
        user_id: UUID,
        action_key: str,
        *,
        tracked_instance_id: str,
        expected_supplement_revision: int,
        substance_key: str,
        analyte_id: str,
        display_name: str,
    ) -> CompositionSession:
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "kir122_begin_amount")
            if not claimed:
                existing = self._session_in_connection(conn, user_id)
                if existing is None:
                    raise InvalidCompositionState("composition session is no longer active")
                return existing

            current = conn.execute(
                """
                SELECT
                    us.revision,
                    us.formulation_id,
                    us.current_serving_basis_id,
                    us.current_consumption_unit_id
                FROM user_supplements AS us
                WHERE us.user_id = %s
                  AND us.instance_id = %s
                FOR UPDATE
                """,
                (user_id, tracked_instance_id),
            ).fetchone()
            if current is None:
                raise StaleCompositionAction("tracked supplement no longer exists")
            if int(current["revision"]) != expected_supplement_revision:
                raise StaleCompositionAction("tracked supplement changed before composition entry")
            basis_id = current["current_serving_basis_id"]
            unit_id = current["current_consumption_unit_id"]
            if basis_id is None or unit_id is None:
                raise InvalidCompositionState("current serving identity is unresolved")

            duplicate = conn.execute(
                """
                SELECT amount_id
                FROM kir122_manual_amounts
                WHERE tracked_instance_id = %s
                  AND substance_key = %s
                """,
                (tracked_instance_id, substance_key),
            ).fetchone()
            if duplicate is not None:
                raise DuplicateCompositionFact("manual composition fact already exists")

            row = conn.execute(
                """
                INSERT INTO kir122_composition_sessions (
                    user_id,
                    state,
                    tracked_instance_id,
                    formulation_id,
                    serving_basis_id,
                    consumption_unit_id,
                    expected_supplement_revision,
                    substance_key,
                    analyte_id,
                    display_name
                )
                VALUES (%s, 'amount_input', %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET state = 'amount_input',
                    tracked_instance_id = EXCLUDED.tracked_instance_id,
                    formulation_id = EXCLUDED.formulation_id,
                    serving_basis_id = EXCLUDED.serving_basis_id,
                    consumption_unit_id = EXCLUDED.consumption_unit_id,
                    expected_supplement_revision = EXCLUDED.expected_supplement_revision,
                    substance_key = EXCLUDED.substance_key,
                    analyte_id = EXCLUDED.analyte_id,
                    display_name = EXCLUDED.display_name,
                    pending_value = NULL,
                    pending_unit = NULL,
                    revision = kir122_composition_sessions.revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING
                    state,
                    tracked_instance_id,
                    formulation_id,
                    serving_basis_id,
                    consumption_unit_id,
                    expected_supplement_revision,
                    substance_key,
                    analyte_id,
                    display_name,
                    pending_value,
                    pending_unit,
                    revision
                """,
                (
                    user_id,
                    tracked_instance_id,
                    current["formulation_id"],
                    basis_id,
                    unit_id,
                    expected_supplement_revision,
                    substance_key,
                    analyte_id,
                    display_name,
                ),
            ).fetchone()
            assert row is not None
            session = self._session_from_row(row)
            assert session is not None
            self._complete_action(conn, user_id, action_key, tracked_instance_id)
            return session

    def set_amount(
        self,
        user_id: UUID,
        action_key: str,
        *,
        value: Decimal,
        unit: str,
    ) -> CompositionSession:
        if not value.is_finite() or value < 0:
            raise ValueError("composition amount must be finite and non-negative")
        if unit not in {"g", "mg", "ug"}:
            raise ValueError("unsupported composition mass unit")

        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "kir122_set_amount")
            session = self._locked_session(conn, user_id, "amount_input")
            if not claimed:
                current = self._session_in_connection(conn, user_id)
                return current or session

            row = conn.execute(
                """
                UPDATE kir122_composition_sessions
                SET state = 'amount_review',
                    pending_value = %s,
                    pending_unit = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                  AND revision = %s
                RETURNING
                    state,
                    tracked_instance_id,
                    formulation_id,
                    serving_basis_id,
                    consumption_unit_id,
                    expected_supplement_revision,
                    substance_key,
                    analyte_id,
                    display_name,
                    pending_value,
                    pending_unit,
                    revision
                """,
                (value, unit, user_id, session.revision),
            ).fetchone()
            if row is None:
                raise StaleCompositionAction("composition session changed before amount was saved")
            updated = self._session_from_row(row)
            assert updated is not None
            self._complete_action(conn, user_id, action_key, updated.tracked_instance_id)
            return updated

    def confirm_amount(
        self,
        user_id: UUID,
        action_key: str,
        *,
        expected_session_revision: int,
    ) -> ManualAmountRecord:
        with self._connect() as conn:
            claimed, result_ref = self._claim_action(
                conn,
                user_id,
                action_key,
                "kir122_confirm_amount",
            )
            if not claimed and result_ref is not None:
                return self._manual_amount_by_id(conn, user_id, result_ref)

            session = self._locked_session(conn, user_id, "amount_review")
            if session.revision != expected_session_revision:
                raise StaleCompositionAction("composition confirmation is stale")
            if session.pending_value is None or session.pending_unit is None:
                raise InvalidCompositionState("composition amount is incomplete")

            current = conn.execute(
                """
                SELECT
                    us.revision,
                    us.formulation_id,
                    us.current_serving_basis_id,
                    us.current_consumption_unit_id,
                    serving.source_id,
                    serving.basis_type
                FROM user_supplements AS us
                JOIN product_servings AS serving
                  ON serving.formulation_id = us.formulation_id
                 AND serving.basis_id = us.current_serving_basis_id
                 AND serving.consumption_unit_id = us.current_consumption_unit_id
                WHERE us.user_id = %s
                  AND us.instance_id = %s
                FOR UPDATE OF us
                """,
                (user_id, session.tracked_instance_id),
            ).fetchone()
            if current is None:
                raise StaleCompositionAction("tracked supplement no longer exists")
            if int(current["revision"]) != session.expected_supplement_revision:
                raise StaleCompositionAction("supplement changed before composition confirmation")
            if (
                str(current["formulation_id"]) != session.formulation_id
                or str(current["current_serving_basis_id"]) != session.serving_basis_id
                or str(current["current_consumption_unit_id"]) != session.consumption_unit_id
            ):
                raise StaleCompositionAction("serving identity changed before confirmation")
            if current["basis_type"] != "per_label_portion":
                raise InvalidCompositionState(
                    "manual composition requires the confirmed label-serving basis"
                )

            duplicate = conn.execute(
                """
                SELECT amount_id
                FROM kir122_manual_amounts
                WHERE tracked_instance_id = %s
                  AND substance_key = %s
                FOR UPDATE
                """,
                (session.tracked_instance_id, session.substance_key),
            ).fetchone()
            if duplicate is not None:
                raise DuplicateCompositionFact("manual composition fact already exists")

            conn.execute(
                """
                INSERT INTO tracked_analytes (analyte_id, display_name)
                VALUES (%s, %s)
                ON CONFLICT (analyte_id) DO NOTHING
                """,
                (session.analyte_id, session.display_name),
            )

            amount_id = f"amount:kir122:{uuid4().hex}"
            raw_text = f"{session.pending_value} {session.pending_unit}"
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
                    quantity_basis_id,
                    raw_text
                )
                VALUES (
                    %s,
                    %s,
                    'analyte',
                    %s,
                    %s,
                    'resolved',
                    'declared',
                    %s,
                    %s,
                    'analyte',
                    'per_label_portion',
                    %s,
                    %s
                )
                """,
                (
                    amount_id,
                    session.formulation_id,
                    session.analyte_id,
                    current["source_id"],
                    session.pending_value,
                    session.pending_unit,
                    session.serving_basis_id,
                    raw_text,
                ),
            )
            conn.execute(
                """
                INSERT INTO kir122_manual_amounts (
                    user_id,
                    tracked_instance_id,
                    formulation_id,
                    amount_id,
                    substance_key,
                    analyte_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    session.tracked_instance_id,
                    session.formulation_id,
                    amount_id,
                    session.substance_key,
                    session.analyte_id,
                ),
            )
            conn.execute(
                "DELETE FROM kir122_composition_sessions WHERE user_id = %s",
                (user_id,),
            )
            self._complete_action(conn, user_id, action_key, amount_id)
            return ManualAmountRecord(
                amount_id=amount_id,
                tracked_instance_id=session.tracked_instance_id,
                formulation_id=session.formulation_id,
                substance_key=session.substance_key,
                analyte_id=session.analyte_id,
                value=session.pending_value,
                unit=session.pending_unit,
                serving_basis_id=session.serving_basis_id,
            )

    def cancel(self, user_id: UUID) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM kir122_composition_sessions WHERE user_id = %s",
                (user_id,),
            )

    def manual_substance_keys(self, user_id: UUID, tracked_instance_id: str) -> tuple[str, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT substance_key
                FROM kir122_manual_amounts
                WHERE user_id = %s
                  AND tracked_instance_id = %s
                ORDER BY substance_key
                """,
                (user_id, tracked_instance_id),
            ).fetchall()
        return tuple(str(row["substance_key"]) for row in rows)

    def snapshot(
        self,
        user_id: UUID,
        *,
        semantic_versions: tuple[str, ...],
    ) -> VerticalSnapshot:
        with self._connect(repeatable_read=True) as conn:
            profile = conn.execute(
                """
                SELECT timezone, locale, profile_version
                FROM user_profiles
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
            profile_version = 0 if profile is None else int(profile["profile_version"])
            timezone = None if profile is None else profile["timezone"]
            locale = None if profile is None else profile["locale"]

            supplement_rows = conn.execute(
                """
                SELECT
                    us.instance_id,
                    us.container_label,
                    us.revision AS supplement_revision,
                    product.product_id,
                    formulation.formulation_id,
                    formulation.version AS formulation_version,
                    unit.unit_id,
                    unit.label_name AS unit_label,
                    serving.basis_id AS serving_basis_id,
                    serving.basis_type AS serving_basis_type,
                    serving.label_text AS serving_label_text,
                    serving.basis_quantity AS serving_quantity,
                    serving.basis_unit AS serving_unit,
                    serving.source_id AS serving_source_id,
                    head.plan_id,
                    head.plan_version,
                    head.revision AS plan_head_revision
                FROM user_supplements AS us
                JOIN product_formulations AS formulation
                  ON formulation.formulation_id = us.formulation_id
                JOIN products AS product
                  ON product.product_id = formulation.product_id
                JOIN consumption_units AS unit
                  ON unit.formulation_id = us.formulation_id
                 AND unit.unit_id = us.current_consumption_unit_id
                JOIN product_servings AS serving
                  ON serving.formulation_id = us.formulation_id
                 AND serving.basis_id = us.current_serving_basis_id
                 AND serving.consumption_unit_id = us.current_consumption_unit_id
                LEFT JOIN intake_plan_heads AS head
                  ON head.tracked_instance_id = us.instance_id
                WHERE us.user_id = %s
                ORDER BY us.created_at, us.instance_id
                """,
                (user_id,),
            ).fetchall()

            supplements: list[SnapshotSupplement] = []
            for row in supplement_rows:
                plan_id = row["plan_id"]
                plan_version = row["plan_version"]
                event_rows: list[dict[str, Any]]
                if plan_id is None or plan_version is None:
                    event_rows = []
                else:
                    event_rows = conn.execute(
                        """
                        SELECT
                            event_id,
                            consumption_unit_id,
                            consumption_units,
                            schedule_label,
                            schedule_kind,
                            local_time
                        FROM planned_intake_events
                        WHERE plan_id = %s
                          AND plan_version = %s
                          AND formulation_id = %s
                        ORDER BY event_id
                        """,
                        (plan_id, plan_version, row["formulation_id"]),
                    ).fetchall()

                amount_rows = conn.execute(
                    """
                    SELECT
                        amount.amount_id,
                        amount.subject_kind,
                        amount.analyte_id,
                        amount.ingredient_id,
                        amount.source_id,
                        source.version AS source_version,
                        source.superseded_by_source_id,
                        amount.resolution_status,
                        amount.evidence_status,
                        amount.value,
                        amount.unit,
                        amount.amount_basis,
                        amount.quantity_basis,
                        amount.quantity_basis_id,
                        amount.equivalence_basis,
                        amount.raw_text
                    FROM product_amounts AS amount
                    JOIN source_records AS source
                      ON source.source_id = amount.source_id
                    WHERE amount.formulation_id = %s
                    ORDER BY amount.amount_id
                    """,
                    (row["formulation_id"],),
                ).fetchall()

                events = tuple(
                    SnapshotEvent(
                        event_id=str(event["event_id"]),
                        consumption_unit_id=str(event["consumption_unit_id"]),
                        consumption_units=event["consumption_units"],
                        schedule_label=event["schedule_label"],
                        schedule_kind=str(event["schedule_kind"]),
                        local_time=(
                            None
                            if event["local_time"] is None
                            else event["local_time"].isoformat(timespec="minutes")
                        ),
                    )
                    for event in event_rows
                )
                amounts = tuple(
                    SnapshotAmount(
                        amount_id=str(amount["amount_id"]),
                        subject_kind=str(amount["subject_kind"]),
                        subject_id=str(
                            amount["analyte_id"]
                            if amount["subject_kind"] == "analyte"
                            else amount["ingredient_id"]
                        ),
                        source_id=str(amount["source_id"]),
                        source_version=str(amount["source_version"]),
                        source_superseded_by=amount["superseded_by_source_id"],
                        resolution_status=str(amount["resolution_status"]),
                        evidence_status=str(amount["evidence_status"]),
                        value=amount["value"],
                        unit=amount["unit"],
                        amount_basis=amount["amount_basis"],
                        quantity_basis=amount["quantity_basis"],
                        quantity_basis_id=amount["quantity_basis_id"],
                        equivalence_basis=amount["equivalence_basis"],
                        raw_text=amount["raw_text"],
                    )
                    for amount in amount_rows
                )
                supplements.append(
                    SnapshotSupplement(
                        instance_id=str(row["instance_id"]),
                        name=str(row["container_label"]),
                        supplement_revision=int(row["supplement_revision"]),
                        product_id=str(row["product_id"]),
                        formulation_id=str(row["formulation_id"]),
                        formulation_version=str(row["formulation_version"]),
                        unit_id=str(row["unit_id"]),
                        unit_label=str(row["unit_label"]),
                        serving_basis_id=str(row["serving_basis_id"]),
                        serving_basis_type=str(row["serving_basis_type"]),
                        serving_label_text=str(row["serving_label_text"]),
                        serving_quantity=row["serving_quantity"],
                        serving_unit=row["serving_unit"],
                        serving_source_id=str(row["serving_source_id"]),
                        plan_id=None if plan_id is None else str(plan_id),
                        plan_version=None if plan_version is None else str(plan_version),
                        plan_head_revision=(
                            None
                            if row["plan_head_revision"] is None
                            else int(row["plan_head_revision"])
                        ),
                        events=events,
                        amounts=amounts,
                    )
                )

            revision_payload = {
                "profile": {
                    "version": profile_version,
                    "timezone": timezone,
                    "locale": locale,
                },
                "semantic_versions": list(semantic_versions),
                "supplements": [self._revision_payload(item) for item in supplements],
            }
            digest = hashlib.sha256(
                json.dumps(
                    revision_payload,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            return VerticalSnapshot(
                user_id=user_id,
                profile_version=profile_version,
                timezone=timezone,
                locale=locale,
                context_revision=f"kir122:{digest}",
                supplements=tuple(supplements),
            )

    @staticmethod
    def _revision_payload(supplement: SnapshotSupplement) -> dict[str, object]:
        return {
            "instance_id": supplement.instance_id,
            "supplement_revision": supplement.supplement_revision,
            "product_id": supplement.product_id,
            "formulation_id": supplement.formulation_id,
            "formulation_version": supplement.formulation_version,
            "unit_id": supplement.unit_id,
            "serving_basis_id": supplement.serving_basis_id,
            "serving_basis_type": supplement.serving_basis_type,
            "serving_quantity": (
                None if supplement.serving_quantity is None else str(supplement.serving_quantity)
            ),
            "serving_unit": supplement.serving_unit,
            "serving_source_id": supplement.serving_source_id,
            "plan_id": supplement.plan_id,
            "plan_version": supplement.plan_version,
            "plan_head_revision": supplement.plan_head_revision,
            "events": [
                {
                    "event_id": event.event_id,
                    "consumption_unit_id": event.consumption_unit_id,
                    "consumption_units": str(event.consumption_units),
                    "schedule_label": event.schedule_label,
                    "schedule_kind": event.schedule_kind,
                    "local_time": event.local_time,
                }
                for event in supplement.events
            ],
            "amounts": [
                {
                    "amount_id": amount.amount_id,
                    "subject_kind": amount.subject_kind,
                    "subject_id": amount.subject_id,
                    "source_id": amount.source_id,
                    "source_version": amount.source_version,
                    "source_superseded_by": amount.source_superseded_by,
                    "resolution_status": amount.resolution_status,
                    "evidence_status": amount.evidence_status,
                    "value": None if amount.value is None else str(amount.value),
                    "unit": amount.unit,
                    "amount_basis": amount.amount_basis,
                    "quantity_basis": amount.quantity_basis,
                    "quantity_basis_id": amount.quantity_basis_id,
                    "equivalence_basis": amount.equivalence_basis,
                    "raw_text": amount.raw_text,
                }
                for amount in supplement.amounts
            ],
        }

    def _session_in_connection(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
    ) -> CompositionSession | None:
        row = conn.execute(
            """
            SELECT
                state,
                tracked_instance_id,
                formulation_id,
                serving_basis_id,
                consumption_unit_id,
                expected_supplement_revision,
                substance_key,
                analyte_id,
                display_name,
                pending_value,
                pending_unit,
                revision
            FROM kir122_composition_sessions
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
        return self._session_from_row(row)

    def _locked_session(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        expected_state: str,
    ) -> CompositionSession:
        row = conn.execute(
            """
            SELECT
                state,
                tracked_instance_id,
                formulation_id,
                serving_basis_id,
                consumption_unit_id,
                expected_supplement_revision,
                substance_key,
                analyte_id,
                display_name,
                pending_value,
                pending_unit,
                revision
            FROM kir122_composition_sessions
            WHERE user_id = %s
            FOR UPDATE
            """,
            (user_id,),
        ).fetchone()
        session = self._session_from_row(row)
        if session is None or session.state != expected_state:
            raise InvalidCompositionState("composition session state no longer matches this action")
        return session

    @staticmethod
    def _manual_amount_by_id(
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        amount_id: str,
    ) -> ManualAmountRecord:
        row = conn.execute(
            """
            SELECT
                marker.amount_id,
                marker.tracked_instance_id,
                marker.formulation_id,
                marker.substance_key,
                marker.analyte_id,
                amount.value,
                amount.unit,
                amount.quantity_basis_id
            FROM kir122_manual_amounts AS marker
            JOIN product_amounts AS amount
              ON amount.formulation_id = marker.formulation_id
             AND amount.amount_id = marker.amount_id
            WHERE marker.user_id = %s
              AND marker.amount_id = %s
            """,
            (user_id, amount_id),
        ).fetchone()
        if row is None:
            raise InvalidCompositionState("confirmed composition fact no longer exists")
        return ManualAmountRecord(
            amount_id=str(row["amount_id"]),
            tracked_instance_id=str(row["tracked_instance_id"]),
            formulation_id=str(row["formulation_id"]),
            substance_key=str(row["substance_key"]),
            analyte_id=str(row["analyte_id"]),
            value=row["value"],
            unit=str(row["unit"]),
            serving_basis_id=str(row["quantity_basis_id"]),
        )
