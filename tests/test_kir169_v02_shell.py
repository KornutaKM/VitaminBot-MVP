from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID

from vitaminbot.application.kir116 import Button, Screen
from vitaminbot.application.kir120 import KIR120Controller
from vitaminbot.persistence.kir120 import OccurrenceRecord
from vitaminbot.telegram.bot import _resolve_start_screen
from vitaminbot.telegram.presentation import (
    project_v02_scientific_shell,
    project_v02_screen,
)


def _callbacks(screen: Screen) -> list[str]:
    return [button.callback_data for row in screen.rows for button in row]


def _labels(screen: Screen) -> list[str]:
    return [button.label for row in screen.rows for button in row]


class _StartBase:
    def __init__(self, *, returning: bool) -> None:
        self.returning = returning
        self.start_calls = 0

    def has_supplements(self, telegram_user_id: int) -> bool:
        assert telegram_user_id > 0
        return self.returning

    def start(self, telegram_user_id: int) -> Screen:
        self.start_calls += 1
        return Screen(
            text="Welcome to VitaminBot",
            rows=((Button("Add first supplement", "a"),),),
        )


class _StartSchedule:
    def __init__(self) -> None:
        self.today_calls = 0

    def today(self, telegram_user_id: int) -> Screen:
        self.today_calls += 1
        return Screen(
            text="Today\n\nNo scheduled occurrences for this local day.",
            rows=((Button("Open Plan", "k120p"),),),
        )


def test_start_routes_first_use_to_onboarding_and_returning_user_to_today() -> None:
    first = _StartBase(returning=False)
    schedule = _StartSchedule()

    first_screen, first_surface = _resolve_start_screen(first, schedule, 169001)
    assert first_surface == "start"
    assert first_screen.text == "Welcome to VitaminBot"
    assert first.start_calls == 1
    assert schedule.today_calls == 0

    returning = _StartBase(returning=True)
    today_screen, today_surface = _resolve_start_screen(returning, schedule, 169002)
    assert today_surface == "today"
    assert today_screen.text.startswith("Today")
    assert returning.start_calls == 0
    assert schedule.today_calls == 1


def test_first_use_and_empty_supplement_shell_are_russian_first() -> None:
    first = project_v02_screen(
        Screen(
            text="Welcome to VitaminBot",
            rows=(
                (Button("Add first supplement", "a"),),
                (Button("How it works", "h"),),
            ),
        ),
        surface="start",
    )
    assert first.text.startswith("VitaminBot")
    assert "без догадок" in first.text
    assert _callbacks(first) == ["a", "h"]
    assert _labels(first)[0] == "Добавить первую добавку"

    empty = project_v02_screen(
        Screen(
            text="No supplements yet.\n\nAdd one manually to get started.",
            rows=((Button("Add supplement", "a"),),),
        ),
        surface="supplements",
    )
    assert empty.text.startswith("Добавок пока нет")
    assert "Сегодня" in _labels(empty)
    assert "План" in _labels(empty)
    assert "История" in _labels(empty)


def test_structured_placeholders_localize_without_rewriting_dynamic_status_token() -> None:
    supplement = project_v02_screen(
        Screen(
            text=(
                "Status: Confirmed manual entry\n\n"
                "Status: Confirmed manual entry\n"
                "Label serving: 2 capsule\n"
                "Your plan: Not set"
            ),
            rows=((Button("Back to supplements", "ls"),),),
        ),
        surface="supplement",
    )
    supplement_lines = supplement.text.splitlines()
    assert supplement_lines[0] == "Status: Confirmed manual entry"
    assert "Статус: подтверждённый ручной ввод" in supplement_lines
    assert "Порция по этикетке: 2 capsule" in supplement_lines
    assert "Ваш план: Не настроен" in supplement_lines

    profile = project_v02_screen(
        Screen(
            text="Profile\n\nTimezone: Not set\nLocale: Not set",
            rows=((Button("Edit timezone", "pt:1"),),),
        ),
        surface="profile",
    )
    assert "Часовой пояс: Не настроен" in profile.text
    assert "Язык интерфейса: Не настроен" in profile.text


def test_dynamic_add_prefixes_and_residual_copy_preserve_identity_substrings() -> None:
    serving = project_v02_screen(
        Screen(text="Serving — Serving — Formula"),
        surface="add",
    )
    assert serving.text == "Порция — Serving — Formula"

    current_name = project_v02_screen(
        Screen(text="Current name: Current name: Formula"),
        surface="add",
    )
    assert current_name.text == "Текущее название: Current name: Formula"

    edit_name = project_v02_screen(
        Screen(text="Edit name — Name updated.\n\nSend the new tracked supplement name."),
        surface="add",
    )
    assert edit_name.text.splitlines()[0] == "Edit name — Name updated."


def test_supplement_list_localizes_only_structural_state_suffix() -> None:
    projected = project_v02_screen(
        Screen(
            text="My supplements — 1\n\n1. Formula — plan set — plan set",
            rows=((Button("Open Formula — plan set", "o:0123456789abcdef:1"),),),
        ),
        surface="supplements",
    )
    lines = projected.text.splitlines()
    assert lines[0] == "Мои добавки — 1"
    assert lines[2] == "1. Formula — plan set — план настроен"


def test_supplement_open_label_uses_callback_role_not_dynamic_label_text() -> None:
    projected = project_v02_screen(
        Screen(
            text="My supplements — 1\n\n1. Plan — plan set",
            rows=((Button("Open Plan", "o:0123456789abcdef:1"),),),
        ),
        surface="supplements",
    )
    assert "1. Plan — план настроен" in projected.text
    assert _labels(projected)[0] == "Открыть Plan"


def test_today_shell_preserves_occurrence_actions_and_has_no_taken_all() -> None:
    raw = Screen(
        text=(
            "Today\n\n"
            "• Morning — Product X: 2 capsule [pending]\n\n"
            "Today shows generated occurrences. Plan edits affect the recurring template; "
            "existing Today occurrences keep their original quantity/unit snapshot."
        ),
        rows=(
            (
                Button("Taken", "k120t:occ-1:4"),
                Button("Later", "k120l:occ-1:4"),
                Button("Skip", "k120s:occ-1:4"),
            ),
            (Button("Why?", "k120w:occ-1:4"),),
            (Button("Plan", "k120p"), Button("History", "k120h")),
        ),
    )

    projected = project_v02_screen(raw, surface="today")
    callbacks = _callbacks(projected)
    labels = _labels(projected)

    assert "k120t:occ-1:4" in callbacks
    assert "k120l:occ-1:4" in callbacks
    assert "k120s:occ-1:4" in callbacks
    assert "k120w:occ-1:4" in callbacks
    assert any(label == "Принял(а)" for label in labels)
    assert all("всё" not in label.lower() for label in labels)
    assert "Итоги" in labels
    assert "Добавки" in labels
    assert "История" in labels


def test_supplement_detail_adds_contextual_composition_without_rewriting_write_callbacks() -> None:
    token = "0123456789abcdef"
    raw = Screen(
        text=(
            "Example\n\n"
            "Status: Confirmed manual entry\n"
            "Label serving: 2 capsule\n"
            "Your plan: Morning — 1 capsule\n\n"
            "Product facts and your plan are stored separately."
        ),
        rows=(
            (Button("Add / edit plan", f"p:{token}:7"),),
            (
                Button("Edit name", f"en:{token}:7"),
                Button("Edit serving", f"es:{token}:7"),
            ),
            (Button("Remove supplement…", f"rp:{token}:7"),),
            (Button("Back to supplements", "ls"),),
        ),
    )

    projected = project_v02_screen(raw, surface="supplement")
    callbacks = _callbacks(projected)

    assert f"k122c:{token}:7" in callbacks
    assert f"p:{token}:7" in callbacks
    assert f"en:{token}:7" in callbacks
    assert f"es:{token}:7" in callbacks
    assert f"rp:{token}:7" in callbacks
    assert "k122tot" in callbacks
    assert callbacks.count(f"p:{token}:7") == 1


def test_destructive_copy_matches_real_backend_scope_and_keeps_revision_callback() -> None:
    token = "0123456789abcdef"
    raw = Screen(
        text=(
            "Remove Example?\n\n"
            "This removes the tracked supplement, its saved plan, and linked intake history."
        ),
        rows=(
            (Button("Remove supplement", f"rc:{token}:9"),),
            (Button("Cancel", f"o:{token}:9"),),
        ),
    )

    projected = project_v02_screen(raw, surface="supplement")

    assert projected.text.startswith("Удалить Example?")
    assert "сохранённый план" in projected.text
    assert "связанная история приёма" in projected.text
    assert "Служебные строки" in projected.text
    assert "Другие отслеживаемые добавки не изменятся" in projected.text
    assert _callbacks(projected) == [f"rc:{token}:9", f"o:{token}:9"]


def test_history_uses_non_mutating_confirmation_route_before_correction_write() -> None:
    raw = Screen(
        text=(
            "History\n\n"
            "• Example: 1 capsule — taken\n\n"
            "History is an audit/correction view. Reminder delivery is not intake proof."
        ),
        rows=(
            (Button("Correct Example", "k120c:occ-1:3"),),
            (Button("Today", "k120today"),),
        ),
    )

    projected = project_v02_screen(raw, surface="history")
    assert "k120q:occ-1:3" in _callbacks(projected)
    assert "k120c:occ-1:3" not in _callbacks(projected)

    occurrence = OccurrenceRecord(
        occurrence_id="occ-1",
        instance_id="instance-1",
        name="Example",
        unit_id="unit-1",
        unit_label="capsule",
        quantity=Decimal("1"),
        schedule_kind="bucket",
        schedule_label="morning",
        timezone="Europe/Helsinki",
        local_date=date(2026, 9, 20),
        scheduled_local_time=time(8, 0),
        scheduled_at=datetime(2026, 9, 20, 5, 0, tzinfo=UTC),
        due_at=datetime(2026, 9, 20, 5, 0, tzinfo=UTC),
        state="taken",
        later_count=0,
        revision=3,
    )

    class _PreviewOnlyStore:
        def __init__(self) -> None:
            self.occurrence_reads = 0

        def ensure_user(self, telegram_user_id: int) -> UUID:
            assert telegram_user_id == 169003
            return UUID(int=1)

        def occurrence(self, user_id: UUID, occurrence_id: str) -> OccurrenceRecord:
            assert user_id == UUID(int=1)
            assert occurrence_id == "occ-1"
            self.occurrence_reads += 1
            return occurrence

    store = _PreviewOnlyStore()
    controller = KIR120Controller(store)  # type: ignore[arg-type]
    preview = controller.callback(
        169003,
        "k120q:occ-1:3",
        action_key="cb:preview-only",
        now=datetime(2026, 9, 20, 6, 0, tzinfo=UTC),
    )

    assert store.occurrence_reads == 1
    assert "История не удаляется молча" in preview.text
    assert _callbacks(preview) == ["k120c:occ-1:3", "k120h"]


def test_profile_projection_preserves_jit_minimization_without_new_health_fields() -> None:
    raw = Screen(
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
        ),
    )

    projected = project_v02_screen(raw, surface="profile")

    assert "только технические настройки" in projected.text
    assert "не собираются заранее" in projected.text
    assert "governed" not in projected.text.lower()
    assert "k120today" in _callbacks(projected)
    assert not any(word in projected.text.lower() for word in ("лекарств", "беремен", "диагноз"))


def test_timezone_validation_hides_iana_jargon_and_preserves_example() -> None:
    raw = Screen(
        text="I don’t recognize that IANA timezone. Example: Europe/Helsinki.",
        rows=((Button("Profile", "pf"),),),
    )

    projected = project_v02_screen(raw, surface="profile")

    assert projected.text == "Не удалось распознать часовой пояс. Пример: Europe/Helsinki."
    assert "IANA" not in projected.text
    assert "Europe/Helsinki" in projected.text
    assert "pf" in _callbacks(projected)


def test_fail_closed_and_no_supported_rule_copy_survive_projection() -> None:
    safety_text = (
        "Магний\n"
        "Статус: Не могу оценить\n"
        "Вывод удержан: персональный вывод о безопасности не сделан.\n"
        "Важно: неизвестная применимость не означает отсутствие риска."
    )
    safety = project_v02_screen(
        Screen(
            text=safety_text,
            rows=((Button("Почему / источники", "k122src:abc123"),),),
        ),
        surface="safety",
    )
    assert safety_text in safety.text
    assert "безопасно для вас" not in safety.text.lower()
    assert "k122src:abc123" in _callbacks(safety)

    rules_text = (
        "Планирование\n\n"
        "Поддерживаемое правило не найдено. "
        "Это не подтверждение совместимости или безопасности.\n\n"
        "Отсутствие правила не означает, что сочетание безопасно."
    )
    rules = project_v02_screen(
        Screen(
            text=rules_text,
            rows=((Button("Источники правил", "k122why:abc123"),),),
        ),
        surface="rules",
    )
    assert rules.text == rules_text
    assert "не подтверждение совместимости или безопасности" in rules.text
    assert "k122why:abc123" in _callbacks(rules)


def test_stale_and_ambiguous_states_remain_explicit_and_recoverable() -> None:
    stale = project_v02_screen(
        Screen(
            text=(
                "This action is out of date, so I didn’t apply it. "
                "Open the current supplement state and try again."
            ),
            rows=((Button("My supplements", "ls"),),),
        ),
        surface="supplement",
    )
    assert "устарело" in stale.text or "устарел" in stale.text
    assert "не применил" in stale.text
    assert _callbacks(stale) == ["ls"]

    ambiguous_text = (
        "Нужно подтвердить\n\nЕсть несколько вариантов. Ни один вариант не выбран автоматически."
    )
    ambiguous = project_v02_screen(
        Screen(
            text=ambiguous_text,
            rows=(
                (Button("Вариант A", "candidate:a:2"),),
                (Button("Вариант B", "candidate:b:2"),),
            ),
        ),
        surface="composition",
    )
    assert ambiguous.text == ambiguous_text
    assert _callbacks(ambiguous) == ["candidate:a:2", "candidate:b:2"]


def test_governed_scientific_body_is_not_paraphrased_by_russian_shell() -> None:
    governed = (
        "Vitamin B12\n"
        "Status: CANNOT_ASSESS\n"
        "Personal applicability is unresolved; an adult/default context was not assumed."
    )
    raw = Screen(
        text=governed,
        rows=(
            (Button("Reference values", "k146r:vitamin_b12"),),
            (Button("Why / Sources", "k146s:vitamin_b12"),),
            (Button("Back", "k146list"),),
        ),
    )

    projected = project_v02_scientific_shell(raw)

    assert projected.text == governed
    assert _labels(projected) == ["Справочные значения", "Почему? / Источники", "Назад"]
    assert _callbacks(projected) == [
        "k146r:vitamin_b12",
        "k146s:vitamin_b12",
        "k146list",
    ]
