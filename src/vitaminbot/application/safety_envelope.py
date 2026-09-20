from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SafetyStatus(StrEnum):
    INFORMATION = "information"
    CANNOT_ASSESS = "cannot_assess"
    NEEDS_CONFIRMATION = "needs_confirmation"
    CAUTION = "caution"
    POTENTIAL_REFERENCE_LIMIT_CONCERN = "potential_reference_limit_concern"
    INTERACTION_REVIEW = "interaction_review"
    HIGH_RISK_CONTEXT_REVIEW = "high_risk_context_review"


class SafetyEvidenceState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    PROVENANCE_FAILURE = "provenance_failure"


@dataclass(frozen=True, slots=True)
class SafetyFact:
    key: str
    value: str

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.value.strip():
            raise ValueError("safety fact key/value must not be blank")


@dataclass(frozen=True, slots=True)
class SafetyProvenance:
    source_key: str
    title: str
    source_url: str
    version: str
    source_locator: str

    def __post_init__(self) -> None:
        for value in (
            self.source_key,
            self.title,
            self.source_url,
            self.version,
            self.source_locator,
        ):
            if not value.strip():
                raise ValueError("safety provenance fields must not be blank")


@dataclass(frozen=True, slots=True)
class SafetyComparisonContext:
    reference_type: str
    reference_record_id: str | None
    amount_basis: str
    equivalence_basis: str | None
    relation: str | None
    dataset_version: str

    def __post_init__(self) -> None:
        if not self.reference_type.strip():
            raise ValueError("reference_type must not be blank")
        if not self.amount_basis.strip():
            raise ValueError("amount_basis must not be blank")
        if not self.dataset_version.strip():
            raise ValueError("dataset_version must not be blank")
        if self.reference_record_id is not None and not self.reference_record_id.strip():
            raise ValueError("reference_record_id must not be blank when present")
        if self.relation not in {None, "below", "equal", "above"}:
            raise ValueError("unsupported comparison relation")


@dataclass(frozen=True, slots=True)
class SafetyContributor:
    tracked_instance_id: str
    display_name: str
    normalized_amount: str

    def __post_init__(self) -> None:
        if not self.tracked_instance_id.strip():
            raise ValueError("tracked_instance_id must not be blank")
        if not self.display_name.strip():
            raise ValueError("display_name must not be blank")
        if not self.normalized_amount.strip():
            raise ValueError("normalized_amount must not be blank")


@dataclass(frozen=True, slots=True)
class SafetyEnvelope:
    subject_name: str
    status: SafetyStatus
    classification: str
    known_facts: tuple[SafetyFact, ...]
    unknown_or_ambiguous: tuple[SafetyFact, ...]
    withheld_conclusion: str | None
    provenance: tuple[SafetyProvenance, ...]
    resolution_path: str | None
    escalation_path: str | None
    non_droppable_warnings: tuple[str, ...]
    comparison_context: SafetyComparisonContext | None
    contributors: tuple[SafetyContributor, ...]
    evidence_state: SafetyEvidenceState
    context_revision: str

    def __post_init__(self) -> None:
        if not self.subject_name.strip():
            raise ValueError("safety subject_name must not be blank")
        if not self.classification.strip():
            raise ValueError("safety classification must not be blank")
        if not self.context_revision.strip():
            raise ValueError("safety context_revision must not be blank")
        if any(not warning.strip() for warning in self.non_droppable_warnings):
            raise ValueError("non-droppable warnings must not be blank")

        fail_closed = self.status in {
            SafetyStatus.CANNOT_ASSESS,
            SafetyStatus.NEEDS_CONFIRMATION,
            SafetyStatus.INTERACTION_REVIEW,
            SafetyStatus.HIGH_RISK_CONTEXT_REVIEW,
        }
        if fail_closed:
            if self.withheld_conclusion is None or not self.withheld_conclusion.strip():
                raise ValueError("fail-closed safety envelope requires withheld_conclusion")
            if self.resolution_path is None or not self.resolution_path.strip():
                raise ValueError("fail-closed safety envelope requires resolution_path")
            if not self.non_droppable_warnings:
                raise ValueError("fail-closed safety envelope requires a non-droppable warning")

        if self.comparison_context is not None and self.evidence_state is SafetyEvidenceState.SUPPORTED:
            if not self.provenance:
                raise ValueError("supported reference comparison requires provenance")

        if self.status is SafetyStatus.POTENTIAL_REFERENCE_LIMIT_CONCERN:
            if self.comparison_context is None or not self.provenance:
                raise ValueError("reference-limit concern requires comparison context and provenance")
            if not self.non_droppable_warnings:
                raise ValueError("reference-limit concern requires non-droppable warning")


_STATUS_LABELS = {
    SafetyStatus.INFORMATION: "Информация",
    SafetyStatus.CANNOT_ASSESS: "Не могу оценить",
    SafetyStatus.NEEDS_CONFIRMATION: "Нужно подтверждение",
    SafetyStatus.CAUTION: "Нужна осторожная интерпретация",
    SafetyStatus.POTENTIAL_REFERENCE_LIMIT_CONCERN: "Возможное превышение справочного предела",
    SafetyStatus.INTERACTION_REVIEW: "Нужна профессиональная проверка взаимодействия",
    SafetyStatus.HIGH_RISK_CONTEXT_REVIEW: "Нужна профессиональная проверка контекста",
}


def render_safety_envelopes(envelopes: tuple[SafetyEnvelope, ...]) -> str:
    """Render KIR-129 state without allowing prose to replace governed fields."""
    lines = [
        "Справочные значения и ограничения",
        "",
        "Здесь нет персональной рекомендации по дозе.",
    ]
    if not envelopes:
        lines.extend(
            [
                "",
                "Статус: Не могу оценить",
                "Для текущих подтверждённых итогов нет сопоставимого справочного результата.",
                "Персональный вывод о безопасности не сделан.",
            ]
        )
        return "\n".join(lines)

    for envelope in envelopes:
        lines.extend(
            [
                "",
                envelope.subject_name,
                f"Статус: {_STATUS_LABELS[envelope.status]}",
            ]
        )
        if envelope.withheld_conclusion is not None:
            lines.append(f"Вывод удержан: {envelope.withheld_conclusion}")

        if envelope.unknown_or_ambiguous:
            lines.append("Неизвестно / неоднозначно:")
            lines.extend(
                f"• {fact.value}" for fact in envelope.unknown_or_ambiguous
            )

        if envelope.known_facts:
            lines.append("Подтверждено:")
            lines.extend(f"• {fact.value}" for fact in envelope.known_facts)

        if envelope.comparison_context is not None:
            context = envelope.comparison_context
            lines.append(f"Тип справочного значения: {context.reference_type}")
            if context.relation is not None:
                relation = {
                    "below": "ниже",
                    "equal": "равен",
                    "above": "выше",
                }[context.relation]
                lines.append(f"Сопоставление: дневной итог {relation} справочного значения.")

        for warning in envelope.non_droppable_warnings:
            lines.append(f"Важно: {warning}")

        if envelope.resolution_path is not None:
            lines.append(f"Как уточнить: {envelope.resolution_path}")
        if envelope.escalation_path is not None:
            lines.append(f"Куда обратиться: {envelope.escalation_path}")

    return "\n".join(lines)
