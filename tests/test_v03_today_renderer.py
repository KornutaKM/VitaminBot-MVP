from datetime import date, time
from decimal import Decimal

import pytest

from vitaminbot.application.intake import (
    TodayActionResult,
    TodayActionStatus,
    TodayOccurrenceState,
    TodayOccurrenceView,
    TodayStatus,
    TodayView,
)
from vitaminbot.presentation.telegram import render_today, render_today_action_result


def _occurrence(
    *,
    occurrence_id: str,
    name: str,
    state: TodayOccurrenceState,
    later: bool = False,
) -> TodayOccurrenceView:
    actionable = state in {
        TodayOccurrenceState.PENDING,
        TodayOccurrenceState.NEEDS_REVIEW,
    }
    return TodayOccurrenceView(
        occurrence_id=occurrence_id,
        revision=4,
        name=name,
        quantity=Decimal("2"),
        unit_label="capsule",
        schedule_kind="explicit_time",
        schedule_label="explicit_time",
        scheduled_local_time=time(20, 0),
        state=state,
        can_take=actionable,
        can_later=state is TodayOccurrenceState.PENDING and not later,
        can_skip=actionable,
        can_explain=True,
    )


def test_render_today_matches_compact_russian_daily_loop() -> None:
    view = TodayView(
        status=TodayStatus.READY,
        local_date=date(2026, 10, 1),
        occurrences=(
            _occurrence(
                occurrence_id="occ-d3",
                name="Vitamin D3",
                state=TodayOccurrenceState.TAKEN,
            ),
            _occurrence(
                occurrence_id="occ-mg",
                name="Magnesium",
                state=TodayOccurrenceState.PENDING,
            ),
        ),
    )

    screen = render_today(view)

    assert screen.text.startswith("Сегодня · четверг, 1 октября")
    assert "✓ Vitamin D3" in screen.text
    assert "○ Magnesium" in screen.text
    assert "2 капсулы · 20:00" in screen.text

    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert "k120t:occ-mg:4" in callbacks
    assert "k120l:occ-mg:4" in callbacks
    assert "k120s:occ-mg:4" in callbacks
    assert "k120w:occ-mg:4" in callbacks
    assert "k120p" in callbacks
    assert "k120h" in callbacks

    assert "k120t:occ-d3:4" not in callbacks
    assert "k120s:occ-d3:4" not in callbacks


@pytest.mark.parametrize(
    ("status", "expected_callback"),
    [
        (TodayStatus.MISSING_TIMEZONE, "pf"),
        (TodayStatus.AMBIGUOUS_LOCAL_TIME, "k120p"),
        (TodayStatus.INVALID_SCHEDULE, "k120p"),
    ],
)
def test_render_today_fail_closed_states(
    status: TodayStatus,
    expected_callback: str,
) -> None:
    screen = render_today(TodayView(status=status))

    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert callbacks == [expected_callback]


def test_render_today_empty_day_keeps_navigation() -> None:
    screen = render_today(
        TodayView(
            status=TodayStatus.READY,
            local_date=date(2026, 10, 1),
        )
    )

    assert "На сегодня ничего не запланировано." in screen.text
    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert callbacks == ["k120p", "k120h"]


def test_render_today_action_result_keeps_stale_action_explicit() -> None:
    stale = render_today_action_result(TodayActionResult(status=TodayActionStatus.STALE))
    assert "Повторная отметка о приёме не записана." in stale.text
    callbacks = [button.callback_data for row in stale.rows for button in row]
    assert callbacks == ["k120today", "k120h"]


def test_render_today_action_result_renders_applied_view() -> None:
    view = TodayView(
        status=TodayStatus.READY,
        local_date=date(2026, 10, 1),
    )
    screen = render_today_action_result(
        TodayActionResult(
            status=TodayActionStatus.APPLIED,
            view=view,
        )
    )
    assert "На сегодня ничего не запланировано." in screen.text
