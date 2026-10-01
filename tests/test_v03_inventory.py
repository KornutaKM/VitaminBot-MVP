from decimal import Decimal

from vitaminbot.application.supplements import (
    InventoryEditStep,
    InventoryEditView,
    SupplementDetailStatus,
    SupplementDetailView,
)
from vitaminbot.presentation.telegram import render_inventory_edit, render_supplement_detail


def test_inventory_editor_prompts_and_returns_to_supplement() -> None:
    prompt = render_inventory_edit(
        InventoryEditView(
            step=InventoryEditStep.QUANTITY,
            name="Magnesium Citrate",
            unit_label="capsule",
            supplement_instance_id="instance:manual:0123456789abcdef",
            supplement_revision=3,
        )
    )
    assert "Сколько единиц осталось сейчас?" in prompt.text
    assert [button.callback_data for row in prompt.rows for button in row] == ["ivc"]

    complete = render_inventory_edit(
        InventoryEditView(
            step=InventoryEditStep.COMPLETE,
            name="Magnesium Citrate",
            unit_label="capsule",
            supplement_instance_id="instance:manual:0123456789abcdef",
            supplement_revision=3,
        )
    )
    assert "Запас сохранён" in complete.text
    assert [button.callback_data for row in complete.rows for button in row] == [
        "o:0123456789abcdef:3"
    ]


def test_supplement_detail_shows_inventory_horizon_only_for_same_unit_identity() -> None:
    current = SupplementDetailView(
        status=SupplementDetailStatus.READY,
        instance_id="instance:manual:0123456789abcdef",
        revision=3,
        name="Magnesium Citrate",
        unit_id="unit:manual:0123456789abcdef",
        unit_label="capsule",
        serving_basis_type="per_consumption_unit",
        units_per_serving=Decimal("1"),
        plan_quantity=Decimal("2"),
        plan_bucket="evening",
        plan_unit_label="capsule",
        plan_unit_id="unit:manual:0123456789abcdef",
        lifecycle_status="active",
        inventory_remaining_units=Decimal("36"),
        inventory_unit_id="unit:manual:0123456789abcdef",
        inventory_revision=1,
    )
    screen = render_supplement_detail(current)

    assert "Запас\n36 капсул · ≈ 18 дн." in screen.text
    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert "iv:0123456789abcdef:3" in callbacks

    stale_unit = SupplementDetailView(
        status=SupplementDetailStatus.READY,
        instance_id="instance:manual:0123456789abcdef",
        revision=4,
        name="Magnesium Citrate",
        unit_id="unit:manual:0123456789abcdef:r4",
        unit_label="capsule",
        serving_basis_type="per_label_portion",
        units_per_serving=Decimal("1"),
        plan_quantity=Decimal("2"),
        plan_bucket="evening",
        plan_unit_label="capsule",
        plan_unit_id="unit:manual:0123456789abcdef",
        lifecycle_status="active",
        inventory_remaining_units=Decimal("36"),
        inventory_unit_id="unit:manual:0123456789abcdef",
        inventory_revision=1,
    )
    stale_screen = render_supplement_detail(stale_unit)
    assert "Нужно уточнить после смены единицы учёта." in stale_screen.text
    assert "≈ 18 дн." not in stale_screen.text


def test_inventory_invalid_and_cancelled_are_explicit() -> None:
    invalid = render_inventory_edit(InventoryEditView(step=InventoryEditStep.INVALID))
    assert "Данные не были изменены." in invalid.text

    cancelled = render_inventory_edit(InventoryEditView(step=InventoryEditStep.CANCELLED))
    assert "Изменение запаса отменено." in cancelled.text
