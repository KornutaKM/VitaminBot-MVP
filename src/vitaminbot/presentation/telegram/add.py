from __future__ import annotations

from decimal import Decimal

from vitaminbot.application.supplements import Button, QuickAddStep, QuickAddView, Screen

_UNIT_FORMS = {
    "capsule": ("капсула", "капсулы", "капсул"),
    "tablet": ("таблетка", "таблетки", "таблеток"),
    "softgel": ("мягкая капсула", "мягкие капсулы", "мягких капсул"),
    "scoop": ("мерная ложка", "мерные ложки", "мерных ложек"),
    "drop": ("капля", "капли", "капель"),
}
_BUCKET_RU = {
    "morning": "утром",
    "day": "днём",
    "evening": "вечером",
}


def render_quick_add(view: QuickAddView) -> Screen:
    if view.step is QuickAddStep.NAME:
        return Screen(
            text=(
                "Добавим добавку\n\n"
                "Как она называется?\n"
                "Напишите название так, как хотите видеть его в списке."
            ),
            rows=((Button("Отмена", "qac"),),),
        )

    if view.step is QuickAddStep.UNIT:
        if view.draft_id is None or view.revision is None:
            return _stale_screen()
        name = view.name or "Добавка"
        return Screen(
            text=f"{name}\n\nЧто вы принимаете?",
            rows=(
                (
                    Button("Капсула", f"qau:{view.draft_id}:{view.revision}:c"),
                    Button("Таблетка", f"qau:{view.draft_id}:{view.revision}:t"),
                ),
                (
                    Button("Мягкая капсула", f"qau:{view.draft_id}:{view.revision}:sg"),
                    Button("Мерная ложка", f"qau:{view.draft_id}:{view.revision}:sc"),
                ),
                (Button("Капля", f"qau:{view.draft_id}:{view.revision}:d"),),
                (Button("Отмена", "qac"),),
            ),
        )

    if view.step is QuickAddStep.QUANTITY:
        name = view.name or "Добавка"
        unit = _count_question_unit(view.unit_label)
        return Screen(
            text=(
                f"{name}\n\n"
                f"Сколько {unit} вы принимаете за один раз?\n"
                "Можно выбрать 1 или 2 либо отправить другое положительное число сообщением."
            ),
            rows=(
                (Button("1", "qaq:1"), Button("2", "qaq:2")),
                (Button("Другое число", "qaq:custom"),),
                (Button("Отмена", "qac"),),
            ),
        )

    if view.step is QuickAddStep.BUCKET:
        if view.revision is None:
            return _stale_screen()
        name = view.name or "Добавка"
        quantity = view.quantity or Decimal("0")
        amount = f"{_decimal(quantity)} {_unit_label(view.unit_label, quantity)}"
        return Screen(
            text=(
                f"{name} · {amount}\n\n"
                "Когда напоминать?\n"
                "Утро / день / вечер — это только метки вашего режима. "
                "Точное время можно настроить после сохранения в разделе «План»."
            ),
            rows=(
                (
                    Button("Утро", f"qab:m:{view.revision}"),
                    Button("День", f"qab:d:{view.revision}"),
                    Button("Вечер", f"qab:e:{view.revision}"),
                ),
                (Button("Отмена", "qac"),),
            ),
        )

    if view.step is QuickAddStep.COMPLETE:
        quantity = view.quantity or Decimal("0")
        amount = f"{_decimal(quantity)} {_unit_label(view.unit_label, quantity)}"
        when = _BUCKET_RU.get(view.bucket or "", view.bucket or "")
        details = amount if not when else f"{amount} · {when}"
        return Screen(
            text=(
                "Готово ✓\n\n"
                f"{view.name or 'Добавка'}\n"
                f"{details}\n\n"
                "Состав этикетки можно добавить отдельно. "
                "Он не нужен для работы ежедневного плана."
            ),
            rows=(
                (Button("Добавить состав с этикетки", "k122comp"),),
                (Button("Сегодня", "k120today"), Button("Мои добавки", "ls")),
            ),
        )

    if view.step is QuickAddStep.CANCELLED:
        return Screen(
            text="Добавление отменено. Подтверждённые добавки и история не изменены.",
            rows=((Button("Мои добавки", "ls"),),),
        )

    if view.step is QuickAddStep.STALE:
        return _stale_screen()

    return Screen(
        text=(
            "Не удалось применить этот шаг. Данные не были угаданы или дополнены автоматически. "
            "Начните добавление ещё раз."
        ),
        rows=((Button("Добавить заново", "a"),),),
    )


def _stale_screen() -> Screen:
    return Screen(
        text=(
            "Этот шаг уже устарел. Никаких дополнительных данных не было записано. "
            "Откройте актуальное добавление ещё раз."
        ),
        rows=((Button("Добавить заново", "a"),),),
    )


def _decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f").replace(".", ",")


def _unit_label(unit_label: str | None, quantity: Decimal) -> str:
    if unit_label is None:
        return "единицы"
    forms = _UNIT_FORMS.get(unit_label)
    if forms is None:
        return unit_label
    if quantity != quantity.to_integral():
        return forms[1]
    value = abs(int(quantity))
    last_two = value % 100
    last = value % 10
    if last == 1 and last_two != 11:
        return forms[0]
    if last in {2, 3, 4} and last_two not in {12, 13, 14}:
        return forms[1]
    return forms[2]


def _count_question_unit(unit_label: str | None) -> str:
    if unit_label is None:
        return "единиц"
    forms = _UNIT_FORMS.get(unit_label)
    return unit_label if forms is None else forms[2]
