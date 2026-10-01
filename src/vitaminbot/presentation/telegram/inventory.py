from __future__ import annotations

from vitaminbot.application.supplements import (
    Button,
    InventoryEditStep,
    InventoryEditView,
    Screen,
)


def render_inventory_edit(view: InventoryEditView) -> Screen:
    if view.step is InventoryEditStep.QUANTITY:
        return Screen(
            text=(
                f"Запас · {view.name or 'Добавка'}\n\n"
                "Сколько единиц осталось сейчас?\n"
                "Отправьте неотрицательное число. Это ваш операционный учёт, "
                "а не данные с этикетки."
            ),
            rows=((Button("Отмена", "ivc"),),),
        )

    if view.step is InventoryEditStep.COMPLETE:
        if view.supplement_instance_id is None or view.supplement_revision is None:
            return _stale()
        token = view.supplement_instance_id.removeprefix("instance:manual:")
        return Screen(
            text=(
                f"Запас сохранён · {view.name or 'Добавка'}\n\n"
                "Текущий остаток обновлён. Автоматическое списание по факту приёма "
                "подключается отдельным слоем."
            ),
            rows=((Button("Открыть добавку", f"o:{token}:{view.supplement_revision}"),),),
        )

    if view.step is InventoryEditStep.CANCELLED:
        return Screen(
            text="Изменение запаса отменено.",
            rows=((Button("Мои добавки", "ls"),),),
        )

    if view.step is InventoryEditStep.STALE:
        return _stale()

    return Screen(
        text="Значение запаса не распознано. Данные не были изменены.",
        rows=((Button("Мои добавки", "ls"),),),
    )


def _stale() -> Screen:
    return Screen(
        text=(
            "Карточка добавки изменилась до сохранения запаса. "
            "Остаток не был записан."
        ),
        rows=((Button("Мои добавки", "ls"),),),
    )
