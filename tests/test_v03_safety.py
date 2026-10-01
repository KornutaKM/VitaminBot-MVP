from vitaminbot.application.nutrition import (
    SafetyContributorView,
    SafetyEntryView,
    SafetySourcesStatus,
    SafetySourcesView,
    SafetySourceView,
    SafetyView,
)
from vitaminbot.application.safety_envelope import (
    SafetyEvidenceState,
    SafetyStatus,
)
from vitaminbot.presentation.telegram import render_safety, render_safety_sources


def test_fail_closed_safety_renderer_preserves_governed_fields() -> None:
    view = SafetyView(
        entries=(
            SafetyEntryView(
                subject_name="Магний",
                status=SafetyStatus.CANNOT_ASSESS,
                classification="reference_applicability",
                known_facts=("Подтверждённый дневной итог: 100000 мкг.",),
                unknown_facts=("Не установлена точная применимость справочного значения.",),
                withheld_conclusion="Персональный вывод о безопасности не сделан.",
                warnings=("Неизвестная применимость не означает отсутствие риска.",),
                resolution_path="Нужен подтверждённый контекст применимости.",
                escalation_path=None,
                reference_type="UL (верхний допустимый уровень)",
                relation=None,
                evidence_state=SafetyEvidenceState.MISSING,
                contributors=(
                    SafetyContributorView(
                        name="Magnesium Citrate",
                        normalized_amount="100000 мкг",
                    ),
                ),
            ),
        ),
        source_revision="abc123def456",
        has_applicability_profile=True,
        iron_scope_token="0123456789abcdef",
    )

    screen = render_safety(view)

    assert screen.text.startswith("Справочные значения и ограничения")
    assert "Здесь нет персональной рекомендации по дозе." in screen.text
    assert "Статус: Не могу оценить" in screen.text
    assert "Вывод удержан: Персональный вывод о безопасности не сделан." in screen.text
    assert "Неизвестно / неоднозначно:" in screen.text
    assert "Подтверждённый дневной итог: 100000 мкг." in screen.text
    assert "• Magnesium Citrate — 100000 мкг" in screen.text
    assert "Важно: Неизвестная применимость не означает отсутствие риска." in screen.text
    assert "Как уточнить: Нужен подтверждённый контекст применимости." in screen.text

    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert callbacks == [
        "k122src:abc123def456",
        "k122tot",
        "k120today",
        "k174profile",
        "k174iron:0123456789abcdef",
    ]
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_supported_safety_renderer_shows_reference_relation_without_new_conclusion() -> None:
    view = SafetyView(
        entries=(
            SafetyEntryView(
                subject_name="Витамин C",
                status=SafetyStatus.INFORMATION,
                classification="reference_comparison",
                known_facts=(
                    "Подтверждённый дневной итог: 100 мг.",
                    "UL: 1000 мг/день.",
                ),
                unknown_facts=(),
                withheld_conclusion=None,
                warnings=(
                    "Сопоставление само по себе не устанавливает персональную безопасность.",
                ),
                resolution_path=None,
                escalation_path=None,
                reference_type="UL (верхний допустимый уровень)",
                relation="below",
                evidence_state=SafetyEvidenceState.SUPPORTED,
                contributors=(),
            ),
        ),
        source_revision="feedbeef1234",
        has_applicability_profile=False,
    )

    screen = render_safety(view)

    assert "Статус: Информация" in screen.text
    assert "Тип справочного значения: UL (верхний допустимый уровень)" in screen.text
    assert "Сопоставление: дневной итог ниже справочного значения." in screen.text
    assert "безопасно для вас" not in screen.text.lower()


def test_safety_sources_are_public_revision_bound_provenance() -> None:
    ready = SafetySourcesView(
        status=SafetySourcesStatus.READY,
        dataset_version="eu-efsa-test-v1",
        sources=(
            SafetySourceView(
                title="Reference source",
                source_url="https://example.test/reference",
                version="2026",
                source_locator="section 4",
                jurisdiction="EU",
                reference_type="UL",
                applicability_status="match",
                scope_note="Adults in source scope",
            ),
        ),
    )

    screen = render_safety_sources(ready)

    assert "Набор справочных данных: eu-efsa-test-v1." in screen.text
    assert "Reference source" in screen.text
    assert "section 4" in screen.text
    assert "применимость: запись совпала с текущим контекстом" in screen.text
    assert "https://example.test/reference" in screen.text
    assert "source_key" not in screen.text
    assert [button.callback_data for row in screen.rows for button in row] == ["k122safe"]

    stale = render_safety_sources(
        SafetySourcesView(
            status=SafetySourcesStatus.STALE,
            dataset_version="eu-efsa-test-v1",
        )
    )
    assert "Экран источников устарел" in stale.text
    assert "Старые источники не были показаны как относящиеся к новому расчёту." in stale.text
    assert [button.callback_data for row in stale.rows for button in row] == ["k122safe"]


def test_safety_sources_empty_match_does_not_invent_reference() -> None:
    screen = render_safety_sources(
        SafetySourcesView(
            status=SafetySourcesStatus.READY,
            dataset_version="eu-efsa-test-v1",
        )
    )

    assert "Совпавшего справочного источника" in screen.text
    assert "Значение не было угадано или подставлено." in screen.text
