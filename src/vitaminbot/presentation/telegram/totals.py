from __future__ import annotations

from decimal import Decimal

from vitaminbot.application.nutrition import (
    RegimenTotalsStatus,
    RegimenTotalsView,
)
from vitaminbot.application.supplements import Button, Screen
from vitaminbot.domain import Unit

_UNIT_LABELS = {
    Unit.GRAM: "г",
    Unit.MILLIGRAM: "мг",
    Unit.MICROGRAM: "мкг",
}


def render_regimen_totals(view: RegimenTotalsView) -> Screen:
    if view.status is RegimenTotalsStatus.NO_SUPPLEMENTS:
        return Screen(
            text=(
                "Итоги режима\n\n"
                "Добавок пока нет. Итог появляется только из подтверждённого состава "
                "и сохранённого плана."
            ),
            rows=((Button("Добавить добавку", "a"),),),
        )

    if view.status is RegimenTotalsStatus.NO_AGGREGATES:
        return Screen(
            text=(
                "Итоги режима\n\n"
                "Пока нечего суммировать. Нужны подтверждённый состав и сохранённый "
                "план с количеством единиц.\n\n"
                "Неизвестное значение не считается нулём."
            ),
            rows=(
                (Button("Добавить состав", "k122comp"),),
                (Button("План", "k120p"), Button("Сегодня", "k120today")),
            ),
        )

    lines = [
        "Итоги режима",
        "",
        "Только подтверждённый состав × текущий план.",
        "Неизвестное значение не считается нулём.",
    ]
    rows: list[tuple[Button, ...]] = [
        (Button("Проверка", "k122safe"),),
        (Button("Почему так распределено?", "k122rules"),),
    ]

    for nutrient in view.nutrients:
        lines.append("")
        if nutrient.is_complete and nutrient.total is not None and nutrient.unit is not None:
            lines.append(
                f"{nutrient.name} · {_decimal(nutrient.total)} {_unit_label(nutrient.unit)}/день"
            )
        else:
            lines.append(f"{nutrient.name} · итог неполный")

        if nutrient.contributors:
            lines.append("Вклад:")
            for contributor in nutrient.contributors:
                lines.append(
                    f"• {contributor.name} — {_decimal(contributor.value)} "
                    f"{_unit_label(contributor.unit)}"
                )

        if (
            nutrient.unresolved_contributor_count
            or nutrient.issue_codes
            or not nutrient.is_complete
        ):
            lines.append("Нужно уточнить: полный итог не показываю.")

        if nutrient.suppressed_exact_repeat_count:
            lines.append("Точный повтор одного и того же вклада не посчитан второй раз.")

        if nutrient.substance_key is not None:
            rows.append(
                (
                    Button(
                        f"О веществе · {nutrient.name}",
                        f"k146c:{nutrient.substance_key}",
                    ),
                )
            )

    if view.unresolved_contributor_count:
        lines.extend(
            [
                "",
                "Есть неподтверждённые или неоднозначные вклады. "
                "Они не превращены в ноль и не добавлены к полному итогу.",
            ]
        )

    rows.extend(
        [
            (Button("Сегодня", "k120today"), Button("План", "k120p")),
            (Button("Состав", "k122comp"),),
        ]
    )
    return Screen(text="\n".join(lines), rows=tuple(rows))


def _decimal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _unit_label(unit: Unit) -> str:
    return _UNIT_LABELS.get(unit, unit.value)
