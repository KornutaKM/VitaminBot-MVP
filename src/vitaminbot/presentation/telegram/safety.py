from __future__ import annotations

from vitaminbot.application.nutrition import (
    SafetySourcesStatus,
    SafetySourcesView,
    SafetyView,
)
from vitaminbot.application.safety_envelope import SafetyStatus
from vitaminbot.application.supplements import Button, Screen

_STATUS_LABELS = {
    SafetyStatus.INFORMATION: "Информация",
    SafetyStatus.CANNOT_ASSESS: "Не могу оценить",
    SafetyStatus.NEEDS_CONFIRMATION: "Нужно подтверждение",
    SafetyStatus.CAUTION: "Нужна осторожная интерпретация",
    SafetyStatus.POTENTIAL_REFERENCE_LIMIT_CONCERN: "Возможный справочный сигнал",
    SafetyStatus.INTERACTION_REVIEW: "Нужна проверка взаимодействия",
    SafetyStatus.HIGH_RISK_CONTEXT_REVIEW: "Нужна проверка контекста",
}

_RELATION_LABELS = {
    "below": "ниже",
    "equal": "равен",
    "above": "выше",
}


def render_safety(view: SafetyView) -> Screen:
    lines = [
        "Проверка режима",
        "",
        "Справочная проверка подтверждённых данных. Здесь нет персональной рекомендации по дозе.",
    ]

    if not view.envelopes:
        lines.extend(
            [
                "",
                "Не могу оценить: для текущего режима нет сопоставимого справочного результата.",
            ]
        )

    for envelope in view.envelopes:
        lines.extend(
            [
                "",
                envelope.subject_name,
                f"Статус: {_STATUS_LABELS[envelope.status]}",
            ]
        )

        if envelope.comparison_context is not None:
            context = envelope.comparison_context
            lines.append(f"Справочный тип: {context.reference_type}")
            if context.relation is not None:
                lines.append(
                    "Сопоставление: подтверждённый дневной итог "
                    f"{_RELATION_LABELS[context.relation]} справочного значения."
                )

        if envelope.known_facts:
            lines.append("Подтверждено:")
            lines.extend(f"• {fact.value}" for fact in envelope.known_facts)

        if envelope.unknown_or_ambiguous:
            lines.append("Неизвестно / неоднозначно:")
            lines.extend(f"• {fact.value}" for fact in envelope.unknown_or_ambiguous)

        if envelope.withheld_conclusion is not None:
            lines.append(f"Вывод удержан: {envelope.withheld_conclusion}")

        for warning in envelope.non_droppable_warnings:
            lines.append(f"Важно: {warning}")

        if envelope.resolution_path is not None:
            lines.append(f"Как уточнить: {envelope.resolution_path}")
        if envelope.escalation_path is not None:
            lines.append(f"Куда обратиться: {envelope.escalation_path}")

    revision = _short_revision(view.context_revision)
    rows: list[tuple[Button, ...]] = [
        (Button("Почему / источники", f"k122src:{revision}"),),
        (Button("Итоги", "k122tot"), Button("Сегодня", "k120today")),
    ]
    if view.show_applicability_profile:
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
                "Экран устарел: состав, план или контекст применимости уже изменились. "
                "Старые источники не показаны как относящиеся к новому расчёту."
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
                "Совпавшего справочного источника для текущего контекста нет. "
                "Значение не было угадано или подставлено.",
            ]
        )
    else:
        for source in view.sources:
            lines.extend(
                [
                    "",
                    source.title,
                    f"Версия: {source.version}",
                    f"Раздел: {source.source_locator}",
                ]
            )
            if source.jurisdiction is not None:
                lines.append(f"Юрисдикция: {source.jurisdiction}")
            if source.reference_type is not None:
                lines.append(f"Тип: {source.reference_type}")
            if source.applicability_status == "match":
                lines.append("Применимость: совпадает с текущим подтверждённым контекстом")
            if source.scope_note is not None:
                lines.append(f"Ограничение: {source.scope_note}")
            lines.append(source.source_url)

    return Screen(
        text="\n".join(lines),
        rows=((Button("Назад к проверке", "k122safe"),),),
    )


def _short_revision(context_revision: str) -> str:
    return context_revision.removeprefix("kir122:")[:12]
