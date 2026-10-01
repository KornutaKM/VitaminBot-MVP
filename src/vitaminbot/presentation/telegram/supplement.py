from __future__ import annotations

from decimal import Decimal

from vitaminbot.application.supplements import (
    Button,
    Screen,
    SupplementDetailStatus,
    SupplementDetailView,
)

_BUCKET_RU = {
    "morning": "утром",
    "day": "днём",
    "evening": "вечером",
}
_UNIT_FORMS = {
    "capsule": ("капсула", "капсулы", "капсул"),
    "tablet": ("таблетка", "таблетки", "таблеток"),
    "softgel": ("мягкая капсула", "мягкие капсулы", "мягких капсул"),
    "scoop": ("мерная ложка", "мерные ложки", "мерных ложек"),
    "drop": ("капля", "капли", "капель"),
}


def render_supplement_detail(view: SupplementDetailView) -> Screen:
    if view.status is SupplementDetailStatus.STALE:
        return Screen(
            text=(
                "Карточка добавки устарела. Ничего не было изменено. "
                "Откройте актуальный список добавок."
            ),
            rows=((Button("Мои добавки", "ls"),),),
        )
    if view.status is SupplementDetailStatus.NOT_FOUND:
        return Screen(
            text="Добавка больше не найдена.",
            rows=((Button("Мои добавки", "ls"),),),
        )

    if (
        view.instance_id is None
        or view.revision is None
        or view.name is None
        or view.unit_label is None
    ):
        return Screen(
            text="Карточку добавки нельзя безопасно отобразить.",
            rows=((Button("Мои добавки", "ls"),),),
        )

    token = view.instance_id.removeprefix("instance:manual:")
    plan = _plan_line(view)
    unit = _unit_label(view.unit_label, Decimal("1"))
    basis = _basis_line(view)
    paused = view.lifecycle_status == "paused"
    status = "На паузе" if paused else "Активен"
    lifecycle_button = (
        Button("Продолжить", f"rs:{token}:{view.revision}")
        if paused
        else Button("Пауза", f"ps:{token}:{view.revision}")
    )

    return Screen(
        text=(
            f"{view.name}\n\n"
            "Режим\n"
            f"{plan}\n\n"
            "Единица учёта\n"
            f"{unit}\n"
            f"{basis}\n\n"
            "Статус\n"
            f"{status}"
        ),
        rows=(
            (Button("Изменить режим", f"p:{token}:{view.revision}"),),
            (Button("Состав и итоги", "k122comp"),),
            (
                Button("Изменить название", f"en:{token}:{view.revision}"),
                Button("Изменить единицу", f"es:{token}:{view.revision}"),
            ),
            (lifecycle_button,),
            (Button("Удалить…", f"rp:{token}:{view.revision}"),),
            (Button("Назад к добавкам", "ls"),),
        ),
    )


def _plan_line(view: SupplementDetailView) -> str:
    if view.plan_quantity is None or view.plan_bucket is None:
        return "Не настроен"
    unit_label = view.plan_unit_label or view.unit_label
    quantity = view.plan_quantity
    when = _BUCKET_RU.get(view.plan_bucket, view.plan_bucket)
    return f"{_decimal(quantity)} {_unit_label(unit_label, quantity)} · {when}"


def _basis_line(view: SupplementDetailView) -> str:
    if view.serving_basis_type == "per_consumption_unit":
        return "Порция с этикетки пока не подтверждена."
    if view.units_per_serving is None:
        return "Порция с этикетки не указана."
    return (
        "Этикетка: "
        f"{_decimal(view.units_per_serving)} "
        f"{_unit_label(view.unit_label, view.units_per_serving)} на порцию."
    )


def _decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f").replace(".", ",")


def _unit_label(unit_label: str | None, quantity: Decimal) -> str:
    if unit_label is None:
        return "единиц"
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
