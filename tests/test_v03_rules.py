from vitaminbot.application.nutrition import (
    PlanningRulesView,
    PlanningRuleView,
    RuleSourcesStatus,
    RuleSourcesView,
    RuleSourceView,
)
from vitaminbot.nutrition.rules import (
    EventRelation,
    RuleEngineGlobalStatus,
    RuleStatus,
    RuleType,
    RuleWarning,
)
from vitaminbot.presentation.telegram import render_rule_sources, render_rules


def test_matched_rule_renderer_keeps_preference_non_medical() -> None:
    view = PlanningRulesView(
        global_status=RuleEngineGlobalStatus.READY,
        global_reasons=(),
        results=(
            PlanningRuleView(
                item_names=("Calcium", "Iron"),
                status=RuleStatus.MATCHED_PREFERENCE,
                rule_type=RuleType.AVOID_SAME_EVENT,
                event_relation=EventRelation.AVOID_SAME_EVENT,
                warnings=(
                    RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY,
                    RuleWarning.NULL_GAP_MUST_REMAIN_NULL,
                    RuleWarning.NO_PERSONALIZED_DOSE,
                ),
            ),
        ),
        source_revision="abc123def456",
        ruleset_version="rules-v1",
    )

    screen = render_rules(view)

    assert screen.text.startswith("Планирование")
    assert "Calcium, Iron: предпочтение — не размещать в одном приёме." in screen.text
    assert "Точный интервал не установлен." in screen.text
    assert "Это предпочтение, а не медицинская необходимость." in screen.text
    assert "Правило не создаёт и не изменяет персональную дозу." in screen.text
    assert "биологическое преимущество времени суток" in screen.text
    callbacks = [button.callback_data for row in screen.rows for button in row]
    assert callbacks == [
        "k122why:abc123def456",
        "k120today",
        "k120p",
        "k122tot",
    ]
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_no_supported_rule_is_not_rendered_as_safety_clearance() -> None:
    view = PlanningRulesView(
        global_status=RuleEngineGlobalStatus.READY,
        global_reasons=(),
        results=(
            PlanningRuleView(
                item_names=("Magnesium",),
                status=RuleStatus.NO_SUPPORTED_RULE_FOUND,
                rule_type=RuleType.NO_SUPPORTED_RULE,
                event_relation=None,
                warnings=(RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE,),
            ),
        ),
        source_revision="feedbeef1234",
        ruleset_version="rules-v1",
    )

    screen = render_rules(view)

    assert "поддерживаемое правило не найдено" in screen.text
    assert "не подтверждает совместимость или безопасность" in screen.text
    assert "Отсутствие правила не означает, что сочетание безопасно." in screen.text


def test_high_risk_global_status_withholds_automatic_planning() -> None:
    view = PlanningRulesView(
        global_status=RuleEngineGlobalStatus.WITHHELD_HIGH_RISK_CONTEXT,
        global_reasons=(),
        results=(),
        source_revision="deadbeef1234",
        ruleset_version="rules-v1",
    )

    screen = render_rules(view)

    assert "Автоматическое планирование остановлено" in screen.text
    assert "Это не вывод о безопасности." in screen.text


def test_rule_sources_are_revision_bound_public_provenance() -> None:
    ready = RuleSourcesView(
        status=RuleSourcesStatus.READY,
        ruleset_version="rules-v1",
        sources=(
            RuleSourceView(
                title="Rule source",
                authority="Example authority",
                jurisdiction_note="Example scope",
                version_label="2026",
                retrieved_on="2026-10-01",
                locator="section 3",
                source_url="https://example.test/rule",
            ),
        ),
    )
    screen = render_rule_sources(ready)

    assert "Набор правил: rules-v1." in screen.text
    assert "Rule source" in screen.text
    assert "Example authority" in screen.text
    assert "section 3" in screen.text
    assert "https://example.test/rule" in screen.text
    assert "source_key" not in screen.text
    assert [button.callback_data for row in screen.rows for button in row] == ["k122rules"]

    stale = render_rule_sources(
        RuleSourcesView(
            status=RuleSourcesStatus.STALE,
            ruleset_version="rules-v1",
        )
    )
    assert "Экран источников правил устарел" in stale.text
    assert "Старые источники не были показаны" in stale.text
    assert [button.callback_data for row in stale.rows for button in row] == ["k122rules"]


def test_empty_rule_sources_do_not_claim_compatibility() -> None:
    screen = render_rule_sources(
        RuleSourcesView(
            status=RuleSourcesStatus.READY,
            ruleset_version="rules-v1",
        )
    )

    assert "подтверждённое правило с источником не применилось" in screen.text
    assert "Это не подтверждение совместимости или безопасности." in screen.text
