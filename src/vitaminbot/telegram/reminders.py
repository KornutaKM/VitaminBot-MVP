from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

import psycopg
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from vitaminbot.observability import MetricsSink, NULL_METRICS
from vitaminbot.persistence.kir120 import DeliveryClaim, KIR120Store

_LOGGER = logging.getLogger(__name__)


class TelegramReminderRunner:
    """Restart-safe polling runner backed by durable KIR-120 reminder state."""

    def __init__(
        self,
        store: KIR120Store,
        *,
        poll_seconds: int = 30,
        metrics: MetricsSink = NULL_METRICS,
    ) -> None:
        if poll_seconds < 1:
            raise ValueError("poll_seconds must be positive")
        self._store = store
        self._poll_seconds = poll_seconds
        self._metrics = metrics

    async def run_once(self, bot: Bot, *, now: datetime | None = None) -> int:
        current = _utc_now(now)
        self._store.materialize_all(current)
        claims = self._store.claim_due_reminders(
            current,
            execution_key=f"telegram-reminder:{uuid4().hex}",
        )

        validated: list[DeliveryClaim] = []
        for claim in claims:
            current_claim = self._store.validate_claim(claim.delivery_id, current)
            if current_claim is not None:
                validated.append(current_claim)

        self._metrics.increment("reminders_due", len(validated))
        groups: dict[tuple[int, datetime], list[DeliveryClaim]] = defaultdict(list)
        for claim in validated:
            lag_seconds = max(0.0, (current - claim.due_at).total_seconds())
            self._metrics.observe("reminder_lag_seconds", lag_seconds)
            due_minute = claim.due_at.replace(second=0, microsecond=0)
            groups[(claim.telegram_user_id, due_minute)].append(claim)

        delivered = 0
        for (telegram_user_id, _), group in groups.items():
            final_group: list[DeliveryClaim] = []
            revalidation_time = datetime.now(UTC)
            for claim in group:
                current_claim = self._store.validate_claim(
                    claim.delivery_id,
                    revalidation_time,
                )
                if current_claim is not None:
                    final_group.append(current_claim)

            if not final_group:
                continue

            final_group.sort(key=lambda claim: (claim.name, claim.occurrence_id))
            text = _render_group(final_group)
            markup = _render_keyboard(final_group)
            try:
                message = await bot.send_message(
                    chat_id=telegram_user_id,
                    text=text,
                    reply_markup=markup,
                )
            except Exception as exc:
                failure_code = type(exc).__name__
                for claim in final_group:
                    self._store.mark_delivery_failed(
                        claim.delivery_id,
                        failure_code,
                        datetime.now(UTC),
                    )
                self._metrics.increment("reminders_failed", len(final_group))
                continue

            completed_at = datetime.now(UTC)
            for claim in final_group:
                self._store.mark_delivery_sent(
                    claim.delivery_id,
                    str(message.message_id),
                    completed_at,
                )
                delivered += 1
            self._metrics.increment("reminders_sent", len(final_group))
        return delivered

    async def run_forever(self, bot: Bot) -> None:
        while True:
            try:
                await self.run_once(bot)
            except asyncio.CancelledError:
                raise
            except psycopg.Error as exc:
                self._metrics.increment("db_transaction_errors")
                _LOGGER.warning("reminder database cycle failed: %s", type(exc).__name__)
            except Exception as exc:
                _LOGGER.warning("reminder cycle failed: %s", type(exc).__name__)
            await asyncio.sleep(self._poll_seconds)


def _render_group(group: list[DeliveryClaim]) -> str:
    heading = "Напоминание" if len(group) == 1 else f"Напоминания на одно время · {len(group)}"
    lines = [heading, ""]
    for claim in group:
        lines.append(
            f"• {claim.name}: {_display_quantity(claim.quantity)} "
            f"{_display_unit_label(claim.unit_label, claim.quantity)}"
        )
    lines.extend(
        [
            "",
            "Количество взято из вашего подтверждённого плана.",
            "Доставка напоминания не означает, что приём состоялся.",
            "Источник времени: ваша настройка режима; "
            "доказательное пояснение к планированию не привязано.",
        ]
    )
    return "\n".join(lines)


def _render_keyboard(group: list[DeliveryClaim]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for claim in group:
        action_row = [
            InlineKeyboardButton(
                f"Принял(а) · {claim.name[:18]}",
                callback_data=f"k120t:{claim.occurrence_id}:{claim.occurrence_revision}",
            )
        ]
        if claim.later_count == 0:
            action_row.append(
                InlineKeyboardButton(
                    "Позже",
                    callback_data=f"k120l:{claim.occurrence_id}:{claim.occurrence_revision}",
                )
            )
        action_row.append(
            InlineKeyboardButton(
                "Пропустить",
                callback_data=f"k120s:{claim.occurrence_id}:{claim.occurrence_revision}",
            )
        )
        rows.append(action_row)
        rows.append(
            [
                InlineKeyboardButton(
                    f"Почему? · {claim.name[:20]}",
                    callback_data=f"k120w:{claim.occurrence_id}:{claim.occurrence_revision}",
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


def _display_quantity(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered.replace(".", ",")


_RU_UNIT_FORMS: dict[str, tuple[str, str, str, str]] = {
    "capsule": ("капсула", "капсулы", "капсул", "капсулы"),
    "tablet": ("таблетка", "таблетки", "таблеток", "таблетки"),
    "softgel": (
        "мягкая капсула",
        "мягкие капсулы",
        "мягких капсул",
        "мягкой капсулы",
    ),
    "scoop": ("мерная ложка", "мерные ложки", "мерных ложек", "мерной ложки"),
    "drop": ("капля", "капли", "капель", "капли"),
}


def _display_unit_label(value: str, quantity: Decimal) -> str:
    forms = _RU_UNIT_FORMS.get(value)
    if forms is None:
        return value

    singular, few, many, fractional = forms
    if quantity != quantity.to_integral_value():
        return fractional

    integer = abs(int(quantity))
    last_two = integer % 100
    if 11 <= last_two <= 14:
        return many

    last = integer % 10
    if last == 1:
        return singular
    if 2 <= last <= 4:
        return few
    return many


def _utc_now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(UTC)
