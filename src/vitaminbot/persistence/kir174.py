from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


class ApplicabilityStoreError(RuntimeError):
    """Base error for KIR-174 persistence operations."""


class StaleApplicabilityAction(ApplicabilityStoreError):
    """Raised when an applicability action targets an obsolete revision."""


@dataclass(frozen=True, slots=True)
class ApplicabilityProfileRecord:
    completed_months: int | None
    completed_years: int | None
    sex_applicability: str | None
    life_stage: str | None
    physiological_condition: str | None
    revision: int


@dataclass(frozen=True, slots=True)
class IronSupervisionRecord:
    scope_key: str
    under_medical_supervision: bool | None
    revision: int


_PROFILE_FIELDS = frozenset({"sex_applicability", "life_stage", "physiological_condition"})
_PROFILE_VALUES = {
    "sex_applicability": frozenset({"male", "female"}),
    "life_stage": frozenset({"general", "pregnancy", "lactation"}),
    "physiological_condition": frozenset({"premenopausal", "postmenopausal"}),
}


class KIR174Store:
    """Current-only sensitive applicability persistence with explicit revision semantics."""

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
    def _profile_from_row(row: dict[str, Any] | None) -> ApplicabilityProfileRecord:
        if row is None:
            return ApplicabilityProfileRecord(
                completed_months=None,
                completed_years=None,
                sex_applicability=None,
                life_stage=None,
                physiological_condition=None,
                revision=0,
            )
        return ApplicabilityProfileRecord(
            completed_months=row["completed_months"],
            completed_years=row["completed_years"],
            sex_applicability=row["sex_applicability"],
            life_stage=row["life_stage"],
            physiological_condition=row["physiological_condition"],
            revision=int(row["revision"]),
        )

    @staticmethod
    def _claim_action(
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        action_key: str,
        action_type: str,
    ) -> bool:
        row = conn.execute(
            """
            INSERT INTO bot_action_receipts (user_id, action_key, action_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, action_key) DO NOTHING
            RETURNING action_key
            """,
            (user_id, action_key, action_type),
        ).fetchone()
        return row is not None

    @staticmethod
    def _locked_profile(
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
    ) -> ApplicabilityProfileRecord:
        row = conn.execute(
            """
            SELECT completed_months, completed_years, sex_applicability,
                   life_stage, physiological_condition, revision
            FROM user_applicability_profiles
            WHERE user_id = %s
            FOR UPDATE
            """,
            (user_id,),
        ).fetchone()
        return KIR174Store._profile_from_row(row)

    def profile(self, user_id: UUID) -> ApplicabilityProfileRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT completed_months, completed_years, sex_applicability,
                       life_stage, physiological_condition, revision
                FROM user_applicability_profiles
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
        return self._profile_from_row(row)

    def iron_supervision(self, user_id: UUID, scope_key: str) -> IronSupervisionRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT scope_key, under_medical_supervision, revision
                FROM iron_exposure_applicability
                WHERE user_id = %s AND scope_key = %s
                """,
                (user_id, scope_key),
            ).fetchone()
        if row is None:
            return IronSupervisionRecord(
                scope_key=scope_key,
                under_medical_supervision=None,
                revision=0,
            )
        return IronSupervisionRecord(
            scope_key=str(row["scope_key"]),
            under_medical_supervision=row["under_medical_supervision"],
            revision=int(row["revision"]),
        )




    def save_age(
        self,
        user_id: UUID,
        action_key: str,
        *,
        value: int,
        age_unit: str,
        expected_revision: int,
    ) -> ApplicabilityProfileRecord:
        if age_unit == "months":
            if value < 0 or value >= 24:
                raise ValueError("completed months must be from 0 through 23")
            completed_months, completed_years = value, None
        elif age_unit == "years":
            if value < 2:
                raise ValueError("completed years must be at least 2")
            completed_months, completed_years = None, value
        else:
            raise ValueError("unsupported age unit")

        with self._connect() as conn:
            claimed = self._claim_action(conn, user_id, action_key, "applicability_age_save")
            current = self._locked_profile(conn, user_id)
            if not claimed:
                return current
            if current.revision != expected_revision:
                raise StaleApplicabilityAction("applicability profile changed")
            if (
                current.completed_months == completed_months
                and current.completed_years == completed_years
            ):
                return current
            self._write_profile(
                conn,
                user_id,
                current,
                completed_months=completed_months,
                completed_years=completed_years,
            )
            return self._locked_profile(conn, user_id)


    def save_profile_fact(
        self,
        user_id: UUID,
        action_key: str,
        *,
        field: str,
        value: str,
        expected_revision: int,
    ) -> ApplicabilityProfileRecord:
        if field not in _PROFILE_FIELDS:
            raise ValueError("unsupported applicability profile field")
        if value not in _PROFILE_VALUES[field]:
            raise ValueError("unsupported applicability profile value")
        with self._connect() as conn:
            claimed = self._claim_action(conn, user_id, action_key, f"applicability_{field}_save")
            current = self._locked_profile(conn, user_id)
            if not claimed:
                return current
            if current.revision != expected_revision:
                raise StaleApplicabilityAction("applicability profile changed")
            if getattr(current, field) == value:
                return current
            self._write_profile(conn, user_id, current, **{field: value})
            return self._locked_profile(conn, user_id)

    def delete_profile_fact(
        self,
        user_id: UUID,
        action_key: str,
        *,
        field: str,
        expected_revision: int,
    ) -> ApplicabilityProfileRecord:
        if field not in _PROFILE_FIELDS | {"age"}:
            raise ValueError("unsupported applicability profile field")
        with self._connect() as conn:
            claimed = self._claim_action(conn, user_id, action_key, f"applicability_{field}_delete")
            current = self._locked_profile(conn, user_id)
            if not claimed:
                return current
            if current.revision != expected_revision:
                raise StaleApplicabilityAction("applicability profile changed")
            changes: dict[str, object | None]
            if field == "age":
                if current.completed_months is None and current.completed_years is None:
                    return current
                changes = {"completed_months": None, "completed_years": None}
            else:
                if getattr(current, field) is None:
                    return current
                changes = {field: None}
            self._write_profile(conn, user_id, current, **changes)
            return self._locked_profile(conn, user_id)

    def save_iron_supervision(
        self,
        user_id: UUID,
        action_key: str,
        *,
        scope_key: str,
        value: bool,
        expected_revision: int,
    ) -> IronSupervisionRecord:
        if not scope_key.strip():
            raise ValueError("scope_key must not be blank")
        with self._connect() as conn:
            claimed = self._claim_action(conn, user_id, action_key, "iron_supervision_save")
            row = conn.execute(
                """
                SELECT under_medical_supervision, revision
                FROM iron_exposure_applicability
                WHERE user_id = %s AND scope_key = %s
                FOR UPDATE
                """,
                (user_id, scope_key),
            ).fetchone()
            current_revision = 0 if row is None else int(row["revision"])
            if not claimed:
                return self.iron_supervision(user_id, scope_key)
            if current_revision != expected_revision:
                raise StaleApplicabilityAction("iron exposure context changed")
            if row is not None and row["under_medical_supervision"] is value:
                return self.iron_supervision(user_id, scope_key)
            if row is None:
                conn.execute(
                    """
                    INSERT INTO iron_exposure_applicability (
                        user_id, scope_key, under_medical_supervision, revision
                    )
                    VALUES (%s, %s, %s, 1)
                    """,
                    (user_id, scope_key, value),
                )
            else:
                conn.execute(
                    """
                    UPDATE iron_exposure_applicability
                    SET under_medical_supervision = %s,
                        revision = revision + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND scope_key = %s
                    """,
                    (value, user_id, scope_key),
                )
        return self.iron_supervision(user_id, scope_key)

    def delete_iron_supervision(
        self,
        user_id: UUID,
        action_key: str,
        *,
        scope_key: str,
        expected_revision: int,
    ) -> IronSupervisionRecord:
        with self._connect() as conn:
            claimed = self._claim_action(conn, user_id, action_key, "iron_supervision_delete")
            row = conn.execute(
                """
                SELECT under_medical_supervision, revision
                FROM iron_exposure_applicability
                WHERE user_id = %s AND scope_key = %s
                FOR UPDATE
                """,
                (user_id, scope_key),
            ).fetchone()
            current_revision = 0 if row is None else int(row["revision"])
            if not claimed:
                return self.iron_supervision(user_id, scope_key)
            if current_revision != expected_revision:
                raise StaleApplicabilityAction("iron exposure context changed")
            if row is None or row["under_medical_supervision"] is None:
                return self.iron_supervision(user_id, scope_key)
            conn.execute(
                """
                UPDATE iron_exposure_applicability
                SET under_medical_supervision = NULL,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND scope_key = %s
                """,
                (user_id, scope_key),
            )
        return self.iron_supervision(user_id, scope_key)


    @staticmethod
    def _write_profile(
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        current: ApplicabilityProfileRecord,
        **changes: object | None,
    ) -> None:
        values: dict[str, object | None] = {
            "completed_months": current.completed_months,
            "completed_years": current.completed_years,
            "sex_applicability": current.sex_applicability,
            "life_stage": current.life_stage,
            "physiological_condition": current.physiological_condition,
        }
        values.update(changes)
        if current.revision == 0:
            conn.execute(
                """
                INSERT INTO user_applicability_profiles (
                    user_id, completed_months, completed_years, sex_applicability,
                    life_stage, physiological_condition, revision
                )
                VALUES (%s, %s, %s, %s, %s, %s, 1)
                """,
                (
                    user_id,
                    values["completed_months"],
                    values["completed_years"],
                    values["sex_applicability"],
                    values["life_stage"],
                    values["physiological_condition"],
                ),
            )
        else:
            conn.execute(
                """
                UPDATE user_applicability_profiles
                SET completed_months = %s,
                    completed_years = %s,
                    sex_applicability = %s,
                    life_stage = %s,
                    physiological_condition = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                """,
                (
                    values["completed_months"],
                    values["completed_years"],
                    values["sex_applicability"],
                    values["life_stage"],
                    values["physiological_condition"],
                    user_id,
                ),
            )
