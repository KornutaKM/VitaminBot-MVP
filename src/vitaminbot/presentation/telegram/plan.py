from __future__ import annotations

import base64
from decimal import Decimal

from vitaminbot.application.intake import (
    PlanActionResult,
    PlanActionStatus,
    PlanItemView,
    PlanStatus,
    PlanTimeEditView,
    PlanTimeInputError,
    PlanView,
)
from vitaminbot.application.supplements import Button, Screen


def render_plan(view: PlanView, *, notice: str | None = None) -> Screen:
    if view.status is PlanStatus.EMPTY:
        text = (
            "План\n\n"
            "Подтверждённого режима пока нет. Добавьте добавку и сохраните "
            "количество единиц для вашего режима."
        )
        if notice:
            text = f"{notice}\n\n{text}"
        return Screen(
            text=text,
            rows=((Button("Мои добавки", "ls"), Button("Добавить", "a")),),
        )

    lines = ["План"]
    if notice:
        lines.extend(["", notice])
    lines.extend(
        [
            "",
            "Это ваши повторяющиеся настройки режима, а не медицинская рекомендация по времени.",
        ]
    )
    rows: list[tuple[Button, ...]] = []

    for item in view.items:
        lines.extend(
            [
                "",
                item.name,
                f"{_display_quantity(item.quantity)} "
                f"{_display_unit(item.unit_label, item.quantity)} · {_schedule_text(item)}",
            ]
        )

        token = _encode_instance(item.instance_id)
        rows.append(
            (
                Button(
                    _bucket_label("Утро", item, "morning"),
                    f"k120b:{token}:{item.plan_revision}:m",
                ),
                Button(
                    _bucket_label("День", item, "day"),
                    f"k120b:{token}:{item.plan_revision}:d",
                ),
                Button(
                    _bucket_label("Вечер", item, "evening"),
                    f"k120b:{token}:{item.plan_revision}:e",
                ),
            )
        )
        exact_label = (
            f"✓ Точное время · {item.local_time.isoformat(timespec='minutes')}"
            if item.schedule_kind == "explicit_time" and item.local_time is not None
            else "Точное время"
        )
        rows.append(
            (
                Button(
                    exact_label,
                    f"k120e:{token}:{item.plan_revision}",
                ),
            )
        )

    lines.extend(
        [
            "",
            "Утро / день / вечер — организационные метки. "
            "VitaminBot не выводит из них биологическое преимущество времени суток.",
        ]
    )
    rows.extend(
        [
            (Button("Сегодня", "k120today"), Button("Итоги", "k122tot")),
            (Button("Мои добавки", "ls"),),
        ]
    )
    return Screen(text="\n".join(lines), rows=tuple(rows))


def render_plan_action_result(result: PlanActionResult) -> Screen:
    if result.status is PlanActionStatus.APPLIED and result.view is not None:
        return render_plan(result.view, notice="Режим обновлён.")
    if result.status is PlanActionStatus.CANCELLED and result.view is not None:
        return render_plan(result.view, notice="Изменение точного времени отменено.")
    if result.status is PlanActionStatus.INPUT_REQUIRED and result.edit is not None:
        return _render_time_edit(result.edit)
    if result.status is PlanActionStatus.STALE:
        return Screen(
            text=(
                "Этот план уже изменился. Старое действие не применено. Откройте актуальный план."
            ),
            rows=((Button("Открыть план", "k120p"),),),
        )
    return Screen(
        text="Не удалось распознать изменение плана. План не изменён.",
        rows=((Button("Открыть план", "k120p"),),),
    )


def _render_time_edit(edit: PlanTimeEditView) -> Screen:
    lines = [f"Точное время · {edit.name}", ""]
    if edit.error is PlanTimeInputError.INVALID_FORMAT:
        lines.extend(
            [
                "Не удалось распознать время.",
                "",
            ]
        )
    lines.extend(
        [
            "Отправьте местное время в формате HH:MM, например 08:30.",
            "Если это время неоднозначно или не существует в день перехода часов, "
            "VitaminBot не будет молча сдвигать его.",
        ]
    )
    return Screen(
        text="\n".join(lines),
        rows=((Button("Отмена", "k120pc"),),),
    )


def _bucket_label(label: str, item: PlanItemView, bucket: str) -> str:
    if item.schedule_kind == "routine_bucket" and item.schedule_label == bucket:
        return f"✓ {label}"
    return label


def _schedule_text(item: PlanItemView) -> str:
    if item.schedule_kind == "explicit_time" and item.local_time is not None:
        return item.local_time.isoformat(timespec="minutes")
    labels = {
        "morning": "утро",
        "day": "день",
        "evening": "вечер",
    }
    if item.schedule_label is None:
        return "не настроено"
    return labels.get(item.schedule_label, item.schedule_label)


def _encode_instance(instance_id: str) -> str:
    encoded = base64.urlsafe_b64encode(instance_id.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _display_quantity(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        rendered = str(normalized.quantize(Decimal("1")))
    else:
        rendered = format(normalized, "f")
    return rendered.replace(".", ",")


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
