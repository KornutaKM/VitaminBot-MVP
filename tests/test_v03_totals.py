from decimal import Decimal

from vitaminbot.application.nutrition import (
    NutrientContributorView,
    NutrientTotalsView,
    RegimenTotalsStatus,
    RegimenTotalsView,
)
from vitaminbot.domain import Unit
from vitaminbot.presentation.telegram import render_regimen_totals


def _callbacks(view: RegimenTotalsView) -> list[str]:
    screen = render_regimen_totals(view)
    return [button.callback_data for row in screen.rows for button in row]


def test_complete_regimen_totals_show_total_and_contributor_breakdown() -> None:
    view = RegimenTotalsView(
        status=RegimenTotalsStatus.READY,
        nutrients=(
            NutrientTotalsView(
                subject_id="analyte:magnesium",
                name="Магний",
                total=Decimal("75000"),
                unit=Unit.MICROGRAM,
                is_complete=True,
                contributors=(
                    NutrientContributorView(
                        tracked_instance_id="instance:manual:0123456789abcdef",
                        name="Example Magnesium",
                        value=Decimal("75000"),
                        unit=Unit.MICROGRAM,
                    ),
                ),
                unresolved_contributor_count=0,
                issue_codes=(),
                suppressed_exact_repeat_count=0,
                substance_key="magnesium",
            ),
        ),
    )

    screen = render_regimen_totals(view)

    assert screen.text.startswith("Итоги режима")
    assert "Магний · 75000 мкг/день" in screen.text
    assert "• Example Magnesium — 75000 мкг" in screen.text
    assert "итог неполный" not in screen.text
    assert "Неизвестное значение не считается нулём." in screen.text

    callbacks = _callbacks(view)
    assert callbacks == [
        "k122safe",
        "k122rules",
        "k146c:magnesium",
        "k120today",
        "k120p",
        "k122comp",
    ]
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_incomplete_regimen_totals_withhold_full_numeric_total() -> None:
    view = RegimenTotalsView(
        status=RegimenTotalsStatus.READY,
        nutrients=(
            NutrientTotalsView(
                subject_id="analyte:magnesium",
                name="Магний",
                total=None,
                unit=None,
                is_complete=False,
                contributors=(
                    NutrientContributorView(
                        tracked_instance_id="instance:manual:0123456789abcdef",
                        name="Known Magnesium",
                        value=Decimal("50000"),
                        unit=Unit.MICROGRAM,
                    ),
                ),
                unresolved_contributor_count=1,
                issue_codes=("unresolved_contributor",),
                suppressed_exact_repeat_count=1,
                substance_key="magnesium",
            ),
        ),
        unresolved_contributor_count=1,
    )

    screen = render_regimen_totals(view)

    assert "Магний · итог неполный" in screen.text
    assert "• Known Magnesium — 50000 мкг" in screen.text
    assert "Нужно уточнить: полный итог не показываю." in screen.text
    assert "Точный повтор одного и того же вклада не посчитан второй раз." in screen.text
    assert "Они не превращены в ноль" in screen.text
    assert "Магний · 50000 мкг/день" not in screen.text


def test_empty_regimen_totals_states_preserve_unknown_as_unknown() -> None:
    no_supplements = render_regimen_totals(
        RegimenTotalsView(status=RegimenTotalsStatus.NO_SUPPLEMENTS)
    )
    assert "Добавок пока нет." in no_supplements.text
    assert _callbacks(
        RegimenTotalsView(status=RegimenTotalsStatus.NO_SUPPLEMENTS)
    ) == ["a"]

    no_aggregates_view = RegimenTotalsView(
        status=RegimenTotalsStatus.NO_AGGREGATES,
        unresolved_contributor_count=1,
    )
    no_aggregates = render_regimen_totals(no_aggregates_view)
    assert "Пока нечего суммировать." in no_aggregates.text
    assert "Неизвестное значение не считается нулём." in no_aggregates.text
    assert _callbacks(no_aggregates_view) == ["k122comp", "k120p", "k120today"]
