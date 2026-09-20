from vitaminbot.application.kir116 import Button, Screen
from vitaminbot.application.russian_presenter import RussianFirstPresenter


def test_kir116_projection_is_russian_first_and_preserves_callbacks() -> None:
    source = Screen(
        text=(
            "Review manual entry — Example\n\n"
            "Label serving: 1 capsule\n"
            "Confirming means this matches what you entered. "
            "It does not mean the supplement is safe or appropriate for you."
        ),
        rows=(
            (Button("Confirm entry", "mc:opaque:1"),),
            (Button("Cancel", "x"),),
        ),
    )

    projected = RussianFirstPresenter().project("kir116", source)

    assert "Проверьте ручной ввод" in projected.text
    assert "Порция на этикетке" in projected.text
    assert "капсула" in projected.text
    assert "не означает" in projected.text
    assert "безопас" in projected.text
    assert projected.rows[0][0].label == "Подтвердить"
    assert projected.rows[0][0].callback_data == "mc:opaque:1"
    assert projected.rows[1][0].callback_data == "x"


def test_kir120_projection_keeps_null_gap_language_non_numeric() -> None:
    source = Screen(
        text=(
            "Why this time? — Calcium\n\n"
            "Timing source: Your preference. "
            "No evidence-backed planning note is attached to this occurrence. "
            "VitaminBot is not inferring a biological Morning/Day/Evening advantage."
        ),
        rows=((Button("Back to Today", "k120today"),),),
    )

    projected = RussianFirstPresenter().project("kir120", source)

    assert "Почему это время?" in projected.text
    assert "Источник времени: ваша настройка" in projected.text
    assert "биологическое преимущество" in projected.text
    assert projected.rows[0][0].label == "К Сегодня"
    assert projected.rows[0][0].callback_data == "k120today"


def test_governed_kir146_copy_is_not_translated_or_rewritten() -> None:
    governed = Screen(
        text=(
            "Reference comparison: CANNOT_ASSESS\n"
            "No personalized safety conclusion is made."
        ),
        rows=((Button("Source", "k146s:vitamin_d"),),),
    )

    assert RussianFirstPresenter().project("kir146", governed) == governed
