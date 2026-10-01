from __future__ import annotations

from vitaminbot.application.nutrition import (
    SafetySourcesStatus,
    SafetySourcesView,
    SafetyView,
)
from vitaminbot.application.safety_envelope import (
    SafetyEvidenceState,
    SafetyStatus,
)
from vitaminbot.application.supplements import Button, Screen

_STATUS_LABELS = {
    SafetyStatus.INFORMATION: "Информация",
    SafetyStatus.CANNOT_ASSESS: "Не могу оценить",
    SafetyStatus.NEEDS_CONFIRMATION: "Нужно подтверждение",
    SafetyStatus.CAUTION: "Нужна осторожная интерпретация",
    SafetyStatus.POTENTIAL_REFERENCE_LIMIT_CONCERN: "Возможное превышение справочного предела",
    SafetyStatus.INTERACTION_REVIEW: "Нужна профессиональная проверка взаимодействия",
    SafetyStatus.HIGH_RISK_CONTEXT_REVIEW: "Нужна профессиональная проверка контекста",
}

_EVIDENCE_LABELS = {
    SafetyEvidenceState.SUPPORTED: "поддержано источником",
    SafetyEvidenceState.UNSUPPORTED: "не поддержано источником",
    SafetyEvidenceState.MISSING: "источник или применимость отсутствуют",
    SafetyEvidenceState.AMBIGUOUS: "неоднозначно",
    SafetyEvidenceState.PROVENANCE_FAILURE: "ошибка происхождения данных",
}

_RELATION_LABELS = {
    "below": "ниже",
    "equal": "равен",
    "above": "выше",
}


def render_safety(view: SafetyView) -> Screen:
    lines = [
        "Справочные значения и ограничения",
        "",
        "Здесь нет персональной рекомендации по дозе.",
    ]

    if not view.entries:
        lines.extend(
            [
                "",
                "Статус: Не могу оценить",
                "Для текущих подтверждённых итогов нет сопоставимого справочного результата.",
                "Персональный вывод о безопасности не сделан.",
            ]
        )

    for entry in view.entries:
        lines.extend(
            [
                "",
                entry.subject_name,
                f"Статус: {_STATUS_LABELS[entry.status]}",
                f"Состояние данных: {_EVIDENCE_LABELS[entry.evidence_state]}",
            ]
        )
        if entry.withheld_conclusion is not None:
            lines.append(f"Вывод удержан: {entry.withheld_conclusion}")

        if entry.unknown_facts:
            lines.append("Неизвестно / неоднозначно:")
            lines.extend(f"• {fact}" for fact in entry.unknown_facts)

        if entry.known_facts:
            lines.append("Подтверждено:")
            lines.extend(f"• {fact}" for fact in entry.known_facts)

        if entry.contributors:
            lines.append("Подтверждённые вклады:")
            lines.extend(
                f"• {contributor.name} — {contributor.normalized_amount}"
                for contributor in entry.contributors
            )

        if entry.reference_type is not None:
            lines.append(f"Тип справочного значения: {entry.reference_type}")
        if entry.relation is not None:
            relation = _RELATION_LABELS.get(entry.relation, entry.relation)
            lines.append(f"Сопоставление: дневной итог {relation} справочного значения.")

        lines.extend(f"Важно: {warning}" for warning in entry.warnings)

        if entry.resolution_path is not None:
            lines.append(f"Как уточнить: {entry.resolution_path}")
        if entry.escalation_path is not None:
            lines.append(f"Куда обратиться: {entry.escalation_path}")

    rows: list[tuple[Button, ...]] = [
        (Button("Почему / источники", f"k122src:{view.source_revision}"),),
        (Button("Итоги", "k122tot"), Button("Сегодня", "k120today")),
    ]
    if view.has_applicability_profile:
        rows.append((Button("Контекст применимости", "k174profile"),))
    if view.iron_scope_token is not None:
        rows.append(
            (
                Button(
                    "Контекст текущего приёма железа",
                    f"k174iron:{view.iron_scope_token}",
                ),
            )
        )
    return Screen(text="\n".join(lines), rows=tuple(rows))


def render_safety_sources(view: SafetySourcesView) -> Screen:
    if view.status is SafetySourcesStatus.STALE:
        return Screen(
            text=(
                "Экран источников устарел: состав, план или контекст применимости уже изменились. "
                "Старые источники не были показаны как относящиеся к новому расчёту."
            ),
            rows=((Button("Обновить проверку", "k122safe"),),),
        )

    lines = [
        "Почему / источники",
        "",
        f"Набор справочных данных: {view.dataset_version}.",
        "Показываются только источники записей, совпавших с текущим контекстом.",
    ]
    if not view.sources:
        lines.extend(
            [
                "",
                "Совпавшего справочного источника для текущего контекста нет.",
                "Значение не было угадано или подставлено.",
            ]
        )
    else:
        for source in view.sources:
            lines.extend(
                [
                    "",
                    f"• {source.title}",
                    f"  версия: {source.version}",
                    f"  раздел источника: {source.source_locator}",
                ]
            )
            if source.jurisdiction is not None:
                lines.append(f"  юрисдикция: {source.jurisdiction}")
            if source.reference_type is not None:
                lines.append(f"  тип справочного значения: {source.reference_type}")
            if source.applicability_status == "match":
                lines.append("  применимость: запись совпала с текущим контекстом")
            elif source.applicability_status is not None:
                lines.append(f"  применимость: {source.applicability_status}")
            if source.scope_note is not None:
                lines.append(f"  область/ограничение: {source.scope_note}")
            lines.append(f"  {source.source_url}")

    return Screen(
        text="\n".join(lines),
        rows=((Button("Назад к проверке", "k122safe"),),),
    )
