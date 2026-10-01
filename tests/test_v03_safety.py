from vitaminbot.application.nutrition import (
    SafetySourceItem,
    SafetySourcesStatus,
    SafetySourcesView,
    SafetyView,
)
from vitaminbot.application.safety_envelope import (
    SafetyComparisonContext,
    SafetyEnvelope,
    SafetyEvidenceState,
    SafetyFact,
    SafetyProvenance,
    SafetyStatus,
)
from vitaminbot.presentation.telegram import render_safety, render_safety_sources


def _envelope() -> SafetyEnvelope:
    return SafetyEnvelope(
        subject_name="Магний",
        status=SafetyStatus.CANNOT_ASSESS,
        classification="daily_exposure_comparison",
        known_facts=(
            SafetyFact(
                key="confirmed_daily_total",
                value="Подтверждённый дневной итог: 75000 мкг.",
            ),
        ),
        unknown_or_ambiguous=(
            SafetyFact(
                key="reference_applicability",
                value="Не установлена точная применимость справочного значения.",
            ),
        ),
        withheld_conclusion="Персональный вывод о безопасности не сделан.",
        provenance=(),
        resolution_path="Нужно подтвердить контекст применимости.",
        escalation_path=None,
        non_droppable_warnings=(
            "Неизвестная применимость не означает отсутствие риска.",
            "Справочное значение нельзя превращать в персональную дозу.",
        ),
        comparison_context=SafetyComparisonContext(
            reference_type="UL (верхний допустимый уровень)",
            reference_record_id=None,
            amount_basis="analyte",
            equivalence_basis=None,
            relation=None,
            dataset_version="efsa-test-v1",
        ),
        contributors=(),
        evidence_state=SafetyEvidenceState.MISSING,
        context_revision="kir122:abcdef1234567890",
    )


def test_safety_renderer_preserves_fail_closed_fields_and_revision_bound_sources() -> None:
    view = SafetyView(
        envelopes=(_envelope(),),
        context_revision="kir122:abcdef1234567890",
        show_applicability_profile=True,
        iron_scope_token="0123456789abcdef",
    )

    screen = render_safety(view)

    assert screen.text.startswith("Проверка режима")
    assert "Статус: Не могу оценить" in screen.text
    assert "Персональный вывод о безопасности не сделан." in screen.text
    assert "Неизвестная применимость не означает отсутствие риска." in screen.text
    assert "Справочное значение нельзя превращать в персональную дозу." in screen.text
    assert "Нужно подтвердить контекст применимости." in screen.text

    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert callbacks == [
        "k122src:abcdef123456",
        "k122tot",
        "k120today",
        "k174profile",
        "k174iron:0123456789abcdef",
    ]
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_safety_renderer_keeps_supported_reference_relation_explicit() -> None:
    envelope = SafetyEnvelope(
        subject_name="Витамин D",
        status=SafetyStatus.INFORMATION,
        classification="reference_comparison",
        known_facts=(
            SafetyFact(
                key="confirmed_daily_total",
                value="Подтверждённый дневной итог: 10 мкг.",
            ),
        ),
        unknown_or_ambiguous=(),
        withheld_conclusion=None,
        provenance=(
            SafetyProvenance(
                source_key="efsa-vitamin-d",
                title="EFSA vitamin D opinion",
                source_url="https://example.test/efsa-vitamin-d",
                version="v1",
                source_locator="Table 1",
                jurisdiction="EU",
                reference_type="UL",
                applicability_status="match",
            ),
        ),
        resolution_path=None,
        escalation_path=None,
        non_droppable_warnings=(
            "Сопоставление само по себе не устанавливает персональную безопасность.",
        ),
        comparison_context=SafetyComparisonContext(
            reference_type="UL (верхний допустимый уровень)",
            reference_record_id="record-vitamin-d",
            amount_basis="analyte",
            equivalence_basis=None,
            relation="below",
            dataset_version="efsa-test-v1",
        ),
        contributors=(),
        evidence_state=SafetyEvidenceState.SUPPORTED,
        context_revision="context-1234567890",
    )

    screen = render_safety(
        SafetyView(
            envelopes=(envelope,),
            context_revision="context-1234567890",
            show_applicability_profile=False,
        )
    )

    assert "Сопоставление: подтверждённый дневной итог ниже справочного значения." in screen.text
    assert "Сопоставление само по себе не устанавливает персональную безопасность." in screen.text
    assert "безопасно для вас" not in screen.text.lower()


def test_safety_sources_renderer_shows_only_typed_provenance_fields() -> None:
    view = SafetySourcesView(
        status=SafetySourcesStatus.READY,
        dataset_version="efsa-test-v1",
        sources=(
            SafetySourceItem(
                source_key="efsa-magnesium",
                title="EFSA magnesium opinion",
                source_url="https://example.test/efsa-magnesium",
                version="2026-01",
                source_locator="Section 3.2",
                jurisdiction="EU",
                reference_type="UL",
                applicability_status="match",
                scope_note="Supplemental sources only",
            ),
        ),
    )

    screen = render_safety_sources(view)

    assert screen.text.startswith("Почему / источники")
    assert "Набор справочных данных: efsa-test-v1." in screen.text
    assert "EFSA magnesium opinion" in screen.text
    assert "Section 3.2" in screen.text
    assert "Применимость: совпадает с текущим подтверждённым контекстом" in screen.text
    assert "https://example.test/efsa-magnesium" in screen.text
    assert [button.callback_data for row in screen.rows for button in row] == ["k122safe"]


def test_stale_safety_sources_never_render_old_provenance() -> None:
    screen = render_safety_sources(
        SafetySourcesView(
            status=SafetySourcesStatus.STALE,
            dataset_version="efsa-test-v1",
            sources=(
                SafetySourceItem(
                    source_key="must-not-render",
                    title="Old source",
                    source_url="https://example.test/old",
                    version="old",
                    source_locator="old",
                    jurisdiction=None,
                    reference_type=None,
                    applicability_status=None,
                    scope_note=None,
                ),
            ),
        )
    )

    assert "Экран устарел" in screen.text
    assert "Old source" not in screen.text
    assert "https://example.test/old" not in screen.text
    assert [button.callback_data for row in screen.rows for button in row] == ["k122safe"]
