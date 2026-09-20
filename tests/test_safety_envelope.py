from __future__ import annotations

import pytest

from vitaminbot.application.safety_envelope import (
    SafetyComparisonContext,
    SafetyEnvelope,
    SafetyEvidenceState,
    SafetyFact,
    SafetyStatus,
    render_safety_envelopes,
)


def _cannot_assess() -> SafetyEnvelope:
    return SafetyEnvelope(
        subject_name="Магний",
        status=SafetyStatus.CANNOT_ASSESS,
        classification="reference_applicability",
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
        resolution_path="Нужно подтвердить требуемый контекст применимости.",
        escalation_path=None,
        non_droppable_warnings=("Неизвестная применимость не означает отсутствие риска.",),
        comparison_context=SafetyComparisonContext(
            reference_type="UL (верхний допустимый уровень)",
            reference_record_id=None,
            amount_basis="elemental",
            equivalence_basis=None,
            relation=None,
            dataset_version="test-dataset",
        ),
        contributors=(),
        evidence_state=SafetyEvidenceState.MISSING,
        context_revision="kir122:test",
    )


def test_fail_closed_envelope_requires_withheld_resolution_and_warning() -> None:
    base = _cannot_assess()

    with pytest.raises(ValueError, match="withheld_conclusion"):
        SafetyEnvelope(
            subject_name=base.subject_name,
            status=base.status,
            classification=base.classification,
            known_facts=base.known_facts,
            unknown_or_ambiguous=base.unknown_or_ambiguous,
            withheld_conclusion=None,
            provenance=base.provenance,
            resolution_path=base.resolution_path,
            escalation_path=base.escalation_path,
            non_droppable_warnings=base.non_droppable_warnings,
            comparison_context=base.comparison_context,
            contributors=base.contributors,
            evidence_state=base.evidence_state,
            context_revision=base.context_revision,
        )

    with pytest.raises(ValueError, match="resolution_path"):
        SafetyEnvelope(
            subject_name=base.subject_name,
            status=base.status,
            classification=base.classification,
            known_facts=base.known_facts,
            unknown_or_ambiguous=base.unknown_or_ambiguous,
            withheld_conclusion=base.withheld_conclusion,
            provenance=base.provenance,
            resolution_path=None,
            escalation_path=base.escalation_path,
            non_droppable_warnings=base.non_droppable_warnings,
            comparison_context=base.comparison_context,
            contributors=base.contributors,
            evidence_state=base.evidence_state,
            context_revision=base.context_revision,
        )

    with pytest.raises(ValueError, match="non-droppable warning"):
        SafetyEnvelope(
            subject_name=base.subject_name,
            status=base.status,
            classification=base.classification,
            known_facts=base.known_facts,
            unknown_or_ambiguous=base.unknown_or_ambiguous,
            withheld_conclusion=base.withheld_conclusion,
            provenance=base.provenance,
            resolution_path=base.resolution_path,
            escalation_path=base.escalation_path,
            non_droppable_warnings=(),
            comparison_context=base.comparison_context,
            contributors=base.contributors,
            evidence_state=base.evidence_state,
            context_revision=base.context_revision,
        )


def test_renderer_places_fail_closed_state_before_confirmed_facts_and_keeps_warning() -> None:
    rendered = render_safety_envelopes((_cannot_assess(),))

    status_index = rendered.index("Статус: Не могу оценить")
    withheld_index = rendered.index("Вывод удержан:")
    known_index = rendered.index("Подтверждено:")
    warning_index = rendered.index("Важно: Неизвестная применимость")

    assert status_index < withheld_index < known_index
    assert warning_index > status_index
    assert "Персональный вывод о безопасности не сделан." in rendered
    assert "взросл" not in rendered.lower()


def test_supported_reference_comparison_requires_provenance() -> None:
    with pytest.raises(ValueError, match="requires provenance"):
        SafetyEnvelope(
            subject_name="DHA",
            status=SafetyStatus.INFORMATION,
            classification="reference_comparison",
            known_facts=(),
            unknown_or_ambiguous=(),
            withheld_conclusion=None,
            provenance=(),
            resolution_path=None,
            escalation_path=None,
            non_droppable_warnings=(
                "Сопоставление само по себе не устанавливает персональную безопасность.",
            ),
            comparison_context=SafetyComparisonContext(
                reference_type="SAFE_LEVEL (отдельный тип, не UL)",
                reference_record_id="record:test",
                amount_basis="analyte",
                equivalence_basis=None,
                relation="below",
                dataset_version="test-dataset",
            ),
            contributors=(),
            evidence_state=SafetyEvidenceState.SUPPORTED,
            context_revision="kir122:test",
        )
