from decimal import Decimal

from vitaminbot.application.supplements import QuickAddStep, QuickAddView
from vitaminbot.presentation.telegram import render_quick_add


def _callbacks(view: QuickAddView) -> list[str]:
    screen = render_quick_add(view)
    return [button.callback_data for row in screen.rows for button in row]


def test_quick_add_name_and_unit_steps_are_compact_and_callback_safe() -> None:
    name = render_quick_add(
        QuickAddView(
            step=QuickAddStep.NAME,
            draft_id="0123456789abcdef",
            revision=1,
        )
    )
    assert "Как она называется?" in name.text
    assert _callbacks(
        QuickAddView(
            step=QuickAddStep.NAME,
            draft_id="0123456789abcdef",
            revision=1,
        )
    ) == ["qac"]

    unit_view = QuickAddView(
        step=QuickAddStep.UNIT,
        name="Magnesium Citrate",
        draft_id="0123456789abcdef",
        revision=2,
    )
    unit = render_quick_add(unit_view)
    assert "Что вы принимаете?" in unit.text
    callbacks = _callbacks(unit_view)
    assert "qau:0123456789abcdef:2:c" in callbacks
    assert "qau:0123456789abcdef:2:t" in callbacks
    assert "qau:0123456789abcdef:2:sg" in callbacks
    assert "qau:0123456789abcdef:2:sc" in callbacks
    assert "qau:0123456789abcdef:2:d" in callbacks
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_quick_add_quantity_bucket_and_complete_match_product_concept() -> None:
    quantity_view = QuickAddView(
        step=QuickAddStep.QUANTITY,
        name="Magnesium Citrate",
        unit_label="capsule",
        supplement_instance_id="instance:manual:0123456789abcdef",
        supplement_revision=1,
    )
    quantity = render_quick_add(quantity_view)
    assert "Сколько капсул вы принимаете за один раз?" in quantity.text
    assert _callbacks(quantity_view) == ["qaq:1", "qaq:2", "qaq:custom", "qac"]

    bucket_view = QuickAddView(
        step=QuickAddStep.BUCKET,
        name="Magnesium Citrate",
        unit_label="capsule",
        quantity=Decimal("2"),
        revision=7,
    )
    bucket = render_quick_add(bucket_view)
    assert "Magnesium Citrate · 2 капсулы" in bucket.text
    assert "Точное время можно настроить" in bucket.text
    assert _callbacks(bucket_view) == ["qab:m:7", "qab:d:7", "qab:e:7", "qac"]

    complete_view = QuickAddView(
        step=QuickAddStep.COMPLETE,
        name="Magnesium Citrate",
        unit_label="capsule",
        quantity=Decimal("2"),
        bucket="evening",
    )
    complete = render_quick_add(complete_view)
    assert complete.text.startswith("Готово ✓")
    assert "2 капсулы · вечером" in complete.text
    assert "Состав этикетки можно добавить отдельно." in complete.text
    assert _callbacks(complete_view) == ["k122comp", "k120today", "ls"]


def test_quick_add_stale_and_cancelled_fail_closed() -> None:
    stale = render_quick_add(QuickAddView(step=QuickAddStep.STALE))
    assert "Никаких дополнительных данных не было записано." in stale.text
    assert [button.callback_data for row in stale.rows for button in row] == ["a"]

    cancelled = render_quick_add(QuickAddView(step=QuickAddStep.CANCELLED))
    assert "Добавление отменено." in cancelled.text
    assert [button.callback_data for row in cancelled.rows for button in row] == ["ls"]
