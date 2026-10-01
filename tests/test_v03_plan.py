from datetime import time
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
from vitaminbot.presentation.telegram import render_plan, render_plan_action_result


def _callbacks(view: PlanView) -> list[str]:
    screen = render_plan(view)
    return [button.callback_data for row in screen.rows for button in row]


def _item(
    *,
    schedule_kind: str = "routine_bucket",
    schedule_label: str | None = "morning",
    local_time: time | None = None,
    revision: int = 4,
) -> PlanItemView:
    return PlanItemView(
        instance_id="instance:manual:0123456789abcdef",
        name="Magnesium Citrate",
        plan_revision=revision,
        quantity=Decimal("2"),
        unit_label="capsule",
        schedule_kind=schedule_kind,
        schedule_label=schedule_label,
        local_time=local_time,
    )


def test_plan_renderer_shows_current_bucket_and_revision_bound_actions() -> None:
    view = PlanView(status=PlanStatus.READY, items=(_item(),))

    screen = render_plan(view)

    assert screen.text.startswith("План")
    assert "Magnesium Citrate" in screen.text
    assert "2 капсулы · утро" in screen.text
    assert "не медицинская рекомендация по времени" in screen.text

    labels = [button.label for row in screen.rows for button in row]
    callbacks = _callbacks(view)

    assert "✓ Утро" in labels
    assert "День" in labels
    assert "Вечер" in labels
    assert "Точное время" in labels
    assert callbacks[-3:] == ["k120today", "k122tot", "ls"]
    assert any(value.endswith(":4:m") and value.startswith("k120b:") for value in callbacks)
    assert any(value.endswith(":4:d") and value.startswith("k120b:") for value in callbacks)
    assert any(value.endswith(":4:e") and value.startswith("k120b:") for value in callbacks)
    assert any(value.endswith(":4") and value.startswith("k120e:") for value in callbacks)
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_plan_renderer_shows_exact_time_without_timing_claim() -> None:
    view = PlanView(
        status=PlanStatus.READY,
        items=(
            _item(
                schedule_kind="explicit_time",
                schedule_label="explicit_time",
                local_time=time(8, 30),
                revision=5,
            ),
        ),
    )

    screen = render_plan(view)

    assert "2 капсулы · 08:30" in screen.text
    assert "✓ Точное время · 08:30" in [
        button.label for row in screen.rows for button in row
    ]
    assert "биологическое преимущество времени суток" in screen.text


def test_plan_time_input_and_fail_closed_actions_are_explicit() -> None:
    edit = PlanTimeEditView(
        instance_id="instance:manual:0123456789abcdef",
        name="Magnesium Citrate",
        expected_plan_revision=7,
    )
    prompt = render_plan_action_result(
        PlanActionResult(
            status=PlanActionStatus.INPUT_REQUIRED,
            edit=edit,
        )
    )
    assert "Точное время · Magnesium Citrate" in prompt.text
    assert "HH:MM" in prompt.text
    assert [button.callback_data for row in prompt.rows for button in row] == ["k120pc"]

    invalid = render_plan_action_result(
        PlanActionResult(
            status=PlanActionStatus.INPUT_REQUIRED,
            edit=PlanTimeEditView(
                instance_id=edit.instance_id,
                name=edit.name,
                expected_plan_revision=edit.expected_plan_revision,
                error=PlanTimeInputError.INVALID_FORMAT,
            ),
        )
    )
    assert "Не удалось распознать время." in invalid.text

    stale = render_plan_action_result(
        PlanActionResult(status=PlanActionStatus.STALE)
    )
    assert "Старое действие не применено." in stale.text

    malformed = render_plan_action_result(
        PlanActionResult(status=PlanActionStatus.INVALID)
    )
    assert "План не изменён." in malformed.text


def test_empty_and_cancelled_plan_keep_navigation() -> None:
    empty = render_plan(PlanView(status=PlanStatus.EMPTY))
    assert "Подтверждённого режима пока нет." in empty.text
    assert [button.callback_data for row in empty.rows for button in row] == ["ls", "a"]

    view = PlanView(status=PlanStatus.READY, items=(_item(),))
    cancelled = render_plan_action_result(
        PlanActionResult(
            status=PlanActionStatus.CANCELLED,
            view=view,
        )
    )
    assert "Изменение точного времени отменено." in cancelled.text
    assert "Magnesium Citrate" in cancelled.text


def test_fractional_plan_quantity_uses_russian_decimal_and_unit_form() -> None:
    item = PlanItemView(
        instance_id="instance:manual:fedcba9876543210",
        name="Fractional supplement",
        plan_revision=2,
        quantity=Decimal("1.5"),
        unit_label="capsule",
        schedule_kind="routine_bucket",
        schedule_label="evening",
        local_time=None,
    )

    screen = render_plan(PlanView(status=PlanStatus.READY, items=(item,)))

    assert "1,5 капсулы · вечер" in screen.text
