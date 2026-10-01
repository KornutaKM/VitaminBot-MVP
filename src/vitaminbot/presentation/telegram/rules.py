from __future__ import annotations

from vitaminbot.application.nutrition import (
    PlanningRulesView,
    RuleSourcesStatus,
    RuleSourcesView,
)
from vitaminbot.application.supplements import Button, Screen
from vitaminbot.nutrition.rules import (
    EventRelation,
    RuleEngineGlobalStatus,
    RuleStatus,
    RuleType,
    RuleWarning,
)

_WARNING_TEXT = {
    RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY: (
        "Это предпочтение, а не медицинская необходимость."
    ),
    RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE: (
        "Отсутствие поддерживаемого правила не подтверждает совместимость или безопасность."
    ),
    RuleWarning.NULL_GAP_MUST_REMAIN_NULL: (
        "Точный интервал не установлен и не должен быть придуман."
    ),
    RuleWarning.NO_PERSONALIZED_DOSE: ("Правило не создаёт и не изменяет персональную дозу."),
    RuleWarning.FIXED_COMBINATION_NOT_SPLITTABLE: (
        "Неделимая комбинация не должна автоматически разноситься по компонентам."
    ),
    RuleWarning.USER_PREFERENCE_NOT_SCIENTIFIC_EVIDENCE: (
        "Пользовательская настройка времени не является научным доказательством."
    ),
    RuleWarning.MEDICATION_NO_RESULT_NOT_NO_INTERACTION: (
        "Отсутствие результата по взаимодействию не означает отсутствие взаимодействия."
    ),
    RuleWarning.LLM_MUST_NOT_STRENGTHEN: (
        "Пояснение не должно усиливать вывод сверх подтверждённого правила."
    ),
}


def render_rules(view: PlanningRulesView) -> Screen:
    lines = ["Планирование", ""]

    if view.global_status is RuleEngineGlobalStatus.WITHHELD_HIGH_RISK_CONTEXT:
        lines.append(
            "Автоматическое планирование остановлено: текущий контекст требует "
            "отдельно подтверждённого правила. Это не вывод о безопасности."
        )
    elif not view.results:
        lines.append(
            "Недостаточно подтверждённых данных для доказательного правила планирования. "
            "Текущие Утро / День / Вечер остаются вашими организационными метками."
        )
    else:
        for result in view.results:
            label = ", ".join(result.item_names)
            if result.status is RuleStatus.MATCHED_PREFERENCE:
                if result.event_relation is EventRelation.AVOID_SAME_EVENT:
                    lines.append(
                        f"• {label}: предпочтение — не размещать в одном приёме. "
                        "Точный интервал не установлен. Это не медицинская необходимость."
                    )
                elif result.rule_type is RuleType.MEAL_CONTEXT:
                    lines.append(
                        f"• {label}: найдено доказательное предпочтение, связанное с едой. "
                        "Это предпочтение, а не обязательное медицинское указание."
                    )
                else:
                    lines.append(
                        f"• {label}: найдено доказательное предпочтение по распределению "
                        "уже запланированных единиц. Оно не создаёт новую дозу."
                    )
            elif result.status is RuleStatus.NO_SUPPORTED_RULE_FOUND:
                lines.append(
                    f"• {label}: поддерживаемое правило не найдено. "
                    "Это не подтверждение совместимости или безопасности."
                )
            elif result.status is RuleStatus.INSUFFICIENT_EVIDENCE:
                lines.append(
                    f"• {label}: данных недостаточно. "
                    "План автоматически не усиливается и не дополняется догадкой."
                )
            elif result.status is RuleStatus.CANNOT_OPTIMIZE_FIXED_COMBINATION:
                lines.append(
                    f"• {label}: состав одной единицы нельзя разнести по компонентам. "
                    "План не пытается разделить неделимую добавку."
                )
            else:
                lines.append(
                    f"• {label}: более приоритетный подтверждённый контекст не позволяет "
                    "автоматически применить это предпочтение."
                )

            lines.extend(f"  Важно: {_WARNING_TEXT[warning]}" for warning in result.warnings)

    lines.extend(
        [
            "",
            "Утро / День / Вечер — организационные метки пользователя. "
            "VitaminBot не выводит из них биологическое преимущество времени суток.",
            "Отсутствие правила не означает, что сочетание безопасно.",
        ]
    )
    return Screen(
        text="\n".join(lines),
        rows=(
            (Button("Источники правил", f"k122why:{view.source_revision}"),),
            (Button("Сегодня", "k120today"), Button("План", "k120p")),
            (Button("Итоги", "k122tot"),),
        ),
    )


def render_rule_sources(view: RuleSourcesView) -> Screen:
    if view.status is RuleSourcesStatus.STALE:
        return Screen(
            text=(
                "Экран источников правил устарел: состав или план уже изменились. "
                "Старые источники не были показаны как относящиеся к новому расчёту."
            ),
            rows=((Button("Обновить правила", "k122rules"),),),
        )

    lines = [
        "Почему / источники правил",
        "",
        f"Набор правил: {view.ruleset_version}.",
        "Источники принадлежат принятому детерминированному набору правил. "
        "Текст интерфейса не создаёт новые научные правила.",
    ]
    if not view.sources:
        lines.extend(
            [
                "",
                "Для текущего результата подтверждённое правило с источником не применилось.",
                "Это не подтверждение совместимости или безопасности.",
            ]
        )
    else:
        for source in view.sources:
            lines.extend(
                [
                    "",
                    f"• {source.title}",
                    f"  автор/организация: {source.authority}",
                    f"  область применимости источника: {source.jurisdiction_note}",
                    f"  версия: {source.version_label}",
                    f"  получен: {source.retrieved_on}",
                    f"  раздел/идентификатор: {source.locator}",
                    f"  {source.source_url}",
                ]
            )

    return Screen(
        text="\n".join(lines),
        rows=((Button("Назад к правилам", "k122rules"),),),
    )
