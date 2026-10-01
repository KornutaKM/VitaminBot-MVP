from __future__ import annotations

from decimal import Decimal

from vitaminbot.application.intake import (
    HistoryActionResult,
    HistoryActionStatus,
    HistoryEntryView,
    HistoryStatus,
    HistoryView,
)
from vitaminbot.application.supplements import Button, Screen

_ACTION_LABELS = {
    "taken": "принято",
    "skip": "пропущено",
    "later": "отложено",
    "correction": "исправление",
}


def render_history(view: HistoryView, *, notice: str | None = None) -> Screen:
    if view.status is HistoryStatus.EMPTY:
        text = "История\n\nОтметок пока нет."
        if notice:
            text = f"{notice}\n\n{text}"
        return Screen(
            text=text,
            rows=(
                (Button("Сегодня", "k120today"),),
                (Button("Статистика", "k120a"),),
            ),
        )

    lines = ["История"]
    if notice:
        lines.extend(["", notice])
    lines.append("")
    rows: list[tuple[Button, ...]] = []

    for entry in view.entries:
        status = _entry_status(entry)
        lines.append(
            f"• {entry.name}: {_display_quantity(entry.quantity)} "
            f"{_display_unit(entry.unit_label, entry.quantity)} — {status}"
        )
        if entry.correctable:
            rows.append(
                (
                    Button(
                        f"Исправить · {entry.name[:22]}",
                        f"k120q:{entry.occurrence_id}:{entry.occurrence_revision}",
                    ),
                )
            )

    lines.extend(
        [
            "",
            "История — аудит ваших отметок. "
            "Доставка напоминания не доказывает, что приём состоялся.",
        ]
    )
    rows.extend(
        [
            (Button("Сегодня", "k120today"), Button("Статистика", "k120a")),
            (Button("План", "k120p"),),
        ]
    )
    return Screen(text="\n".join(lines), rows=tuple(rows))


def render_history_action_result(result: HistoryActionResult) -> Screen:
    if result.status is HistoryActionStatus.PREVIEW and result.preview is not None:
        preview = result.preview
        current = "принято" if preview.state == "taken" else "пропущено"
        return Screen(
            text=(
                f"Исправить запись — {preview.name}\n\n"
                f"Текущая отметка: {current}.\n\n"
                "После подтверждения эта отметка останется в истории как ошибочная, "
                "а событие вернётся в состояние «нужна проверка». "
                "История не удаляется молча."
            ),
            rows=(
                (
                    Button(
                        "Подтвердить исправление",
                        f"k120c:{preview.occurrence_id}:{preview.expected_revision}",
                    ),
                ),
                (Button("Назад к истории", "k120h"),),
            ),
        )

    if result.status is HistoryActionStatus.APPLIED and result.view is not None:
        return render_history(result.view, notice="Исправление сохранено.")

    if result.status is HistoryActionStatus.STALE:
        return Screen(
            text=(
                "Эта запись уже изменилась или была исправлена. Повторное исправление не записано."
            ),
            rows=((Button("Открыть историю", "k120h"),),),
        )

    return Screen(
        text="Не удалось распознать исправление. История не изменена.",
        rows=((Button("Открыть историю", "k120h"),),),
    )


def _entry_status(entry: HistoryEntryView) -> str:
    if entry.entered_in_error:
        original = _ACTION_LABELS.get(entry.action_kind, entry.action_kind)
        return f"{original} · ошибочная запись"
    return _ACTION_LABELS.get(entry.action_kind, entry.action_kind)


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
