from decimal import Decimal

from vitaminbot.application.supplements import (
    SupplementDetailStatus,
    SupplementDetailView,
)
from vitaminbot.presentation.telegram import render_supplement_detail


def _callbacks(view: SupplementDetailView) -> list[str]:
    screen = render_supplement_detail(view)
    return [button.callback_data for row in screen.rows for button in row]


def test_quick_record_detail_does_not_invent_label_serving() -> None:
    view = SupplementDetailView(
        status=SupplementDetailStatus.READY,
        instance_id="instance:manual:0123456789abcdef",
        revision=3,
        name="Magnesium Citrate",
        unit_label="capsule",
        serving_basis_type="per_consumption_unit",
        units_per_serving=Decimal("1"),
        plan_quantity=Decimal("2"),
        plan_bucket="evening",
        plan_unit_label="capsule",
    )

    screen = render_supplement_detail(view)

    assert screen.text.startswith("Magnesium Citrate")
    assert "2 капсулы · вечером" in screen.text
    assert "Порция с этикетки пока не подтверждена." in screen.text
    assert "Этикетка: 1 капсула" not in screen.text
    assert "Статус\nАктивен" in screen.text

    callbacks = _callbacks(view)
    assert "p:0123456789abcdef:3" in callbacks
    assert "en:0123456789abcdef:3" in callbacks
    assert "es:0123456789abcdef:3" in callbacks
    assert "rp:0123456789abcdef:3" in callbacks
    assert "k122comp" in callbacks
    assert "ls" in callbacks


def test_label_serving_detail_preserves_explicit_manual_fact() -> None:
    view = SupplementDetailView(
        status=SupplementDetailStatus.READY,
        instance_id="instance:manual:fedcba9876543210",
        revision=4,
        name="Vitamin D3",
        unit_label="softgel",
        serving_basis_type="per_label_portion",
        units_per_serving=Decimal("2"),
        plan_quantity=Decimal("1"),
        plan_bucket="morning",
        plan_unit_label="softgel",
    )

    screen = render_supplement_detail(view)

    assert "1 мягкая капсула · утром" in screen.text
    assert "Этикетка: 2 мягкие капсулы на порцию." in screen.text


def test_supplement_detail_stale_and_missing_fail_closed() -> None:
    stale = render_supplement_detail(SupplementDetailView(status=SupplementDetailStatus.STALE))
    assert "Карточка добавки устарела." in stale.text
    assert [button.callback_data for row in stale.rows for button in row] == ["ls"]

    missing = render_supplement_detail(
        SupplementDetailView(status=SupplementDetailStatus.NOT_FOUND)
    )
    assert "Добавка больше не найдена." in missing.text
    assert [button.callback_data for row in missing.rows for button in row] == ["ls"]
