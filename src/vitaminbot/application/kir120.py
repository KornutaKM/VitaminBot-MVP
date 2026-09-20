from __future__ import annotations

import base64
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from vitaminbot.application.kir116 import Button, Screen
from vitaminbot.persistence.kir120 import (
    AmbiguousLocalTime,
    InvalidOccurrenceState,
    InvalidScheduleTime,
    KIR120Store,
    MissingTimezone,
    NonexistentLocalTime,
    OccurrenceRecord,
    ScheduleRecordNotFound,
    ScheduleTemplate,
    StaleOccurrence,
)

_BUCKET_CODES = {
    "m": "morning",
    "d": "day",
    "e": "evening",
}


class KIR120Controller:
    """Transport-independent Today/Plan/History state machine."""

    def __init__(
        self,
        store: KIR120Store,
        *,
        later_delay: timedelta = timedelta(minutes=30),
    ) -> None:
        if later_delay <= timedelta(0):
            raise ValueError("later_delay must be positive")
        self._store = store
        self._later_delay = later_delay

    def has_pending_text(self, telegram_user_id: int) -> bool:
        user_id = self._store.ensure_user(telegram_user_id)
        return self._store.schedule_session(user_id) is not None

    def cancel(self, telegram_user_id: int) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        self._store.cancel_schedule_edit(user_id)
        return Screen(
            text=(
                "Pending Plan input cancelled. "
                "The recurring plan and Today occurrences were unchanged."
            ),
            rows=((Button("Open Plan", "k120p"),),),
        )

    def today(self, telegram_user_id: int, *, now: datetime | None = None) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        current = _utc_now(now)
        try:
            occurrences = self._store.today(user_id, current)
        except MissingTimezone:
            return Screen(
                text=(
                    "Today needs your timezone before reminders can be placed on a local day.\n\n"
                    "Set a timezone in Profile. This is a technical scheduling field, "
                    "not a medical applicability field."
                ),
                rows=((Button("Open profile", "pf"),),),
            )
        except (AmbiguousLocalTime, NonexistentLocalTime):
            return Screen(
                text=(
                    "Today could not resolve one of your local schedule times across a DST "
                    "transition. Nothing was moved automatically. Review the Plan and choose "
                    "an unambiguous local time."
                ),
                rows=((Button("Open Plan", "k120p"),),),
            )
        except InvalidScheduleTime:
            return Screen(
                text=(
                    "Today could not resolve the stored schedule safely. "
                    "No reminder occurrence was guessed."
                ),
                rows=((Button("Open Plan", "k120p"),),),
            )
        return self._today_screen(occurrences)

    def plan(self, telegram_user_id: int, *, prefix: str = "") -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        templates = self._store.list_templates(user_id)
        if not templates:
            return Screen(
                text=(
                    f"{prefix}Plan\n\nNo confirmed supplement plan exists yet. "
                    "Add or edit a supplement plan first."
                ),
                rows=((Button("My supplements", "ls"),),),
            )

        lines = [f"{prefix}Plan", "", "These are your recurring routine preferences."]
        rows: list[tuple[Button, ...]] = []
        for template in templates:
            lines.append(
                f"• {template.name}: {_display_decimal(template.quantity)} "
                f"{template.unit_label} — {self._template_schedule(template)}"
            )
            token = _encode_instance(template.instance_id)
            rows.append(
                (
                    Button("Morning", f"k120b:{token}:{template.plan_revision}:m"),
                    Button("Day", f"k120b:{token}:{template.plan_revision}:d"),
                    Button("Evening", f"k120b:{token}:{template.plan_revision}:e"),
                )
            )
            rows.append(
                (
                    Button(
                        f"Exact time for {template.name[:20]}",
                        f"k120e:{token}:{template.plan_revision}",
                    ),
                )
            )
        lines.extend(
            [
                "",
                "Morning / Day / Evening are routine buckets, not biological timing claims.",
                "Evidence-backed planning notes are shown only when a governed rule is attached.",
            ]
        )
        return Screen(text="\n".join(lines), rows=tuple(rows))

    def history(self, telegram_user_id: int) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        entries = self._store.history(user_id)
        if not entries:
            return Screen(
                text="History\n\nNo Taken / Skip / Later actions have been recorded yet.",
                rows=((Button("Today", "k120today"),),),
            )

        lines = ["History", ""]
        rows: list[tuple[Button, ...]] = []
        for entry in entries:
            status = "entered in error" if entry.entered_in_error else entry.action_kind
            lines.append(
                f"• {entry.name}: {_display_decimal(entry.quantity)} "
                f"{entry.unit_label} — {status}"
            )
            if entry.correctable:
                rows.append(
                    (
                        Button(
                            f"Correct {entry.name[:24]}",
                            f"k120c:{entry.occurrence_id}:{entry.occurrence_revision}",
                        ),
                    )
                )
        lines.extend(
            [
                "",
                "History is an audit/correction view. Reminder delivery is not intake proof.",
            ]
        )
        rows.append((Button("Today", "k120today"),))
        return Screen(text="\n".join(lines), rows=tuple(rows))

    def text(
        self,
        telegram_user_id: int,
        value: str,
        *,
        action_key: str,
    ) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        if self._store.schedule_session(user_id) is None:
            return Screen(text="No Plan field is waiting for text input.")
        try:
            local_time = _parse_clock(value)
            self._store.save_explicit_time(user_id, action_key, local_time)
        except ValueError as exc:
            return Screen(text=str(exc))
        except (InvalidOccurrenceState, StaleOccurrence, ScheduleRecordNotFound):
            return Screen(
                text="This Plan edit is out of date. Open the current Plan and try again.",
                rows=((Button("Open Plan", "k120p"),),),
            )
        return self.plan(
            telegram_user_id,
            prefix="Exact local time saved. The planned product-unit amount was not changed.\n\n",
        )

    def callback(
        self,
        telegram_user_id: int,
        data: str,
        *,
        action_key: str,
        now: datetime | None = None,
    ) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        current = _utc_now(now)
        parts = data.split(":")
        action = parts[0]
        try:
            if action == "k120today":
                return self.today(telegram_user_id, now=current)
            if action == "k120p":
                return self.plan(telegram_user_id)
            if action == "k120h":
                return self.history(telegram_user_id)
            if action == "k120b":
                instance_id = _decode_instance(parts[1])
                expected_revision = int(parts[2])
                bucket = _BUCKET_CODES.get(parts[3])
                if bucket is None:
                    raise ValueError("Unsupported routine bucket.")
                self._store.set_schedule_bucket(
                    user_id,
                    action_key,
                    instance_id,
                    expected_revision,
                    bucket,
                )
                return self.plan(
                    telegram_user_id,
                    prefix=(
                        "Routine preference updated. The planned product-unit amount "
                        "was not changed.\n\n"
                    ),
                )
            if action == "k120e":
                instance_id = _decode_instance(parts[1])
                expected_revision = int(parts[2])
                self._store.begin_explicit_time_edit(
                    user_id,
                    action_key,
                    instance_id,
                    expected_revision,
                )
                return Screen(
                    text=(
                        "Exact local time\n\nSend a local time as HH:MM, for example 08:30. "
                        "If that clock time is ambiguous or nonexistent on a DST transition day, "
                        "VitaminBot will fail closed rather than silently shift it."
                    )
                )
            if action in {"k120t", "k120s", "k120l", "k120w", "k120c"}:
                occurrence_id = parts[1]
                expected_revision = int(parts[2])
                if action == "k120w":
                    occurrence = self._store.occurrence(user_id, occurrence_id)
                    return self._why_screen(occurrence)
                if action == "k120t":
                    self._store.take(
                        user_id,
                        occurrence_id,
                        expected_revision,
                        action_key,
                        current,
                    )
                    return self.today(telegram_user_id, now=current)
                if action == "k120s":
                    self._store.skip(
                        user_id,
                        occurrence_id,
                        expected_revision,
                        action_key,
                        current,
                    )
                    return self.today(telegram_user_id, now=current)
                if action == "k120l":
                    self._store.later(
                        user_id,
                        occurrence_id,
                        expected_revision,
                        action_key,
                        current,
                        current + self._later_delay,
                    )
                    return self.today(telegram_user_id, now=current)
                self._store.correct_latest(
                    user_id,
                    occurrence_id,
                    expected_revision,
                    action_key,
                    current,
                )
                return self.history(telegram_user_id)
        except ValueError as exc:
            return Screen(text=str(exc))
        except (StaleOccurrence, InvalidOccurrenceState, ScheduleRecordNotFound):
            return Screen(
                text=(
                    "This action is out of date or no longer valid. "
                    "No duplicate intake action was recorded."
                ),
                rows=(
                    (Button("Today", "k120today"),),
                    (Button("History", "k120h"),),
                ),
            )

        return Screen(text="Unsupported Today/Plan action.")

    @staticmethod
    def _template_schedule(template: ScheduleTemplate) -> str:
        if template.schedule_kind == "explicit_time" and template.local_time is not None:
            return template.local_time.isoformat(timespec="minutes")
        if template.schedule_label is None:
            return "not scheduled"
        return template.schedule_label.title()

    @staticmethod
    def _today_screen(occurrences: tuple[OccurrenceRecord, ...]) -> Screen:
        if not occurrences:
            return Screen(
                text=(
                    "Today\n\nNo scheduled occurrences for this local day. "
                    "Plan is the recurring-template view."
                ),
                rows=((Button("Open Plan", "k120p"),),),
            )

        lines = ["Today", ""]
        rows: list[tuple[Button, ...]] = []
        for occurrence in occurrences:
            schedule = (
                occurrence.scheduled_local_time.isoformat(timespec="minutes")
                if occurrence.schedule_kind == "explicit_time"
                else occurrence.schedule_label.title()
            )
            lines.append(
                f"• {schedule} — {occurrence.name}: "
                f"{_display_decimal(occurrence.quantity)} {occurrence.unit_label} "
                f"[{occurrence.state}]"
            )
            action_buttons = [
                Button(
                    "Taken",
                    f"k120t:{occurrence.occurrence_id}:{occurrence.revision}",
                )
            ]
            if occurrence.state == "pending" and occurrence.later_count == 0:
                action_buttons.append(
                    Button(
                        "Later",
                        f"k120l:{occurrence.occurrence_id}:{occurrence.revision}",
                    )
                )
            action_buttons.append(
                Button(
                    "Skip",
                    f"k120s:{occurrence.occurrence_id}:{occurrence.revision}",
                )
            )
            if occurrence.state in {"pending", "needs_review"}:
                rows.append(tuple(action_buttons))
            rows.append(
                (
                    Button(
                        "Why?",
                        f"k120w:{occurrence.occurrence_id}:{occurrence.revision}",
                    ),
                )
            )
        lines.extend(
            [
                "",
                "Today shows generated occurrences. Plan edits affect the recurring template; "
                "existing Today occurrences keep their original quantity/unit snapshot.",
            ]
        )
        rows.extend(
            [
                (Button("Plan", "k120p"), Button("History", "k120h")),
            ]
        )
        return Screen(text="\n".join(lines), rows=tuple(rows))

    @staticmethod
    def _why_screen(occurrence: OccurrenceRecord) -> Screen:
        return Screen(
            text=(
                f"Why this time? — {occurrence.name}\n\n"
                "Timing source: Your preference. "
                "No evidence-backed planning note is attached to this occurrence. "
                "VitaminBot is not inferring a biological Morning/Day/Evening advantage."
            ),
            rows=((Button("Back to Today", "k120today"),),),
        )


def _parse_clock(value: str) -> time:
    normalized = value.strip()
    try:
        parsed = time.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Send a local time as HH:MM, for example 08:30.") from exc
    if parsed.tzinfo is not None or parsed.second != 0 or parsed.microsecond != 0:
        raise ValueError("Send a local time as HH:MM without seconds or timezone.")
    return parsed


def _encode_instance(instance_id: str) -> str:
    encoded = base64.urlsafe_b64encode(instance_id.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_instance(token: str) -> str:
    padding = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid Plan reference.") from exc
    if not raw or len(raw) > 120:
        raise ValueError("Invalid Plan reference.")
    return raw


def _display_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _utc_now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(UTC)
