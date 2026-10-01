from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from vitaminbot.nutrition.rules import (
    EventRelation,
    GlobalReason,
    RuleEngineGlobalStatus,
    RuleStatus,
    RuleType,
    RuleWarning,
)


@dataclass(frozen=True, slots=True)
class PlanningRuleView:
    item_names: tuple[str, ...]
    status: RuleStatus
    rule_type: RuleType
    event_relation: EventRelation | None
    warnings: tuple[RuleWarning, ...]


@dataclass(frozen=True, slots=True)
class PlanningRulesView:
    global_status: RuleEngineGlobalStatus
    global_reasons: tuple[GlobalReason, ...]
    results: tuple[PlanningRuleView, ...]
    source_revision: str
    ruleset_version: str


class RuleSourcesStatus(StrEnum):
    READY = "ready"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class RuleSourceView:
    title: str
    authority: str
    jurisdiction_note: str
    version_label: str
    retrieved_on: str
    locator: str
    source_url: str


@dataclass(frozen=True, slots=True)
class RuleSourcesView:
    status: RuleSourcesStatus
    ruleset_version: str
    sources: tuple[RuleSourceView, ...] = ()
