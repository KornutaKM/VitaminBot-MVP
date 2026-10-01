from __future__ import annotations

from vitaminbot.application.intake import (
    AdherenceStatus,
    AdherenceView,
    AdherenceWindowView,
)
from vitaminbot.application.supplements import Button, Screen


def render_adherence(view: AdherenceView) -> Screen:
    if view.status is AdherenceStatus.MISSING_TIMEZONE:
        return Screen(
            text=(
                "Статистика отметок\n\n"
                "Для календарной сводки нужен ваш часовой пояс. "
                "Это техническая настройка расписания."
            ),
            rows=((Button("Открыть профиль", "pf"),),),
        )
    if view.status is AdherenceStatus.INVALID_SCHEDULE:
        return Screen(
            text=(
                "Статистика отметок\n\n"
                "Расписание нельзя безопасно интерпретировать для текущего дня. "
                "VitaminBot не стал достраивать события автоматически."
            ),
            rows=((Button("Открыть план", "k120p"),),),
        )

    lines = ["Статистика отметок", ""]
    for index, window in enumerate(view.windows):
        if index:
            lines.append("")
        lines.extend(_window_lines(window))

    lines.extend(
        [
            "",
            "Сводка строится по созданным событиям расписания и вашим отметкам. "
            "Это не медицинская оценка приверженности.",
        ]
    )
    return Screen(
        text="\n".join(lines),
        rows=(
            (Button("Сегодня", "k120today"), Button("История", "k120h")),
        ),
    )


def _window_lines(window: AdherenceWindowView) -> list[str]:
    lines = [
        f"Последние {window.days} дней",
        f"Событий плана к этому моменту: {window.planned}",
        f"Отмечено как принято: {window.taken}",
        f"Пропущено: {window.skipped}",
        f"Без окончательной отметки: {window.unresolved}",
    ]
    if window.planned:
        percent = (window.taken * 100 + window.planned // 2) // window.planned
        lines.append(f"{percent}% событий отмечено как принято")
    return lines
