from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from vitaminbot.application.kir116 import Button, Screen
from vitaminbot.telegram.bot import _operational_screen, _scientific_screen


def _context() -> Any:
    return cast(Any, SimpleNamespace(application=SimpleNamespace(bot_data={})))


def _callbacks(screen: Screen) -> list[str]:
    return [button.callback_data for row in screen.rows for button in row]


def test_lookup_driven_kir174_prompt_is_not_rewritten_by_v02_shell() -> None:
    prompt = Screen(
        text=(
            "Для текущего SAFE_LEVEL железа источник исключает приём под "
            "медицинским наблюдением. Нужно знать только относится ли это "
            "к текущему приёму железа."
        ),
        rows=(
            (
                Button("Да", "k174med:scope:0:yes"),
                Button("Нет", "k174med:scope:0:no"),
            ),
            (Button("Не сейчас", "k174skip"),),
        ),
    )

    assert _operational_screen(_context(), prompt, surface="safety") == prompt
    assert _scientific_screen(prompt) == prompt
    assert _callbacks(prompt) == [
        "k174med:scope:0:yes",
        "k174med:scope:0:no",
        "k174skip",
    ]


def test_profile_shell_preserves_view_only_kir174_entry_without_new_questions() -> None:
    profile = Screen(
        text=(
            "Profile\n\n"
            "Timezone: Europe/Helsinki\n"
            "Locale: ru\n\n"
            "Only technical profile fields are collected here. "
            "Medical/applicability fields are not collected speculatively."
        ),
        rows=(
            (Button("Edit timezone", "pt:2"),),
            (Button("Edit locale", "pl:2"),),
            (Button("Контекст применимости", "k174profile"),),
        ),
    )

    projected = _operational_screen(_context(), profile, surface="profile")

    assert "k174profile" in _callbacks(projected)
    assert "не собираются заранее" in projected.text
    assert not any(word in projected.text.lower() for word in ("лекарств", "диагноз", "болезн"))
