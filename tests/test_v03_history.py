from datetime import UTC, datetime
from decimal import Decimal

from vitaminbot.application.intake import (
    HistoryActionResult,
    HistoryActionStatus,
    HistoryCorrectionPreview,
    HistoryEntryView,
    HistoryStatus,
    HistoryView,
)
from vitaminbot.presentation.telegram import render_history, render_history_action_result


def _callbacks(view: HistoryView) -> list[str]:
    screen = render_history(view)
    return [button.callback_data for row in screen.rows for button in row]


def test_history_renderer_keeps_audit_states_and_two_step_correction() -> None:
    view = HistoryView(
        status=HistoryStatus.READY,
        entries=(
            HistoryEntryView(
                occurrence_id="occ-taken",
                occurrence_revision=5,
                action_kind="taken",
                name="Magnesium",
                quantity=Decimal("2"),
                unit_label="capsule",
                created_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
                entered_in_error=False,
                correctable=True,
            ),
            HistoryEntryView(
                occurrence_id="occ-old",
                occurrence_revision=7,
                action_kind="skip",
                name="Vitamin D3",
                quantity=Decimal("1"),
                unit_label="softgel",
                created_at=datetime(2026, 9, 30, 9, 0, tzinfo=UTC),
                entered_in_error=True,
                correctable=False,
            ),
            HistoryEntryView(
                occurrence_id="occ-correction",
                occurrence_revision=7,
                action_kind="correction",
                name="Vitamin D3",
                quantity=Decimal("1"),
                unit_label="softgel",
                created_at=datetime(2026, 9, 30, 9, 1, tzinfo=UTC),
                entered_in_error=False,
                correctable=False,
            ),
        ),
    )

    screen = render_history(view)

    assert screen.text.startswith("История")
    assert "Magnesium: 2 капсулы — принято" in screen.text
    assert "Vitamin D3: 1 мягкая капсула — пропущено · ошибочная запись" in screen.text
    assert "Vitamin D3: 1 мягкая капсула — исправление" in screen.text
    assert "Доставка напоминания не доказывает" in screen.text

    callbacks = _callbacks(view)
    assert "k120q:occ-taken:5" in callbacks
    assert "k120q:occ-old:7" not in callbacks
    assert "k120today" in callbacks
    assert "k120a" in callbacks
    assert "k120p" in callbacks
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_history_correction_preview_requires_explicit_confirmation() -> None:
    result = HistoryActionResult(
        status=HistoryActionStatus.PREVIEW,
        preview=HistoryCorrectionPreview(
            occurrence_id="occ-taken",
            expected_revision=5,
            name="Magnesium",
            state="taken",
        ),
    )

    screen = render_history_action_result(result)

    assert screen.text.startswith("Исправить запись — Magnesium")
    assert "Текущая отметка: принято." in screen.text
    assert "останется в истории как ошибочная" in screen.text
    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert callbacks == ["k120c:occ-taken:5", "k120h"]


def test_history_applied_stale_invalid_and_empty_states_are_explicit() -> None:
    empty = HistoryView(status=HistoryStatus.EMPTY)
    empty_screen = render_history(empty)
    assert "Отметок пока нет." in empty_screen.text
    assert _callbacks(empty) == ["k120today", "k120a"]

    applied = render_history_action_result(
        HistoryActionResult(
            status=HistoryActionStatus.APPLIED,
            view=HistoryView(status=HistoryStatus.EMPTY),
        )
    )
    assert applied.text.startswith("Исправление сохранено.")
    assert "Отметок пока нет." in applied.text

    stale = render_history_action_result(
        HistoryActionResult(status=HistoryActionStatus.STALE)
    )
    assert "Повторное исправление не записано." in stale.text
    assert [button.callback_data for row in stale.rows for button in row] == ["k120h"]

    invalid = render_history_action_result(
        HistoryActionResult(status=HistoryActionStatus.INVALID)
    )
    assert "История не изменена." in invalid.text
