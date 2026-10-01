from __future__ import annotations

import re
from decimal import Decimal

from vitaminbot.application.nutrition import CompositionStep, CompositionView
from vitaminbot.application.supplements import Button, Screen

_UNIT_NAMES = {
    "capsule": ("капсула", "капсулы", "капсул"),
    "tablet": ("таблетка", "таблетки", "таблеток"),
    "softgel": ("мягкая капсула", "мягкие капсулы", "мягких капсул"),
    "scoop": ("мерная ложка", "мерные ложки", "мерных ложек"),
    "drop": ("капля", "капли", "капель"),
}
_MASS_UNITS = {"g": "г", "mg": "мг", "ug": "мкг"}


def render_composition(view: CompositionView) -> Screen:
    if view.step is CompositionStep.EMPTY:
        return Screen(
            text=("Состав\n\nСначала добавьте добавку. Состав не будет придуман автоматически."),
            rows=((Button("Добавить добавку", "a"),),),
        )

    if view.step is CompositionStep.LIST:
        rows: list[tuple[Button, ...]] = []
        lines = [
            "Состав",
            "",
            "Выберите добавку. Сохраняются только значения, которые вы явно подтверждаете.",
        ]
        for supplement in view.supplements:
            status = (
                f"{supplement.confirmed_count} подтверждено"
                if supplement.confirmed_count
                else "состав не указан"
            )
            if supplement.serving_basis_type != "per_label_portion":
                status += " · нужна порция этикетки"
            lines.append(f"• {supplement.name} — {status}")
            rows.append(
                (
                    Button(
                        f"Состав · {supplement.name[:26]}",
                        f"k122c:{supplement.token}:{supplement.revision}",
                    ),
                )
            )
        rows.append((Button("Итоги", "k122tot"),))
        return Screen(text="\n".join(lines), rows=tuple(rows))

    if view.step is CompositionStep.SERVING_QUANTITY:
        unit = _unit_genitive(view.unit_label)
        error = (
            "\n\nНе удалось распознать число. Например: 1, 2 или 2,5." if view.input_error else ""
        )
        return Screen(
            text=(
                f"Порция с этикетки · {view.name or 'Добавка'}\n\n"
                f"Сколько {unit} указано в одной порции на этикетке?\n"
                "Отправьте положительное число. Это факт о порции продукта; "
                "он не меняет количество в вашем плане."
                f"{error}"
            ),
            rows=((Button("Отмена", "k122cancel"),),),
        )

    if view.step is CompositionStep.NUTRIENT:
        if not view.nutrients:
            return Screen(
                text=(
                    f"Состав · {view.name or 'Добавка'}\n\n"
                    "Все поддерживаемые позиции ручного списка уже подтверждены. "
                    "Дубликаты не создаются автоматически."
                ),
                rows=(
                    (Button("Итоги", "k122tot"),),
                    (Button("Назад к составу", "k122comp"),),
                ),
            )
        if view.supplement_token is None or view.supplement_revision is None:
            return _stale()
        return Screen(
            text=(
                f"Состав · {view.name or 'Добавка'}\n\n"
                "Какой нутриент указан на этикетке? "
                "Выберите только то, что действительно указано на продукте."
            ),
            rows=tuple(
                (
                    Button(
                        nutrient.name,
                        (
                            f"k122n:{view.supplement_token}:"
                            f"{view.supplement_revision}:{nutrient.substance_key}"
                        ),
                    ),
                )
                for nutrient in view.nutrients
            )
            + ((Button("Отмена", "k122cancel"),),),
        )

    if view.step is CompositionStep.AMOUNT:
        error = (
            "\n\nФормат не распознан. Примеры: 100 mg, 250 мкг, 1 g." if view.input_error else ""
        )
        return Screen(
            text=(
                f"{view.nutrient_name or 'Нутриент'}\n\n"
                "Введите количество на одну порцию с этикетки вместе с единицей массы. "
                "Значение не будет пересчитано в другую химическую форму и не является "
                "рекомендацией по дозе."
                f"{error}"
            ),
            rows=((Button("Отмена", "k122cancel"),),),
        )

    if view.step is CompositionStep.REVIEW:
        if view.value is None or view.unit is None or view.session_revision is None:
            return _stale()
        return Screen(
            text=(
                "Проверьте состав\n\n"
                f"{view.nutrient_name or 'Нутриент'}: {_decimal(view.value)} "
                f"{_mass_unit(view.unit)} на одну порцию этикетки.\n\n"
                "Подтверждение означает только «это совпадает с тем, что я ввёл». "
                "Оно не означает «безопасно», «подходит» или «рекомендовано»."
            ),
            rows=(
                (Button("Подтвердить", f"k122ok:{view.session_revision}"),),
                (Button("Отмена / ввести заново", "k122cancel"),),
            ),
        )

    if view.step is CompositionStep.COMPLETE:
        amount = ""
        if view.value is not None and view.unit is not None:
            amount = f": {_decimal(view.value)} {_mass_unit(view.unit)}"
        rows: list[tuple[Button, ...]] = [
            (Button("Добавить ещё строку", "k122comp"),),
            (Button("Итоги", "k122tot"), Button("Сегодня", "k120today")),
        ]
        manual_token = _manual_token(view.instance_id)
        if manual_token is not None and view.supplement_revision is not None:
            rows.insert(
                1,
                (
                    Button(
                        "Открыть добавку",
                        f"o:{manual_token}:{view.supplement_revision}",
                    ),
                ),
            )
        return Screen(
            text=(
                "Состав подтверждён\n\n"
                f"{view.nutrient_name or 'Нутриент'}{amount} на порцию этикетки.\n\n"
                "Это сохранённый факт с этикетки, а не вывод о безопасности "
                "и не рекомендация по дозе."
            ),
            rows=tuple(rows),
        )

    if view.step is CompositionStep.CANCELLED:
        return Screen(
            text="Ввод состава отменён. Подтверждённые данные не изменены.",
            rows=((Button("Состав", "k122comp"),),),
        )

    if view.step is CompositionStep.DUPLICATE:
        return Screen(
            text=(
                "Для этого нутриента уже есть подтверждённая ручная строка. "
                "Она не была заменена молча."
            ),
            rows=((Button("Состав", "k122comp"), Button("Итоги", "k122tot")),),
        )

    if view.step is CompositionStep.STALE:
        return _stale()

    return Screen(
        text="Это действие больше нельзя применить. Подтверждённые данные не изменены.",
        rows=((Button("Состав", "k122comp"),),),
    )


def _stale() -> Screen:
    return Screen(
        text=(
            "Экран устарел: добавка, порция или состав уже изменились. "
            "Старое действие не было применено."
        ),
        rows=((Button("Состав", "k122comp"), Button("Итоги", "k122tot")),),
    )


def _manual_token(instance_id: str | None) -> str | None:
    if instance_id is None:
        return None
    token = instance_id.removeprefix("instance:manual:")
    return token if re.fullmatch(r"[0-9a-f]{16}", token) else None


def _unit_genitive(unit_label: str | None) -> str:
    if unit_label is None:
        return "единиц"
    forms = _UNIT_NAMES.get(unit_label)
    return unit_label if forms is None else forms[2]


def _decimal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered.replace(".", ",")


def _mass_unit(unit: str) -> str:
    return _MASS_UNITS.get(unit, unit)
