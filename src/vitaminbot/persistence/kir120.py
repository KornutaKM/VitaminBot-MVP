from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

_INTAKE_CONFIRMATION_SOURCE_ID = "source:vitaminbot:user-intake-action"
_MAX_DELIVERY_ATTEMPTS = 3


class ScheduleError(RuntimeError):
    """Base error for KIR-120 scheduling operations."""


class MissingTimezone(ScheduleError):
    """Raised when local scheduling is requested without a user timezone."""


class InvalidScheduleTime(ScheduleError):
    """Raised when a local schedule value cannot be resolved safely."""


class AmbiguousLocalTime(InvalidScheduleTime):
    """Raised when a local clock time maps to two UTC instants."""


class NonexistentLocalTime(InvalidScheduleTime):
    """Raised when a local clock time does not exist because of a DST transition."""


class StaleOccurrence(ScheduleError):
    """Raised when an occurrence callback targets an obsolete revision."""


class InvalidOccurrenceState(ScheduleError):
    """Raised when an action is incompatible with the current occurrence state."""


class ScheduleRecordNotFound(ScheduleError):
    """Raised when a user-owned schedule record cannot be found."""


@dataclass(frozen=True, slots=True)
class RoutineTimes:
    morning: time
    day: time
    evening: time

    @classmethod
    def from_strings(cls, morning: str, day: str, evening: str) -> RoutineTimes:
        return cls(
            morning=_parse_clock(morning),
            day=_parse_clock(day),
            evening=_parse_clock(evening),
        )

    def for_bucket(self, bucket: str) -> time:
        mapping = {
            "morning": self.morning,
            "day": self.day,
            "evening": self.evening,
        }
        try:
            return mapping[bucket]
        except KeyError as exc:
            raise InvalidScheduleTime(f"unsupported routine bucket: {bucket}") from exc


@dataclass(frozen=True, slots=True)
class ScheduleTemplate:
    instance_id: str
    name: str
    plan_id: str
    plan_version: str
    plan_revision: int
    event_id: str
    unit_id: str
    unit_label: str
    quantity: Decimal
    schedule_kind: str
    schedule_label: str | None
    local_time: time | None


@dataclass(frozen=True, slots=True)
class OccurrenceRecord:
    occurrence_id: str
    instance_id: str
    name: str
    unit_id: str
    unit_label: str
    quantity: Decimal
    schedule_kind: str
    schedule_label: str
    timezone: str
    local_date: date
    scheduled_local_time: time
    scheduled_at: datetime
    due_at: datetime
    state: str
    later_count: int
    revision: int


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    delivery_id: str
    occurrence_id: str
    occurrence_revision: int
    telegram_user_id: int
    name: str
    quantity: Decimal
    unit_label: str
    schedule_label: str
    due_at: datetime
    later_count: int


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    action_id: str
    occurrence_id: str
    occurrence_revision: int
    action_kind: str
    name: str
    quantity: Decimal
    unit_label: str
    created_at: datetime
    entered_in_error: bool
    correctable: bool


@dataclass(frozen=True, slots=True)
class AdherenceSummaryRecord:
    days: int
    start_date: date
    end_date: date
    planned: int
    taken: int
    skipped: int
    unresolved: int


def _parse_clock(value: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise InvalidScheduleTime("time must use HH:MM format") from exc
    if parsed.second != 0 or parsed.microsecond != 0 or parsed.tzinfo is not None:
        raise InvalidScheduleTime("time must use local HH:MM without seconds or timezone")
    return parsed


def resolve_local_datetime(local_date: date, local_time: time, timezone_name: str) -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise InvalidScheduleTime("stored timezone is not a valid IANA timezone") from exc

    naive = datetime.combine(local_date, local_time)
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        utc_value = aware.astimezone(UTC)
        round_trip = utc_value.astimezone(zone).replace(tzinfo=None)
        if round_trip == naive:
            candidates[utc_value] = aware

    if not candidates:
        raise NonexistentLocalTime(
            f"{local_date.isoformat()} {local_time.isoformat(timespec='minutes')} "
            f"does not exist in {timezone_name}"
        )
    if len(candidates) > 1:
        raise AmbiguousLocalTime(
            f"{local_date.isoformat()} {local_time.isoformat(timespec='minutes')} "
            f"is ambiguous in {timezone_name}"
        )
    return next(iter(candidates)).astimezone(UTC)


class KIR120Store:
    """Durable schedule/occurrence/reminder/action repository."""

    def __init__(
        self,
        database_url: str,
        *,
        schema: str = "public",
        routine_times: RoutineTimes | None = None,
    ) -> None:
        self._database_url = database_url
        self._schema = schema
        self._routine_times = routine_times or RoutineTimes.from_strings("08:00", "13:00", "19:00")

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
                raise ScheduleError("database returned an invalid user_id")
            return value

    def user_id(self, telegram_user_id: int) -> UUID:
        return self.ensure_user(telegram_user_id)

    def list_templates(self, user_id: UUID) -> tuple[ScheduleTemplate, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    us.instance_id,
                    us.container_label,
                    head.plan_id,
                    head.plan_version,
                    head.revision AS plan_revision,
                    event.event_id,
                    event.consumption_unit_id,
                    unit.label_name AS unit_label,
                    event.consumption_units,
                    event.schedule_kind,
                    event.schedule_label,
                    event.local_time
                FROM intake_plan_heads AS head
                JOIN user_supplements AS us
                  ON us.instance_id = head.tracked_instance_id
                JOIN planned_intake_events AS event
                  ON event.plan_id = head.plan_id
                 AND event.plan_version = head.plan_version
                JOIN consumption_units AS unit
                  ON unit.formulation_id = event.formulation_id
                 AND unit.unit_id = event.consumption_unit_id
                WHERE us.user_id = %s
                  AND us.lifecycle_status = 'active'
                ORDER BY us.created_at, us.instance_id, event.event_id
                """,
                (user_id,),
            ).fetchall()
        return tuple(self._template_from_row(row) for row in rows)

    def schedule_session(self, user_id: UUID) -> tuple[str, int, int] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT tracked_instance_id, expected_plan_revision, revision
                FROM schedule_edit_sessions
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return (
            str(row["tracked_instance_id"]),
            int(row["expected_plan_revision"]),
            int(row["revision"]),
        )

    def begin_explicit_time_edit(
        self,
        user_id: UUID,
        action_key: str,
        instance_id: str,
        expected_plan_revision: int,
    ) -> int:
        with self._connect() as conn:
            claimed = self._claim_action(conn, user_id, action_key, "k120_explicit_time_begin")
            template = self._locked_template(conn, user_id, instance_id)
            if template.plan_revision != expected_plan_revision:
                raise StaleOccurrence("plan changed before schedule editing started")
            if not claimed:
                session = conn.execute(
                    """
                    SELECT revision
                    FROM schedule_edit_sessions
                    WHERE user_id = %s
                    """,
                    (user_id,),
                ).fetchone()
                if session is None:
                    raise InvalidOccurrenceState("explicit-time edit session is no longer active")
                return int(session["revision"])

            row = conn.execute(
                """
                INSERT INTO schedule_edit_sessions (
                    user_id,
                    tracked_instance_id,
                    expected_plan_revision
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET tracked_instance_id = EXCLUDED.tracked_instance_id,
                    expected_plan_revision = EXCLUDED.expected_plan_revision,
                    revision = schedule_edit_sessions.revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING revision
                """,
                (user_id, instance_id, expected_plan_revision),
            ).fetchone()
            assert row is not None
            self._complete_action(conn, user_id, action_key, instance_id)
            return int(row["revision"])

    def cancel_schedule_edit(self, user_id: UUID) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM schedule_edit_sessions WHERE user_id = %s",
                (user_id,),
            )

    def save_explicit_time(
        self,
        user_id: UUID,
        action_key: str,
        local_time: time,
    ) -> ScheduleTemplate:
        with self._connect() as conn:
            session = conn.execute(
                """
                SELECT tracked_instance_id, expected_plan_revision
                FROM schedule_edit_sessions
                WHERE user_id = %s
                FOR UPDATE
                """,
                (user_id,),
            ).fetchone()
            if session is None:
                raise InvalidOccurrenceState("explicit-time edit session is not active")
            result = self._replace_schedule(
                conn,
                user_id,
                action_key,
                str(session["tracked_instance_id"]),
                int(session["expected_plan_revision"]),
                schedule_kind="explicit_time",
                schedule_label="explicit_time",
                local_time=local_time,
            )
            conn.execute("DELETE FROM schedule_edit_sessions WHERE user_id = %s", (user_id,))
            return result

    def set_schedule_bucket(
        self,
        user_id: UUID,
        action_key: str,
        instance_id: str,
        expected_plan_revision: int,
        bucket: str,
    ) -> ScheduleTemplate:
        self._routine_times.for_bucket(bucket)
        with self._connect() as conn:
            return self._replace_schedule(
                conn,
                user_id,
                action_key,
                instance_id,
                expected_plan_revision,
                schedule_kind="routine_bucket",
                schedule_label=bucket,
                local_time=None,
            )

    def today(self, user_id: UUID, now: datetime) -> tuple[OccurrenceRecord, ...]:
        now = _require_aware(now)
        timezone_name = self._timezone_for_user(user_id)
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise InvalidScheduleTime("stored timezone is not a valid IANA timezone") from exc
        local_date = now.astimezone(zone).date()
        self.materialize_user_date(user_id, local_date)
        return self.occurrences_for_date(user_id, local_date)

    def materialize_user_date(
        self,
        user_id: UUID,
        local_date: date,
    ) -> tuple[OccurrenceRecord, ...]:
        timezone_name = self._timezone_for_user(user_id)
        templates = self.list_templates(user_id)
        with self._connect() as conn:
            for template in templates:
                scheduled_local_time = self._local_time_for_template(template)
                if scheduled_local_time is None:
                    continue
                scheduled_at = resolve_local_datetime(
                    local_date,
                    scheduled_local_time,
                    timezone_name,
                )
                occurrence_id = uuid4().hex[:20]
                conn.execute(
                    """
                    INSERT INTO reminder_occurrences (
                        occurrence_id,
                        user_id,
                        tracked_instance_id,
                        formulation_id,
                        plan_id,
                        plan_version,
                        planned_event_id,
                        consumption_unit_id,
                        consumption_units,
                        schedule_kind,
                        schedule_label,
                        timezone,
                        local_date,
                        scheduled_local_time,
                        scheduled_at,
                        due_at
                    )
                    SELECT
                        %s,
                        %s,
                        plan.tracked_instance_id,
                        plan.formulation_id,
                        event.plan_id,
                        event.plan_version,
                        event.event_id,
                        event.consumption_unit_id,
                        event.consumption_units,
                        event.schedule_kind,
                        event.schedule_label,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    FROM intake_plans AS plan
                    JOIN planned_intake_events AS event
                      ON event.plan_id = plan.plan_id
                     AND event.plan_version = plan.version
                    WHERE plan.plan_id = %s
                      AND plan.version = %s
                      AND event.event_id = %s
                      AND EXISTS (
                          SELECT 1
                          FROM user_supplements AS current_supplement
                          WHERE current_supplement.instance_id = plan.tracked_instance_id
                            AND current_supplement.user_id = %s
                            AND current_supplement.lifecycle_status = 'active'
                      )
                    ON CONFLICT (tracked_instance_id, local_date) DO NOTHING
                    """,
                    (
                        occurrence_id,
                        user_id,
                        timezone_name,
                        local_date,
                        scheduled_local_time,
                        scheduled_at,
                        scheduled_at,
                        template.plan_id,
                        template.plan_version,
                        template.event_id,
                        user_id,
                    ),
                )
        return self.occurrences_for_date(user_id, local_date)

    def materialize_all(self, now: datetime) -> tuple[str, ...]:
        now = _require_aware(now)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT profile.user_id, profile.timezone
                FROM user_profiles AS profile
                JOIN user_supplements AS us
                  ON us.user_id = profile.user_id
                JOIN intake_plan_heads AS head
                  ON head.tracked_instance_id = us.instance_id
                WHERE profile.timezone IS NOT NULL
                  AND us.lifecycle_status = 'active'
                ORDER BY profile.user_id
                """
            ).fetchall()
        failures: list[str] = []
        for row in rows:
            timezone_name = str(row["timezone"])
            try:
                zone = ZoneInfo(timezone_name)
                local_date = now.astimezone(zone).date()
                self.materialize_user_date(row["user_id"], local_date)
            except (ScheduleError, ZoneInfoNotFoundError):
                failures.append(str(row["user_id"]))
        return tuple(failures)

    def occurrences_for_date(
        self,
        user_id: UUID,
        local_date: date,
    ) -> tuple[OccurrenceRecord, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                self._occurrence_query()
                + """
                  AND occurrence.local_date = %s
                ORDER BY occurrence.scheduled_at, occurrence.occurrence_id
                """,
                (user_id, local_date),
            ).fetchall()
        return tuple(self._occurrence_from_row(row) for row in rows)

    def occurrence(self, user_id: UUID, occurrence_id: str) -> OccurrenceRecord:
        with self._connect() as conn:
            row = conn.execute(
                self._occurrence_query() + " AND occurrence.occurrence_id = %s",
                (user_id, occurrence_id),
            ).fetchone()
        if row is None:
            raise ScheduleRecordNotFound("occurrence not found")
        return self._occurrence_from_row(row)

    def take(
        self,
        user_id: UUID,
        occurrence_id: str,
        expected_revision: int,
        action_key: str,
        now: datetime,
    ) -> OccurrenceRecord:
        return self._apply_action(
            user_id,
            occurrence_id,
            expected_revision,
            action_key,
            "taken",
            _require_aware(now),
            later_until=None,
        )

    def skip(
        self,
        user_id: UUID,
        occurrence_id: str,
        expected_revision: int,
        action_key: str,
        now: datetime,
    ) -> OccurrenceRecord:
        return self._apply_action(
            user_id,
            occurrence_id,
            expected_revision,
            action_key,
            "skip",
            _require_aware(now),
            later_until=None,
        )

    def later(
        self,
        user_id: UUID,
        occurrence_id: str,
        expected_revision: int,
        action_key: str,
        now: datetime,
        later_until: datetime,
    ) -> OccurrenceRecord:
        return self._apply_action(
            user_id,
            occurrence_id,
            expected_revision,
            action_key,
            "later",
            _require_aware(now),
            later_until=_require_aware(later_until),
        )

    def correct_latest(
        self,
        user_id: UUID,
        occurrence_id: str,
        expected_revision: int,
        action_key: str,
        now: datetime,
    ) -> OccurrenceRecord:
        now = _require_aware(now)
        with self._connect() as conn:
            duplicate = conn.execute(
                """
                SELECT occurrence_id
                FROM occurrence_actions
                WHERE idempotency_key = %s
                """,
                (action_key,),
            ).fetchone()
            if duplicate is not None:
                if duplicate["occurrence_id"] != occurrence_id:
                    raise InvalidOccurrenceState(
                        "action key was already used for another occurrence"
                    )
                return self._occurrence_in_connection(conn, user_id, occurrence_id)

            current = self._locked_occurrence(conn, user_id, occurrence_id)
            if current.revision != expected_revision:
                raise StaleOccurrence("occurrence changed before correction")
            if current.state not in {"taken", "skipped"}:
                raise InvalidOccurrenceState("only taken or skipped actions can be corrected")

            previous = conn.execute(
                """
                SELECT action_id, intake_event_id
                FROM occurrence_actions
                WHERE occurrence_id = %s
                  AND action_kind IN ('taken', 'skip')
                  AND entered_in_error_at IS NULL
                ORDER BY created_at DESC, action_id DESC
                LIMIT 1
                FOR UPDATE
                """,
                (occurrence_id,),
            ).fetchone()
            if previous is None:
                raise InvalidOccurrenceState("no active taken/skip action is available to correct")

            conn.execute(
                """
                UPDATE occurrence_actions
                SET entered_in_error_at = %s
                WHERE action_id = %s
                """,
                (now, previous["action_id"]),
            )
            if previous["intake_event_id"] is not None:
                conn.execute(
                    """
                    UPDATE intake_events
                    SET entered_in_error_at = %s
                    WHERE event_id = %s
                    """,
                    (now, previous["intake_event_id"]),
                )
                self._correct_inventory_for_intake(
                    conn,
                    str(previous["intake_event_id"]),
                )

            conn.execute(
                """
                INSERT INTO occurrence_actions (
                    action_id,
                    occurrence_id,
                    action_kind,
                    idempotency_key,
                    occurrence_revision,
                    corrects_action_id
                )
                VALUES (%s, %s, 'correction', %s, %s, %s)
                """,
                (
                    f"action:k120:{uuid4().hex}",
                    occurrence_id,
                    action_key,
                    expected_revision,
                    previous["action_id"],
                ),
            )
            conn.execute(
                """
                UPDATE reminder_occurrences
                SET state = 'needs_review',
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE occurrence_id = %s
                """,
                (occurrence_id,),
            )
            self._cancel_claimed_deliveries(conn, occurrence_id, now)
            return self._occurrence_in_connection(conn, user_id, occurrence_id)

    def adherence_summary(
        self,
        user_id: UUID,
        now: datetime,
        *,
        days: int,
    ) -> AdherenceSummaryRecord:
        now = _require_aware(now)
        if days < 1:
            raise ValueError("days must be positive")

        timezone_name = self._timezone_for_user(user_id)
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise InvalidScheduleTime("stored timezone is not a valid IANA timezone") from exc

        end_date = now.astimezone(zone).date()
        start_date = end_date - timedelta(days=days - 1)

        # Ensure the current local day exists when a user opens stats before the worker loop.
        self.materialize_user_date(user_id, end_date)

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    count(*) AS planned,
                    count(*) FILTER (WHERE state = 'taken') AS taken,
                    count(*) FILTER (WHERE state = 'skipped') AS skipped,
                    count(*) FILTER (
                        WHERE state IN ('pending', 'needs_review')
                    ) AS unresolved
                FROM reminder_occurrences
                WHERE user_id = %s
                  AND cancelled_at IS NULL
                  AND local_date BETWEEN %s AND %s
                  AND due_at <= %s
                """,
                (user_id, start_date, end_date, now),
            ).fetchone()
        assert row is not None
        return AdherenceSummaryRecord(
            days=days,
            start_date=start_date,
            end_date=end_date,
            planned=int(row["planned"]),
            taken=int(row["taken"]),
            skipped=int(row["skipped"]),
            unresolved=int(row["unresolved"]),
        )

    def history(self, user_id: UUID, limit: int = 20) -> tuple[HistoryEntry, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    action.action_id,
                    action.occurrence_id,
                    occurrence.revision AS current_occurrence_revision,
                    action.action_kind,
                    us.container_label,
                    occurrence.consumption_units,
                    unit.label_name AS unit_label,
                    action.created_at,
                    action.entered_in_error_at IS NOT NULL AS entered_in_error,
                    (
                        action.action_kind IN ('taken', 'skip')
                        AND action.entered_in_error_at IS NULL
                        AND occurrence.state IN ('taken', 'skipped')
                        AND action.action_id = (
                            SELECT latest.action_id
                            FROM occurrence_actions AS latest
                            WHERE latest.occurrence_id = occurrence.occurrence_id
                              AND latest.action_kind IN ('taken', 'skip')
                              AND latest.entered_in_error_at IS NULL
                            ORDER BY latest.created_at DESC, latest.action_id DESC
                            LIMIT 1
                        )
                    ) AS correctable
                FROM occurrence_actions AS action
                JOIN reminder_occurrences AS occurrence
                  ON occurrence.occurrence_id = action.occurrence_id
                JOIN user_supplements AS us
                  ON us.instance_id = occurrence.tracked_instance_id
                 AND us.user_id = occurrence.user_id
                JOIN consumption_units AS unit
                  ON unit.formulation_id = occurrence.formulation_id
                 AND unit.unit_id = occurrence.consumption_unit_id
                WHERE occurrence.user_id = %s
                ORDER BY action.created_at DESC, action.action_id DESC
                LIMIT %s
                """,
                (user_id, limit),
            ).fetchall()
        return tuple(
            HistoryEntry(
                action_id=str(row["action_id"]),
                occurrence_id=str(row["occurrence_id"]),
                occurrence_revision=int(row["current_occurrence_revision"]),
                action_kind=str(row["action_kind"]),
                name=str(row["container_label"]),
                quantity=row["consumption_units"],
                unit_label=str(row["unit_label"]),
                created_at=row["created_at"],
                entered_in_error=bool(row["entered_in_error"]),
                correctable=bool(row["correctable"]),
            )
            for row in rows
        )

    def claim_due_reminders(
        self,
        now: datetime,
        execution_key: str,
        *,
        lease: timedelta = timedelta(minutes=2),
        limit: int = 100,
    ) -> tuple[DeliveryClaim, ...]:
        now = _require_aware(now)
        if not execution_key.strip():
            raise ValueError("execution_key must not be blank")
        if lease <= timedelta(0):
            raise ValueError("lease must be positive")
        if limit < 1:
            raise ValueError("limit must be positive")

        claims: list[DeliveryClaim] = []
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE reminder_delivery_attempts
                SET status = 'uncertain',
                    completed_at = %s
                WHERE status = 'claimed'
                  AND lease_expires_at <= %s
                """,
                (now, now),
            )
            rows = conn.execute(
                """
                SELECT
                    occurrence.occurrence_id,
                    occurrence.revision,
                    occurrence.due_at,
                    occurrence.later_count,
                    occurrence.user_id,
                    users.telegram_user_id,
                    us.container_label,
                    occurrence.consumption_units,
                    unit.label_name AS unit_label,
                    occurrence.schedule_label,
                    (
                        SELECT count(*)
                        FROM reminder_delivery_attempts AS prior
                        WHERE prior.occurrence_id = occurrence.occurrence_id
                          AND prior.occurrence_revision = occurrence.revision
                          AND prior.status = 'failed'
                    ) AS failed_attempts
                FROM reminder_occurrences AS occurrence
                JOIN users
                  ON users.user_id = occurrence.user_id
                JOIN user_supplements AS us
                  ON us.instance_id = occurrence.tracked_instance_id
                 AND us.user_id = occurrence.user_id
                JOIN consumption_units AS unit
                  ON unit.formulation_id = occurrence.formulation_id
                 AND unit.unit_id = occurrence.consumption_unit_id
                WHERE occurrence.state = 'pending'
                  AND occurrence.cancelled_at IS NULL
                  AND us.lifecycle_status = 'active'
                  AND occurrence.due_at <= %s
                  AND users.telegram_user_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM reminder_delivery_attempts AS delivery
                      WHERE delivery.occurrence_id = occurrence.occurrence_id
                        AND delivery.occurrence_revision = occurrence.revision
                        AND (
                            delivery.status IN ('sent', 'uncertain')
                            OR (
                                delivery.status = 'claimed'
                                AND delivery.lease_expires_at > %s
                            )
                        )
                  )
                  AND (
                      SELECT count(*)
                      FROM reminder_delivery_attempts AS failed
                      WHERE failed.occurrence_id = occurrence.occurrence_id
                        AND failed.occurrence_revision = occurrence.revision
                        AND failed.status = 'failed'
                  ) < %s
                ORDER BY occurrence.due_at, occurrence.occurrence_id
                FOR UPDATE OF occurrence SKIP LOCKED
                LIMIT %s
                """,
                (now, now, _MAX_DELIVERY_ATTEMPTS, limit),
            ).fetchall()
            for row in rows:
                attempt_number = int(row["failed_attempts"]) + 1
                delivery_id = f"delivery:k120:{uuid4().hex}"
                idempotency_key = f"{execution_key}:{row['occurrence_id']}:{int(row['revision'])}"
                inserted = conn.execute(
                    """
                    INSERT INTO reminder_delivery_attempts (
                        delivery_id,
                        occurrence_id,
                        occurrence_revision,
                        idempotency_key,
                        attempt_number,
                        status,
                        lease_expires_at,
                        claimed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 'claimed', %s, %s)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING delivery_id
                    """,
                    (
                        delivery_id,
                        row["occurrence_id"],
                        row["revision"],
                        idempotency_key,
                        attempt_number,
                        now + lease,
                        now,
                    ),
                ).fetchone()
                if inserted is None:
                    continue
                claims.append(
                    DeliveryClaim(
                        delivery_id=delivery_id,
                        occurrence_id=str(row["occurrence_id"]),
                        occurrence_revision=int(row["revision"]),
                        telegram_user_id=int(row["telegram_user_id"]),
                        name=str(row["container_label"]),
                        quantity=row["consumption_units"],
                        unit_label=str(row["unit_label"]),
                        schedule_label=str(row["schedule_label"]),
                        due_at=row["due_at"],
                        later_count=int(row["later_count"]),
                    )
                )
        return tuple(claims)

    def validate_claim(self, delivery_id: str, now: datetime) -> DeliveryClaim | None:
        now = _require_aware(now)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    delivery.delivery_id,
                    occurrence.occurrence_id,
                    occurrence.revision,
                    users.telegram_user_id,
                    us.container_label,
                    occurrence.consumption_units,
                    unit.label_name AS unit_label,
                    occurrence.schedule_label,
                    occurrence.due_at,
                    occurrence.later_count,
                    occurrence.cancelled_at,
                    us.lifecycle_status,
                    delivery.lease_expires_at,
                    delivery.occurrence_revision
                FROM reminder_delivery_attempts AS delivery
                JOIN reminder_occurrences AS occurrence
                  ON occurrence.occurrence_id = delivery.occurrence_id
                JOIN users
                  ON users.user_id = occurrence.user_id
                JOIN user_supplements AS us
                  ON us.instance_id = occurrence.tracked_instance_id
                 AND us.user_id = occurrence.user_id
                JOIN consumption_units AS unit
                  ON unit.formulation_id = occurrence.formulation_id
                 AND unit.unit_id = occurrence.consumption_unit_id
                WHERE delivery.delivery_id = %s
                  AND delivery.status = 'claimed'
                FOR UPDATE OF delivery
                """,
                (delivery_id,),
            ).fetchone()
            if row is None:
                return None
            if (
                row["lease_expires_at"] <= now
                or int(row["occurrence_revision"]) != int(row["revision"])
                or row["telegram_user_id"] is None
                or row["cancelled_at"] is not None
                or row["lifecycle_status"] != "active"
            ):
                conn.execute(
                    """
                    UPDATE reminder_delivery_attempts
                    SET status = 'cancelled',
                        completed_at = %s
                    WHERE delivery_id = %s
                    """,
                    (now, delivery_id),
                )
                return None
            occurrence = conn.execute(
                "SELECT state FROM reminder_occurrences WHERE occurrence_id = %s",
                (row["occurrence_id"],),
            ).fetchone()
            if occurrence is None or occurrence["state"] != "pending":
                conn.execute(
                    """
                    UPDATE reminder_delivery_attempts
                    SET status = 'cancelled',
                        completed_at = %s
                    WHERE delivery_id = %s
                    """,
                    (now, delivery_id),
                )
                return None
            return DeliveryClaim(
                delivery_id=str(row["delivery_id"]),
                occurrence_id=str(row["occurrence_id"]),
                occurrence_revision=int(row["revision"]),
                telegram_user_id=int(row["telegram_user_id"]),
                name=str(row["container_label"]),
                quantity=row["consumption_units"],
                unit_label=str(row["unit_label"]),
                schedule_label=str(row["schedule_label"]),
                due_at=row["due_at"],
                later_count=int(row["later_count"]),
            )

    def mark_delivery_sent(
        self,
        delivery_id: str,
        provider_message_id: str,
        now: datetime,
    ) -> None:
        now = _require_aware(now)
        if not provider_message_id.strip():
            raise ValueError("provider_message_id must not be blank")
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE reminder_delivery_attempts
                SET status = 'sent',
                    provider_message_id = %s,
                    completed_at = %s
                WHERE delivery_id = %s
                  AND status = 'claimed'
                RETURNING delivery_id
                """,
                (provider_message_id, now, delivery_id),
            ).fetchone()
            if row is None:
                existing = conn.execute(
                    "SELECT status FROM reminder_delivery_attempts WHERE delivery_id = %s",
                    (delivery_id,),
                ).fetchone()
                if existing is None or existing["status"] != "sent":
                    raise InvalidOccurrenceState("delivery is not claimable as sent")

    def mark_delivery_failed(self, delivery_id: str, failure_code: str, now: datetime) -> None:
        now = _require_aware(now)
        normalized = failure_code.strip()[:80]
        if not normalized:
            raise ValueError("failure_code must not be blank")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE reminder_delivery_attempts
                SET status = 'failed',
                    failure_code = %s,
                    completed_at = %s
                WHERE delivery_id = %s
                  AND status = 'claimed'
                """,
                (normalized, now, delivery_id),
            )

    def _apply_action(
        self,
        user_id: UUID,
        occurrence_id: str,
        expected_revision: int,
        action_key: str,
        action_kind: str,
        now: datetime,
        *,
        later_until: datetime | None,
    ) -> OccurrenceRecord:
        with self._connect() as conn:
            duplicate = conn.execute(
                """
                SELECT occurrence_id
                FROM occurrence_actions
                WHERE idempotency_key = %s
                """,
                (action_key,),
            ).fetchone()
            if duplicate is not None:
                if duplicate["occurrence_id"] != occurrence_id:
                    raise InvalidOccurrenceState(
                        "action key was already used for another occurrence"
                    )
                return self._occurrence_in_connection(conn, user_id, occurrence_id)

            current = self._locked_occurrence(conn, user_id, occurrence_id)
            if current.revision != expected_revision:
                raise StaleOccurrence("occurrence callback is stale")
            if action_kind in {"taken", "skip"}:
                if current.state not in {"pending", "needs_review"}:
                    raise InvalidOccurrenceState("occurrence is already resolved")
            elif action_kind == "later":
                if current.state != "pending":
                    raise InvalidOccurrenceState("only pending occurrences can be moved later")
                if current.later_count >= 1:
                    raise InvalidOccurrenceState("Later is limited to one one-off reschedule")
                if later_until is None or later_until <= now:
                    raise InvalidOccurrenceState("Later must move the occurrence into the future")
            else:
                raise ValueError("unsupported occurrence action")

            action_id = f"action:k120:{uuid4().hex}"
            intake_event_id: str | None = None
            if action_kind == "taken":
                intake_event_id = f"intake:k120:{uuid4().hex}"
                with conn.transaction():
                    self._ensure_intake_confirmation_source(conn)
                    conn.execute(
                        """
                        INSERT INTO intake_events (
                            event_id,
                            tracked_instance_id,
                            formulation_id,
                            consumption_unit_id,
                            consumption_units,
                            consumed_at,
                            confirmation_source_id,
                            idempotency_key
                        )
                        SELECT
                            %s,
                            tracked_instance_id,
                            formulation_id,
                            consumption_unit_id,
                            consumption_units,
                            %s,
                            %s,
                            %s
                        FROM reminder_occurrences
                        WHERE occurrence_id = %s
                        """,
                        (
                            intake_event_id,
                            now,
                            _INTAKE_CONFIRMATION_SOURCE_ID,
                            f"k120:{action_key}",
                            occurrence_id,
                        ),
                    )
                    self._decrement_inventory_for_intake(
                        conn,
                        current,
                        intake_event_id,
                    )

            conn.execute(
                """
                INSERT INTO occurrence_actions (
                    action_id,
                    occurrence_id,
                    action_kind,
                    idempotency_key,
                    occurrence_revision,
                    later_until,
                    intake_event_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    action_id,
                    occurrence_id,
                    action_kind,
                    action_key,
                    expected_revision,
                    later_until,
                    intake_event_id,
                ),
            )
            if action_kind == "taken":
                state = "taken"
                due_at = current.due_at
                later_count = current.later_count
            elif action_kind == "skip":
                state = "skipped"
                due_at = current.due_at
                later_count = current.later_count
            else:
                state = "pending"
                assert later_until is not None
                due_at = later_until
                later_count = current.later_count + 1

            conn.execute(
                """
                UPDATE reminder_occurrences
                SET state = %s,
                    due_at = %s,
                    later_count = %s,
                    revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE occurrence_id = %s
                """,
                (state, due_at, later_count, occurrence_id),
            )
            self._cancel_claimed_deliveries(conn, occurrence_id, now)
            return self._occurrence_in_connection(conn, user_id, occurrence_id)

    def _replace_schedule(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        action_key: str,
        instance_id: str,
        expected_plan_revision: int,
        *,
        schedule_kind: str,
        schedule_label: str,
        local_time: time | None,
    ) -> ScheduleTemplate:
        claimed = self._claim_action(conn, user_id, action_key, "k120_schedule_update")
        if not claimed:
            return self._locked_template(conn, user_id, instance_id)

        template = self._locked_template(conn, user_id, instance_id)
        if template.plan_revision != expected_plan_revision:
            raise StaleOccurrence("plan changed before schedule update")
        next_revision = expected_plan_revision + 1
        next_version = str(next_revision)
        event_id = (
            f"routine:{schedule_label}"
            if schedule_kind == "routine_bucket"
            else "routine:explicit_time"
        )
        formulation = conn.execute(
            """
            SELECT formulation_id
            FROM intake_plans
            WHERE plan_id = %s AND version = %s
            """,
            (template.plan_id, template.plan_version),
        ).fetchone()
        if formulation is None:
            raise ScheduleRecordNotFound("plan formulation is missing")

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
                template.plan_id,
                next_version,
                template.instance_id,
                formulation["formulation_id"],
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
                schedule_label,
                schedule_kind,
                local_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                template.plan_id,
                next_version,
                formulation["formulation_id"],
                event_id,
                template.unit_id,
                template.quantity,
                schedule_label,
                schedule_kind,
                local_time,
            ),
        )
        conn.execute(
            """
            UPDATE intake_plan_heads
            SET plan_version = %s,
                revision = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE tracked_instance_id = %s
              AND revision = %s
            """,
            (
                next_version,
                next_revision,
                template.instance_id,
                expected_plan_revision,
            ),
        )
        self._complete_action(conn, user_id, action_key, template.instance_id)
        return self._locked_template(conn, user_id, template.instance_id)

    def _timezone_for_user(self, user_id: UUID) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT timezone FROM user_profiles WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        if row is None or row["timezone"] is None:
            raise MissingTimezone("timezone is required before reminders can be scheduled")
        return str(row["timezone"])

    def _local_time_for_template(self, template: ScheduleTemplate) -> time | None:
        if template.schedule_kind == "explicit_time":
            if template.local_time is None:
                raise InvalidScheduleTime("explicit-time template has no local time")
            return template.local_time
        if template.schedule_label is None:
            return None
        return self._routine_times.for_bucket(template.schedule_label)

    @staticmethod
    def _ensure_intake_confirmation_source(
        conn: psycopg.Connection[dict[str, Any]],
    ) -> None:
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
                'Explicit user intake action',
                'vitaminbot:user-intake-action',
                '1',
                DATE '2026-09-20'
            )
            ON CONFLICT (source_id) DO NOTHING
            """,
            (_INTAKE_CONFIRMATION_SOURCE_ID,),
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
    def _complete_action(
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        action_key: str,
        result_ref: str,
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
    def _decrement_inventory_for_intake(
        conn: psycopg.Connection[dict[str, Any]],
        occurrence: OccurrenceRecord,
        intake_event_id: str,
    ) -> None:
        inventory = conn.execute(
            """
            SELECT remaining_units, revision, needs_reconciliation
            FROM supplement_inventory
            WHERE tracked_instance_id = %s
              AND consumption_unit_id = %s
            FOR UPDATE
            """,
            (occurrence.instance_id, occurrence.unit_id),
        ).fetchone()
        if inventory is None:
            return

        balance_before: Decimal = inventory["remaining_units"]
        needs_before = bool(inventory["needs_reconciliation"])
        if balance_before >= occurrence.quantity:
            balance_after = balance_before - occurrence.quantity
            needs_after = needs_before
        else:
            balance_after = Decimal("0")
            needs_after = True

        updated = conn.execute(
            """
            UPDATE supplement_inventory
            SET remaining_units = %s,
                needs_reconciliation = %s,
                revision = revision + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE tracked_instance_id = %s
              AND revision = %s
            RETURNING revision
            """,
            (
                balance_after,
                needs_after,
                occurrence.instance_id,
                inventory["revision"],
            ),
        ).fetchone()
        if updated is None:
            raise InvalidOccurrenceState("inventory changed during intake recording")

        conn.execute(
            """
            INSERT INTO inventory_events (
                event_id,
                tracked_instance_id,
                consumption_unit_id,
                event_kind,
                quantity_units,
                balance_before,
                balance_after,
                needs_reconciliation_before,
                inventory_revision_after,
                intake_event_id,
                balance_applied
            )
            VALUES (%s, %s, %s, 'intake_decrement', %s, %s, %s, %s, %s, %s, TRUE)
            """,
            (
                f"inventory:event:{uuid4().hex}",
                occurrence.instance_id,
                occurrence.unit_id,
                occurrence.quantity,
                balance_before,
                balance_after,
                needs_before,
                int(updated["revision"]),
                intake_event_id,
            ),
        )

    @staticmethod
    def _correct_inventory_for_intake(
        conn: psycopg.Connection[dict[str, Any]],
        intake_event_id: str,
    ) -> None:
        event = conn.execute(
            """
            SELECT
                event_id,
                tracked_instance_id,
                consumption_unit_id,
                quantity_units,
                balance_before,
                inventory_revision_after,
                needs_reconciliation_before
            FROM inventory_events
            WHERE intake_event_id = %s
              AND event_kind = 'intake_decrement'
            FOR UPDATE
            """,
            (intake_event_id,),
        ).fetchone()
        if event is None:
            return

        inventory = conn.execute(
            """
            SELECT remaining_units, revision, consumption_unit_id, needs_reconciliation
            FROM supplement_inventory
            WHERE tracked_instance_id = %s
            FOR UPDATE
            """,
            (event["tracked_instance_id"],),
        ).fetchone()
        if inventory is None:
            return

        current_balance: Decimal = inventory["remaining_units"]
        current_revision = int(inventory["revision"])
        exact_reversal = (
            current_revision == int(event["inventory_revision_after"])
            and inventory["consumption_unit_id"] == event["consumption_unit_id"]
            and event["balance_before"] is not None
        )

        if exact_reversal:
            balance_after = event["balance_before"]
            needs_after = bool(event["needs_reconciliation_before"])
            balance_applied = True
        else:
            balance_after = current_balance
            needs_after = True
            balance_applied = False

        updated = conn.execute(
            """
            UPDATE supplement_inventory
            SET remaining_units = %s,
                needs_reconciliation = %s,
                revision = revision + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE tracked_instance_id = %s
              AND revision = %s
            RETURNING revision
            """,
            (
                balance_after,
                needs_after,
                event["tracked_instance_id"],
                current_revision,
            ),
        ).fetchone()
        if updated is None:
            raise InvalidOccurrenceState("inventory changed during intake correction")

        conn.execute(
            """
            INSERT INTO inventory_events (
                event_id,
                tracked_instance_id,
                consumption_unit_id,
                event_kind,
                quantity_units,
                balance_before,
                balance_after,
                needs_reconciliation_before,
                inventory_revision_after,
                intake_event_id,
                related_event_id,
                balance_applied
            )
            VALUES (
                %s, %s, %s, 'intake_correction', %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                f"inventory:event:{uuid4().hex}",
                event["tracked_instance_id"],
                event["consumption_unit_id"],
                event["quantity_units"],
                current_balance,
                balance_after,
                bool(inventory["needs_reconciliation"]),
                int(updated["revision"]),
                intake_event_id,
                event["event_id"],
                balance_applied,
            ),
        )

    @staticmethod
    def _cancel_claimed_deliveries(
        conn: psycopg.Connection[dict[str, Any]],
        occurrence_id: str,
        now: datetime,
    ) -> None:
        conn.execute(
            """
            UPDATE reminder_delivery_attempts
            SET status = 'cancelled',
                completed_at = %s
            WHERE occurrence_id = %s
              AND status = 'claimed'
            """,
            (now, occurrence_id),
        )

    def _locked_template(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        instance_id: str,
    ) -> ScheduleTemplate:
        row = conn.execute(
            """
            SELECT
                us.instance_id,
                us.container_label,
                head.plan_id,
                head.plan_version,
                head.revision AS plan_revision,
                event.event_id,
                event.consumption_unit_id,
                unit.label_name AS unit_label,
                event.consumption_units,
                event.schedule_kind,
                event.schedule_label,
                event.local_time
            FROM intake_plan_heads AS head
            JOIN user_supplements AS us
              ON us.instance_id = head.tracked_instance_id
            JOIN planned_intake_events AS event
              ON event.plan_id = head.plan_id
             AND event.plan_version = head.plan_version
            JOIN consumption_units AS unit
              ON unit.formulation_id = event.formulation_id
             AND unit.unit_id = event.consumption_unit_id
            WHERE us.user_id = %s
              AND us.instance_id = %s
              AND us.lifecycle_status = 'active'
            ORDER BY event.event_id
            LIMIT 1
            FOR UPDATE OF head
            """,
            (user_id, instance_id),
        ).fetchone()
        if row is None:
            raise ScheduleRecordNotFound("current plan not found")
        return self._template_from_row(row)

    def _locked_occurrence(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        occurrence_id: str,
    ) -> OccurrenceRecord:
        row = conn.execute(
            self._occurrence_query()
            + " AND occurrence.occurrence_id = %s FOR UPDATE OF occurrence",
            (user_id, occurrence_id),
        ).fetchone()
        if row is None:
            raise ScheduleRecordNotFound("occurrence not found")
        return self._occurrence_from_row(row)

    def _occurrence_in_connection(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        user_id: UUID,
        occurrence_id: str,
    ) -> OccurrenceRecord:
        row = conn.execute(
            self._occurrence_query() + " AND occurrence.occurrence_id = %s",
            (user_id, occurrence_id),
        ).fetchone()
        if row is None:
            raise ScheduleRecordNotFound("occurrence not found")
        return self._occurrence_from_row(row)

    @staticmethod
    def _template_from_row(row: dict[str, Any]) -> ScheduleTemplate:
        return ScheduleTemplate(
            instance_id=str(row["instance_id"]),
            name=str(row["container_label"]),
            plan_id=str(row["plan_id"]),
            plan_version=str(row["plan_version"]),
            plan_revision=int(row["plan_revision"]),
            event_id=str(row["event_id"]),
            unit_id=str(row["consumption_unit_id"]),
            unit_label=str(row["unit_label"]),
            quantity=row["consumption_units"],
            schedule_kind=str(row["schedule_kind"]),
            schedule_label=None if row["schedule_label"] is None else str(row["schedule_label"]),
            local_time=row["local_time"],
        )

    @staticmethod
    def _occurrence_from_row(row: dict[str, Any]) -> OccurrenceRecord:
        return OccurrenceRecord(
            occurrence_id=str(row["occurrence_id"]),
            instance_id=str(row["tracked_instance_id"]),
            name=str(row["container_label"]),
            unit_id=str(row["consumption_unit_id"]),
            unit_label=str(row["unit_label"]),
            quantity=row["consumption_units"],
            schedule_kind=str(row["schedule_kind"]),
            schedule_label=str(row["schedule_label"]),
            timezone=str(row["timezone"]),
            local_date=row["local_date"],
            scheduled_local_time=row["scheduled_local_time"],
            scheduled_at=row["scheduled_at"],
            due_at=row["due_at"],
            state=str(row["state"]),
            later_count=int(row["later_count"]),
            revision=int(row["revision"]),
        )

    @staticmethod
    def _occurrence_query() -> str:
        return """
            SELECT
                occurrence.occurrence_id,
                occurrence.tracked_instance_id,
                us.container_label,
                occurrence.consumption_unit_id,
                unit.label_name AS unit_label,
                occurrence.consumption_units,
                occurrence.schedule_kind,
                occurrence.schedule_label,
                occurrence.timezone,
                occurrence.local_date,
                occurrence.scheduled_local_time,
                occurrence.scheduled_at,
                occurrence.due_at,
                occurrence.state,
                occurrence.later_count,
                occurrence.revision
            FROM reminder_occurrences AS occurrence
            JOIN user_supplements AS us
              ON us.instance_id = occurrence.tracked_instance_id
             AND us.user_id = occurrence.user_id
            JOIN consumption_units AS unit
              ON unit.formulation_id = occurrence.formulation_id
             AND unit.unit_id = occurrence.consumption_unit_id
            WHERE occurrence.user_id = %s
              AND occurrence.cancelled_at IS NULL
        """


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)
