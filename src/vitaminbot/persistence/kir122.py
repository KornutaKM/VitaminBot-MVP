from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from vitaminbot.domain import (
    AmountBasis,
    AmountRecord,
    EvidenceStatus,
    IntakePlan,
    PlannedIntakeEvent,
    QuantityBasis,
    ResolutionStatus,
    ServingDefinition,
    SubjectKind,
    Unit,
)


class KIR122StoreError(RuntimeError):
    """Base error for the KIR-122 persistence/integration boundary."""


class KIR122InvalidTransition(KIR122StoreError):
    """Raised when a nutrient-entry state transition is invalid."""


class KIR122StaleAction(KIR122StoreError):
    """Raised when a revision-bound action no longer matches current state."""


class KIR122RecordNotFound(KIR122StoreError):
    """Raised when the referenced user-owned record no longer exists."""


@dataclass(frozen=True, slots=True)
class NutrientEntrySession:
    state: str
    tracked_instance_id: str
    substance_key: str | None
    subject_kind: SubjectKind | None
    subject_id: str | None
    amount_basis: AmountBasis | None
    equivalence_basis: str | None
    display_name: str | None
    pending_value: Decimal | None
    pending_unit: Unit | None
    expected_supplement_revision: int
    revision: int


@dataclass(frozen=True, slots=True)
class SnapshotSupplement:
    instance_id: str
    name: str
    supplement_revision: int
    product_id: str
    formulation_id: str
    serving: ServingDefinition
    plan: IntakePlan | None
    plan_revision: int | None
    amounts: tuple[AmountRecord, ...]


@dataclass(frozen=True, slots=True)
class VerticalSnapshot:
    context_revision: str
    locale: str | None
    supplements: tuple[SnapshotSupplement, ...]


class KIR122Store:
    """Durable glue over accepted KIR-112/116/120 persistence.

    Scientific results are deliberately not persisted here. Callers obtain one
    repeatable-read snapshot and derive normalization/aggregation/rules from it.
    """

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
            value = row["user_id"]
            if not isinstance(value, UUID):
                raise KIR122StoreError("database returned invalid user_id")
            return value

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
            SELECT action_type, result_ref
            FROM bot_action_receipts
            WHERE user_id = %s AND action_key = %s
            """,
            (user_id, action_key),
        ).fetchone()
        if existing is None:
            return False, None
        if existing["action_type"] != action_type:
            raise KIR122InvalidTransition("action key was already used for another action")
        return False, existing["result_ref"]

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
    def _session_from_row(row: dict[str, Any] | None) -> NutrientEntrySession | None:
        if row is None:
            return None
        return NutrientEntrySession(
            state=str(row["state"]),
            tracked_instance_id=str(row["tracked_instance_id"]),
            substance_key=None if row["substance_key"] is None else str(row["substance_key"]),
            subject_kind=(
                None if row["subject_kind"] is None else SubjectKind(str(row["subject_kind"]))
            ),
            subject_id=None if row["subject_id"] is None else str(row["subject_id"]),
            amount_basis=(
                None if row["amount_basis"] is None else AmountBasis(str(row["amount_basis"]))
            ),
            equivalence_basis=(
                None if row["equivalence_basis"] is None else str(row["equivalence_basis"])
            ),
            display_name=None if row["display_name"] is None else str(row["display_name"]),
            pending_value=row["pending_value"],
            pending_unit=None if row["pending_unit"] is None else Unit(str(row["pending_unit"])),
            expected_supplement_revision=int(row["expected_supplement_revision"]),
            revision=int(row["revision"]),
        )

    def get_session(self, user_id: UUID) -> NutrientEntrySession | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT state, tracked_instance_id, substance_key, subject_kind, subject_id,
                       amount_basis, equivalence_basis, display_name, pending_value,
                       pending_unit, expected_supplement_revision, revision
                FROM kir122_nutrient_entry_sessions
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
        return self._session_from_row(row)

    def has_pending_text(self, user_id: UUID) -> bool:
        session = self.get_session(user_id)
        return session is not None and session.state in {"nutrient_name", "nutrient_value"}

    def cancel(self, user_id: UUID) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM kir122_nutrient_entry_sessions WHERE user_id = %s",
                (user_id,),
            )

    def list_supplement_refs(self, user_id: UUID) -> tuple[tuple[str, str, int], ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT instance_id, container_label, revision
                FROM user_supplements
                WHERE user_id = %s
                ORDER BY lower(container_label), instance_id
                """,
                (user_id,),
            ).fetchall()
        return tuple(
            (str(row["instance_id"]), str(row["container_label"]), int(row["revision"]))
            for row in rows
        )

    def begin_nutrient_entry(
        self,
        user_id: UUID,
        action_key: str,
        instance_id: str,
        expected_supplement_revision: int,
    ) -> NutrientEntrySession:
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "kir122_begin_nutrient")
            current = conn.execute(
                """
                SELECT revision
                FROM user_supplements
                WHERE user_id = %s AND instance_id = %s
                FOR UPDATE
                """,
                (user_id, instance_id),
            ).fetchone()
            if current is None:
                raise KIR122RecordNotFound("supplement not found")
            if int(current["revision"]) != expected_supplement_revision:
                raise KIR122StaleAction("supplement changed before nutrient entry")
            if not claimed:
                session = self.get_session(user_id)
                if session is None:
                    raise KIR122InvalidTransition("nutrient-entry session is no longer active")
                return session

            row = conn.execute(
                """
                INSERT INTO kir122_nutrient_entry_sessions (
                    user_id, tracked_instance_id, state, expected_supplement_revision
                )
                VALUES (%s, %s, 'nutrient_name', %s)
                ON CONFLICT (user_id) DO UPDATE
                SET tracked_instance_id = EXCLUDED.tracked_instance_id,
                    state = 'nutrient_name',
                    substance_key = NULL,
                    subject_kind = NULL,
                    subject_id = NULL,
                    amount_basis = NULL,
                    equivalence_basis = NULL,
                    display_name = NULL,
                    pending_value = NULL,
                    pending_unit = NULL,
                    expected_supplement_revision = EXCLUDED.expected_supplement_revision,
                    revision = kir122_nutrient_entry_sessions.revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING state, tracked_instance_id, substance_key, subject_kind, subject_id,
                          amount_basis, equivalence_basis, display_name, pending_value,
                          pending_unit, expected_supplement_revision, revision
                """,
                (user_id, instance_id, expected_supplement_revision),
            ).fetchone()
            assert row is not None
            self._complete_action(conn, user_id, action_key, instance_id)
            session = self._session_from_row(row)
            assert session is not None
            return session

    def set_subject(
        self,
        user_id: UUID,
        action_key: str,
        *,
        substance_key: str,
        subject_kind: SubjectKind,
        subject_id: str,
        amount_basis: AmountBasis,
        equivalence_basis: str | None,
        display_name: str,
    ) -> NutrientEntrySession:
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "kir122_subject")
            row = conn.execute(
                """
                SELECT *
                FROM kir122_nutrient_entry_sessions
                WHERE user_id = %s
                FOR UPDATE
                """,
                (user_id,),
            ).fetchone()
            session = self._session_from_row(row)
            if session is None:
                raise KIR122InvalidTransition("no nutrient-entry session")
            if not claimed:
                return session
            if session.state != "nutrient_name":
                raise KIR122InvalidTransition("nutrient name is not expected")
            row = conn.execute(
                """
                UPDATE kir122_nutrient_entry_sessions
                SET state = 'nutrient_value',
                    substance_key = %s,
                    subject_kind = %s,
                    subject_id = %s,
                    amount_basis = %s,
                    equivalence_basis = %s,
                    display_name = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                RETURNING state, tracked_instance_id, substance_key, subject_kind, subject_id,
                          amount_basis, equivalence_basis, display_name, pending_value,
                          pending_unit, expected_supplement_revision, revision
                """,
                (
                    substance_key,
                    subject_kind.value,
                    subject_id,
                    amount_basis.value,
                    equivalence_basis,
                    display_name,
                    user_id,
                ),
            ).fetchone()
            assert row is not None
            self._complete_action(conn, user_id, action_key, subject_id)
            updated = self._session_from_row(row)
            assert updated is not None
            return updated

    def set_value(
        self,
        user_id: UUID,
        action_key: str,
        value: Decimal,
    ) -> NutrientEntrySession:
        if not value.is_finite() or value < 0:
            raise ValueError("amount must be finite and non-negative")
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "kir122_value")
            row = conn.execute(
                """
                SELECT *
                FROM kir122_nutrient_entry_sessions
                WHERE user_id = %s
                FOR UPDATE
                """,
                (user_id,),
            ).fetchone()
            session = self._session_from_row(row)
            if session is None:
                raise KIR122InvalidTransition("no nutrient-entry session")
            if not claimed:
                return session
            if session.state != "nutrient_value":
                raise KIR122InvalidTransition("nutrient amount is not expected")
            row = conn.execute(
                """
                UPDATE kir122_nutrient_entry_sessions
                SET state = 'nutrient_unit',
                    pending_value = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                RETURNING state, tracked_instance_id, substance_key, subject_kind, subject_id,
                          amount_basis, equivalence_basis, display_name, pending_value,
                          pending_unit, expected_supplement_revision, revision
                """,
                (value, user_id),
            ).fetchone()
            assert row is not None
            self._complete_action(conn, user_id, action_key, None)
            updated = self._session_from_row(row)
            assert updated is not None
            return updated

    def set_unit(
        self,
        user_id: UUID,
        action_key: str,
        unit: Unit,
        expected_revision: int,
    ) -> NutrientEntrySession:
        with self._connect() as conn:
            claimed, _ = self._claim_action(conn, user_id, action_key, "kir122_unit")
            row = conn.execute(
                """
                SELECT *
                FROM kir122_nutrient_entry_sessions
                WHERE user_id = %s
                FOR UPDATE
                """,
                (user_id,),
            ).fetchone()
            session = self._session_from_row(row)
            if session is None:
                raise KIR122InvalidTransition("no nutrient-entry session")
            if not claimed:
                return session
            if session.state != "nutrient_unit" or session.revision != expected_revision:
                raise KIR122StaleAction("nutrient unit action is stale")
            row = conn.execute(
                """
                UPDATE kir122_nutrient_entry_sessions
                SET state = 'nutrient_review',
                    pending_unit = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                RETURNING state, tracked_instance_id, substance_key, subject_kind, subject_id,
                          amount_basis, equivalence_basis, display_name, pending_value,
                          pending_unit, expected_supplement_revision, revision
                """,
                (unit.value, user_id),
            ).fetchone()
            assert row is not None
            self._complete_action(conn, user_id, action_key, unit.value)
            updated = self._session_from_row(row)
            assert updated is not None
            return updated

    def confirm_amount(
        self,
        user_id: UUID,
        action_key: str,
        expected_revision: int,
    ) -> str:
        with self._connect() as conn:
            claimed, result_ref = self._claim_action(conn, user_id, action_key, "kir122_confirm")
            if not claimed and result_ref is not None:
                return result_ref

            row = conn.execute(
                """
                SELECT *
                FROM kir122_nutrient_entry_sessions
                WHERE user_id = %s
                FOR UPDATE
                """,
                (user_id,),
            ).fetchone()
            session = self._session_from_row(row)
            if session is None:
                raise KIR122InvalidTransition("no nutrient-entry session")
            if session.state != "nutrient_review" or session.revision != expected_revision:
                raise KIR122StaleAction("nutrient confirmation is stale")
            if (
                session.substance_key is None
                or session.subject_kind is None
                or session.subject_id is None
                or session.amount_basis is None
                or session.display_name is None
                or session.pending_value is None
                or session.pending_unit is None
            ):
                raise KIR122InvalidTransition("nutrient review is incomplete")

            supplement = conn.execute(
                """
                SELECT us.revision, us.formulation_id, us.current_serving_basis_id,
                       fs.source_id
                FROM user_supplements AS us
                JOIN formulation_sources AS fs
                  ON fs.formulation_id = us.formulation_id
                WHERE us.user_id = %s AND us.instance_id = %s
                FOR UPDATE OF us
                """,
                (user_id, session.tracked_instance_id),
            ).fetchall()
            if not supplement:
                raise KIR122RecordNotFound("supplement not found")
            revisions = {int(item["revision"]) for item in supplement}
            if revisions != {session.expected_supplement_revision}:
                raise KIR122StaleAction("supplement changed before nutrient confirmation")
            source_ids = tuple(sorted({str(item["source_id"]) for item in supplement}))
            if len(source_ids) != 1:
                raise KIR122InvalidTransition(
                    "manual nutrient confirmation requires one unambiguous formulation source"
                )
            basis_id = supplement[0]["current_serving_basis_id"]
            if basis_id is None:
                raise KIR122InvalidTransition("supplement serving basis is unresolved")

            conn.execute(
                """
                INSERT INTO tracked_analytes (analyte_id, display_name)
                VALUES (%s, %s)
                ON CONFLICT (analyte_id) DO NOTHING
                """,
                (session.subject_id, session.display_name),
            )

            amount_id = f"amount:kir122:{uuid4().hex}"
            raw_text = (
                f"{session.display_name}: {session.pending_value} {session.pending_unit.value} "
                "per label serving"
            )
            conn.execute(
                """
                INSERT INTO product_amounts (
                    amount_id, formulation_id, subject_kind, subject_id, source_id,
                    resolution_status, evidence_status, value, unit, amount_basis,
                    quantity_basis, quantity_basis_id, equivalence_basis, raw_text
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    'resolved', 'declared', %s, %s, %s,
                    'per_label_portion', %s, %s, %s
                )
                """,
                (
                    amount_id,
                    str(supplement[0]["formulation_id"]),
                    session.subject_kind.value,
                    session.subject_id,
                    source_ids[0],
                    session.pending_value,
                    session.pending_unit.value,
                    session.amount_basis.value,
                    str(basis_id),
                    session.equivalence_basis,
                    raw_text,
                ),
            )
            conn.execute(
                "DELETE FROM kir122_nutrient_entry_sessions WHERE user_id = %s",
                (user_id,),
            )
            self._complete_action(conn, user_id, action_key, amount_id)
            return amount_id

    def snapshot(self, user_id: UUID) -> VerticalSnapshot:
        conn: psycopg.Connection[dict[str, Any]] = psycopg.connect(
            self._database_url,
            autocommit=True,
            row_factory=dict_row,
        )
        try:
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self._schema)))
            with conn.transaction():
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                profile = conn.execute(
                    """
                    SELECT timezone, locale, profile_version
                    FROM user_profiles
                    WHERE user_id = %s
                    """,
                    (user_id,),
                ).fetchone()
                bases = conn.execute(
                    """
                    SELECT
                        us.instance_id, us.container_label, us.revision AS supplement_revision,
                        us.formulation_id, pf.product_id,
                        us.current_serving_basis_id,
                        ps.basis_type, ps.label_text, ps.source_id AS serving_source_id,
                        ps.basis_quantity, ps.basis_unit, ps.consumption_unit_id,
                        h.plan_id, h.plan_version, h.revision AS plan_revision
                    FROM user_supplements AS us
                    JOIN product_formulations AS pf
                      ON pf.formulation_id = us.formulation_id
                    JOIN product_servings AS ps
                      ON ps.basis_id = us.current_serving_basis_id
                    LEFT JOIN intake_plan_heads AS h
                      ON h.tracked_instance_id = us.instance_id
                    WHERE us.user_id = %s
                    ORDER BY us.instance_id
                    """,
                    (user_id,),
                ).fetchall()
                events = conn.execute(
                    """
                    SELECT
                        h.tracked_instance_id, e.event_id, e.consumption_unit_id,
                        e.consumption_units, e.schedule_label
                    FROM intake_plan_heads AS h
                    JOIN user_supplements AS us
                      ON us.instance_id = h.tracked_instance_id
                    JOIN planned_intake_events AS e
                      ON e.plan_id = h.plan_id AND e.plan_version = h.plan_version
                    WHERE us.user_id = %s
                    ORDER BY h.tracked_instance_id, e.event_id
                    """,
                    (user_id,),
                ).fetchall()
                amounts = conn.execute(
                    """
                    SELECT
                        us.instance_id, pa.amount_id, pa.subject_kind, pa.subject_id,
                        pa.source_id, pa.resolution_status, pa.evidence_status, pa.value,
                        pa.unit, pa.amount_basis, pa.quantity_basis, pa.quantity_basis_id,
                        pa.equivalence_basis, pa.raw_text,
                        sr.version AS source_version, sr.retrieved_on AS source_retrieved_on
                    FROM user_supplements AS us
                    JOIN product_amounts AS pa
                      ON pa.formulation_id = us.formulation_id
                    JOIN source_records AS sr
                      ON sr.source_id = pa.source_id
                    WHERE us.user_id = %s
                    ORDER BY us.instance_id, pa.amount_id
                    """,
                    (user_id,),
                ).fetchall()

                revision_payload = {
                    "profile": self._stable_row(profile),
                    "bases": [self._stable_row(row) for row in bases],
                    "events": [self._stable_row(row) for row in events],
                    "amounts": [self._stable_row(row) for row in amounts],
                }
                digest = hashlib.sha256(
                    json.dumps(
                        revision_payload,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
                context_revision = f"kir122:{digest}"

                events_by_instance: dict[str, list[PlannedIntakeEvent]] = {}
                for row in events:
                    instance_id = str(row["tracked_instance_id"])
                    events_by_instance.setdefault(instance_id, []).append(
                        PlannedIntakeEvent(
                            event_id=str(row["event_id"]),
                            consumption_unit_id=str(row["consumption_unit_id"]),
                            consumption_units=row["consumption_units"],
                            schedule_label=(
                                None
                                if row["schedule_label"] is None
                                else str(row["schedule_label"])
                            ),
                        )
                    )

                amounts_by_instance: dict[str, list[AmountRecord]] = {}
                for row in amounts:
                    instance_id = str(row["instance_id"])
                    amounts_by_instance.setdefault(instance_id, []).append(
                        AmountRecord(
                            amount_id=str(row["amount_id"]),
                            subject_kind=SubjectKind(str(row["subject_kind"])),
                            subject_id=str(row["subject_id"]),
                            source_id=str(row["source_id"]),
                            resolution_status=ResolutionStatus(str(row["resolution_status"])),
                            evidence_status=EvidenceStatus(str(row["evidence_status"])),
                            value=row["value"],
                            unit=None if row["unit"] is None else Unit(str(row["unit"])),
                            amount_basis=(
                                None
                                if row["amount_basis"] is None
                                else AmountBasis(str(row["amount_basis"]))
                            ),
                            quantity_basis=(
                                None
                                if row["quantity_basis"] is None
                                else QuantityBasis(str(row["quantity_basis"]))
                            ),
                            quantity_basis_id=(
                                None
                                if row["quantity_basis_id"] is None
                                else str(row["quantity_basis_id"])
                            ),
                            equivalence_basis=(
                                None
                                if row["equivalence_basis"] is None
                                else str(row["equivalence_basis"])
                            ),
                            raw_text=(
                                None if row["raw_text"] is None else str(row["raw_text"])
                            ),
                        )
                    )

                supplements: list[SnapshotSupplement] = []
                for row in bases:
                    instance_id = str(row["instance_id"])
                    plan_id = row["plan_id"]
                    plan_version = row["plan_version"]
                    plan = None
                    if plan_id is not None and plan_version is not None:
                        plan = IntakePlan(
                            plan_id=str(plan_id),
                            tracked_instance_id=instance_id,
                            version=str(plan_version),
                            events=tuple(events_by_instance.get(instance_id, ())),
                        )
                    supplements.append(
                        SnapshotSupplement(
                            instance_id=instance_id,
                            name=str(row["container_label"]),
                            supplement_revision=int(row["supplement_revision"]),
                            product_id=str(row["product_id"]),
                            formulation_id=str(row["formulation_id"]),
                            serving=ServingDefinition(
                                basis_id=str(row["current_serving_basis_id"]),
                                basis_type=QuantityBasis(str(row["basis_type"])),
                                label_text=str(row["label_text"]),
                                source_id=str(row["serving_source_id"]),
                                basis_quantity=row["basis_quantity"],
                                basis_unit=(
                                    None
                                    if row["basis_unit"] is None
                                    else Unit(str(row["basis_unit"]))
                                ),
                                consumption_unit_id=(
                                    None
                                    if row["consumption_unit_id"] is None
                                    else str(row["consumption_unit_id"])
                                ),
                            ),
                            plan=plan,
                            plan_revision=(
                                None
                                if row["plan_revision"] is None
                                else int(row["plan_revision"])
                            ),
                            amounts=tuple(amounts_by_instance.get(instance_id, ())),
                        )
                    )

                return VerticalSnapshot(
                    context_revision=context_revision,
                    locale=None if profile is None else profile["locale"],
                    supplements=tuple(supplements),
                )
        finally:
            conn.close()

    @staticmethod
    def _stable_row(row: dict[str, Any] | None) -> dict[str, str | None] | None:
        if row is None:
            return None
        return {
            str(key): None if value is None else str(value)
            for key, value in sorted(row.items(), key=lambda item: str(item[0]))
        }
