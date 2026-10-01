from __future__ import annotations

from datetime import time
from decimal import Decimal

from vitaminbot.application.intake import TodayOccurrenceState, TodayStatus, TodayView
from vitaminbot.application.supplements import Button, Screen

_WEEKDAYS_RU = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)
_MONTHS_RU = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def render_today(view: TodayView) -> Screen:
    if view.status is TodayStatus.MISSING_TIMEZONE:
        return Screen(
            text=(
                "Сегодня\n\n"
                "Чтобы разложить план по местному дню, нужен ваш часовой пояс. "
                "Это техническая настройка расписания."
            ),
            rows=((Button("Открыть профиль", "pf"),),),
        )
    if view.status is TodayStatus.AMBIGUOUS_LOCAL_TIME:
        return Screen(
            text=(
                "Сегодня\n\n"
                "Одно из местных времён попало на переход часов. "
                "VitaminBot ничего не сдвинул автоматически — проверьте план."
            ),
            rows=((Button("Открыть план", "k120p"),),),
        )
    if view.status is TodayStatus.INVALID_SCHEDULE:
        return Screen(
            text=(
                "Сегодня\n\n"
                "Расписание нельзя безопасно интерпретировать. "
                "VitaminBot не стал угадывать время приёма."
            ),
            rows=((Button("Открыть план", "k120p"),),),
        )

    header = _header(view)
    if not view.occurrences:
        return Screen(
            text=f"{header}\n\nНа сегодня ничего не запланировано.",
            rows=((Button("План", "k120p"), Button("История", "k120h")),),
        )

    lines = [header, ""]
    rows: list[tuple[Button, ...]] = []
    for occurrence in view.occurrences:
        marker, suffix = _state_label(occurrence.state)
        title = f"{marker} {occurrence.name}"
        if suffix:
            title = f"{title} · {suffix}"
        lines.append(title)
        schedule = _schedule_label(
            occurrence.schedule_kind,
            occurrence.schedule_label,
            occurrence.scheduled_local_time,
        )
        lines.append(
            f"  {_display_quantity(occurrence.quantity)} "
            f"{_display_unit(occurrence.unit_label, occurrence.quantity)} · {schedule}"
        )
        lines.append("")

        actions: list[Button] = []
        if occurrence.can_take:
            actions.append(
                Button(
                    "Принял(а)",
                    f"k120t:{occurrence.occurrence_id}:{occurrence.revision}",
                )
            )
        if occurrence.can_later:
            actions.append(
                Button(
                    "Позже",
                    f"k120l:{occurrence.occurrence_id}:{occurrence.revision}",
                )
            )
        if occurrence.can_skip:
            actions.append(
                Button(
                    "Пропустить",
                    f"k120s:{occurrence.occurrence_id}:{occurrence.revision}",
                )
            )
        if actions:
            rows.append(tuple(actions))
        if occurrence.can_explain:
            rows.append(
                (
                    Button(
                        f"Почему? · {occurrence.name[:20]}",
                        f"k120w:{occurrence.occurrence_id}:{occurrence.revision}",
                    ),
                )
            )

    if lines[-1] == "":
        lines.pop()
    rows.append((Button("План", "k120p"), Button("История", "k120h")))
    return Screen(text="\n".join(lines), rows=tuple(rows))


def _header(view: TodayView) -> str:
    if view.local_date is None:
        return "Сегодня"
    value = view.local_date
    return (
        f"Сегодня · {_WEEKDAYS_RU[value.weekday()]}, "
        f"{value.day} {_MONTHS_RU[value.month]}"
    )


def _state_label(state: TodayOccurrenceState) -> tuple[str, str]:
    if state is TodayOccurrenceState.TAKEN:
        return "✓", ""
    if state is TodayOccurrenceState.SKIPPED:
        return "—", "пропущено"
    if state is TodayOccurrenceState.NEEDS_REVIEW:
        return "!", "нужна проверка"
    return "○", ""


def _schedule_label(schedule_kind: str, schedule_label: str, value: time) -> str:
    if schedule_kind == "explicit_time":
        return value.isoformat(timespec="minutes")
    labels = {
        "morning": "утро",
        "day": "день",
        "evening": "вечер",
    }
    return labels.get(schedule_label, schedule_label)


def _display_quantity(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        text = str(normalized.quantize(Decimal("1")))
    else:
        text = format(normalized, "f")
    return text.replace(".", ",")


def _display_unit(unit_label: str, quantity: Decimal) -> str:
    if quantity != quantity.to_integral():
        fractional = {
            "capsule": "капсулы",
            "tablet": "таблетки",
            "softgel": "мягкой капсулы",
            "scoop": "мерной ложки",
            "drop": "капли",
        }
        return fractional.get(unit_label, unit_label)

    value = abs(int(quantity))
    last_two = value % 100
    last = value % 10
    one = last == 1 and last_two != 11
    few = last in {2, 3, 4} and last_two not in {12, 13, 14}

    forms = {
        "capsule": ("капсула", "капсулы", "капсул"),
        "tablet": ("таблетка", "таблетки", "таблеток"),
        "softgel": ("мягкая капсула", "мягкие капсулы", "мягких капсул"),
        "scoop": ("мерная ложка", "мерные ложки", "мерных ложек"),
        "drop": ("капля", "капли", "капель"),
    }
    selected = forms.get(unit_label)
    if selected is None:
        return unit_label
    if one:
        return selected[0]
    if few:
        return selected[1]
    return selected[2]
