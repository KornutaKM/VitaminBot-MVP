from datetime import date

from vitaminbot.application.intake import (
    AdherenceStatus,
    AdherenceView,
    AdherenceWindowView,
)
from vitaminbot.presentation.telegram import render_adherence


def test_adherence_renderer_is_descriptive_not_evaluative() -> None:
    view = AdherenceView(
        status=AdherenceStatus.READY,
        windows=(
            AdherenceWindowView(
                days=7,
                start_date=date(2026, 9, 14),
                end_date=date(2026, 9, 20),
                planned=4,
                taken=3,
                skipped=0,
                unresolved=1,
            ),
            AdherenceWindowView(
                days=30,
                start_date=date(2026, 8, 22),
                end_date=date(2026, 9, 20),
                planned=10,
                taken=7,
                skipped=1,
                unresolved=2,
            ),
        ),
    )

    screen = render_adherence(view)

    assert screen.text.startswith("Статистика отметок")
    assert "Последние 7 дней" in screen.text
    assert "75% событий отмечено как принято" in screen.text
    assert "Последние 30 дней" in screen.text
    assert "70% событий отмечено как принято" in screen.text
    assert "Без окончательной отметки: 2" in screen.text
    assert "Это не медицинская оценка приверженности." in screen.text
    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert callbacks == ["k120today", "k120h"]


def test_adherence_renderer_handles_empty_window_without_fake_percentage() -> None:
    screen = render_adherence(
        AdherenceView(
            status=AdherenceStatus.READY,
            windows=(
                AdherenceWindowView(
                    days=7,
                    start_date=date(2026, 9, 14),
                    end_date=date(2026, 9, 20),
                    planned=0,
                    taken=0,
                    skipped=0,
                    unresolved=0,
                ),
            ),
        )
    )

    assert "Событий плана к этому моменту: 0" in screen.text
    assert "% событий отмечено как принято" not in screen.text


def test_adherence_renderer_fail_closed_states() -> None:
    missing = render_adherence(AdherenceView(status=AdherenceStatus.MISSING_TIMEZONE))
    assert "нужен ваш часовой пояс" in missing.text
    assert [button.callback_data for row in missing.rows for button in row] == ["pf"]

    invalid = render_adherence(AdherenceView(status=AdherenceStatus.INVALID_SCHEDULE))
    assert "не стал достраивать события автоматически" in invalid.text
    assert [button.callback_data for row in invalid.rows for button in row] == ["k120p"]
