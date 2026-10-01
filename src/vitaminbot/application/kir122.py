from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID

from vitaminbot.application.kir116 import Button, Screen
from vitaminbot.application.kir174 import BoundApplicabilityContext, KIR174Controller
from vitaminbot.application.safety_envelope import (
    SafetyComparisonContext,
    SafetyContributor,
    SafetyEnvelope,
    SafetyEvidenceState,
    SafetyFact,
    SafetyProvenance,
    SafetyStatus,
    render_safety_envelopes,
)
from vitaminbot.application.views.composition import (
    CompositionNutrientOption,
    CompositionStep,
    CompositionSupplementView,
    CompositionView,
)
from vitaminbot.application.views.totals import (
    NutrientContributorView,
    NutrientTotalsView,
    RegimenTotalsStatus,
    RegimenTotalsView,
)
from vitaminbot.domain import (
    AmountBasis,
    AmountRecord,
    EvidenceStatus,
    IntakePlan,
    PlannedIntakeEvent,
    QuantityBasis,
    ResolutionStatus,
    ServingDefinition,
    SubjectKind,
    Unit,
)
from vitaminbot.nutrition import (
    DATASET_VERSION,
    EU_EFSA_REFERENCE_DATASET,
    RULESET_VERSION,
    BoundDailyAggregation,
    ComputationTrace,
    ComputedAmount,
    ConfirmedPlannedContribution,
    DailyAggregate,
    DailyAggregationResult,
    EventRelation,
    ExposureContext,
    ItemSourceKind,
    LookupStatus,
    NormalizationOutcome,
    PopulationProfile,
    ReferenceLifecycle,
    ReferenceQuery,
    ReferenceRecord,
    ReferenceStatus,
    ReferenceType,
    RuleEngineGlobalStatus,
    RuleEngineResult,
    RuleEvaluationContext,
    RuleStatus,
    RuleType,
    RuleWarning,
    SchedulingItem,
    UnresolvedReason,
    aggregate_daily_contributions,
    compare_amount_to_reference,
    evaluate_rule_engine,
    lookup_reference,
    normalize_per_consumption_unit,
    normalize_planned_daily_amount,
)
from vitaminbot.persistence.kir116 import (
    InvalidTransition as SupplementInvalidTransition,
    KIR116Store,
    RecordNotFound,
    StaleAction,
    SupplementRecord,
)
from vitaminbot.persistence.kir122 import (
    CompositionSession,
    DuplicateCompositionFact,
    InvalidCompositionState,
    KIR122Store,
    SnapshotAmount,
    SnapshotSupplement,
    StaleCompositionAction,
    VerticalSnapshot,
)

_COUNT_PATTERN = re.compile(r"^\s*(\d{1,12}(?:[.,]\d{1,6})?)\s*$")
_AMOUNT_PATTERN = re.compile(
    r"^\s*(\d{1,12}(?:[.,]\d{1,6})?)\s*(g|mg|ug|г|мг|мкг|µg|μg)\s*$",
    re.IGNORECASE,
)
_UNIT_ALIASES = {
    "g": "g",
    "г": "g",
    "mg": "mg",
    "мг": "mg",
    "ug": "ug",
    "мкг": "ug",
    "µg": "ug",
    "μg": "ug",
}
_RU_UNIT = {"g": "г", "mg": "мг", "ug": "мкг"}
_INTACT_UNIT_LABELS = frozenset({"capsule", "tablet", "softgel"})

# The selectable identity comes from accepted KIR-115 data at runtime. This table owns
# presentation names only; it is not a scientific conversion or reference-value source.
_RU_SUBSTANCE_NAMES = {
    "vitamin_d": "Витамин D",
    "vitamin_c": "Витамин C",
    "magnesium": "Магний",
    "zinc": "Цинк",
    "selenium": "Селен",
    "vitamin_b6": "Витамин B6",
    "vitamin_b12": "Витамин B12",
    "iron": "Железо",
    "calcium": "Кальций",
    "dha": "DHA",
}


@dataclass(frozen=True, slots=True)
class VerticalView:
    snapshot: VerticalSnapshot
    aggregation: DailyAggregationResult
    rule_result: RuleEngineResult
    item_names: dict[str, str]


class KIR122Controller:
    """Russian-first orchestration over accepted KIR-113/114/115/119 contracts."""

    def __init__(
        self,
        *,
        base_store: KIR116Store,
        store: KIR122Store,
        applicability_controller: KIR174Controller | None = None,
    ) -> None:
        self._base_store = base_store
        self._store = store
        self._applicability_controller = applicability_controller

    def composition_view(self, telegram_user_id: int) -> CompositionView:
        user_id = self._base_store.ensure_user(telegram_user_id)
        records = self._base_store.list_supplements(user_id)
        if not records:
            return CompositionView(step=CompositionStep.EMPTY)
        return CompositionView(
            step=CompositionStep.LIST,
            supplements=tuple(
                CompositionSupplementView(
                    instance_id=record.instance_id,
                    token=self._token(record.instance_id),
                    revision=record.revision,
                    name=record.name,
                    unit_label=record.unit_label,
                    serving_basis_type=record.serving_basis_type,
                    confirmed_count=len(
                        self._store.manual_substance_keys(user_id, record.instance_id)
                    ),
                )
                for record in records
            ),
        )

    def composition_text_view(
        self,
        telegram_user_id: int,
        text: str,
        *,
        action_key: str,
    ) -> CompositionView:
        user_id = self._base_store.ensure_user(telegram_user_id)
        base_session = self._base_store.get_session(user_id)
        if base_session is not None and base_session.state == "composition_serving_quantity":
            if base_session.target_instance_id is None:
                return CompositionView(step=CompositionStep.STALE)
            try:
                record = self._base_store.supplement(user_id, base_session.target_instance_id)
            except RecordNotFound:
                return CompositionView(step=CompositionStep.STALE)
            quantity = self._parse_positive_count(text)
            if quantity is None:
                return self._serving_quantity_view(record, input_error=True)
            try:
                updated = self._base_store.save_composition_serving_quantity(
                    user_id,
                    action_key,
                    quantity,
                )
            except (ValueError, SupplementInvalidTransition, StaleAction, RecordNotFound):
                return CompositionView(step=CompositionStep.STALE)
            return self._composition_nutrient_view(user_id, updated)

        session = self._store.session(user_id)
        if session is None or session.state != "amount_input":
            return CompositionView(step=CompositionStep.INVALID)

        parsed = self._parse_amount(text)
        if parsed is None:
            return self._amount_input_view(session, input_error=True)
        value, unit = parsed
        try:
            updated = self._store.set_amount(
                user_id,
                action_key,
                value=value,
                unit=unit,
            )
        except (InvalidCompositionState, StaleCompositionAction):
            return CompositionView(step=CompositionStep.STALE)
        return self._review_view(updated)

    def apply_composition_action_view(
        self,
        telegram_user_id: int,
        data: str,
        *,
        action_key: str,
    ) -> CompositionView:
        user_id = self._base_store.ensure_user(telegram_user_id)
        parts = data.split(":")
        action = parts[0]
        try:
            if action == "k122comp":
                return self.composition_view(telegram_user_id)
            if action == "k122cancel":
                self._store.cancel(user_id)
                self._base_store.cancel_pending(user_id)
                return CompositionView(step=CompositionStep.CANCELLED)
            if action == "k122c":
                if len(parts) != 3:
                    return CompositionView(step=CompositionStep.INVALID)
                record = self._record_from_token(user_id, parts[1], int(parts[2]))
                if record.serving_basis_type != "per_label_portion":
                    self._base_store.begin_composition_serving_quantity(
                        user_id,
                        action_key,
                        record.instance_id,
                        record.revision,
                    )
                    return self._serving_quantity_view(record)
                return self._composition_nutrient_view(user_id, record)
            if action == "k122n":
                if len(parts) != 4:
                    return CompositionView(step=CompositionStep.INVALID)
                record = self._record_from_token(user_id, parts[1], int(parts[2]))
                if record.serving_basis_type != "per_label_portion":
                    return CompositionView(step=CompositionStep.STALE)
                substance_key = parts[3]
                subject_id = self._subject_for_substance(substance_key)
                display_name = _RU_SUBSTANCE_NAMES.get(substance_key)
                if subject_id is None or display_name is None:
                    return CompositionView(step=CompositionStep.INVALID)
                session = self._store.begin_amount(
                    user_id,
                    action_key,
                    tracked_instance_id=record.instance_id,
                    expected_supplement_revision=record.revision,
                    substance_key=substance_key,
                    analyte_id=subject_id,
                    display_name=display_name,
                )
                return self._amount_input_view(session)
            if action == "k122ok":
                if len(parts) != 2:
                    return CompositionView(step=CompositionStep.INVALID)
                amount = self._store.confirm_amount(
                    user_id,
                    action_key,
                    expected_session_revision=int(parts[1]),
                )
                supplement = self._base_store.supplement(user_id, amount.tracked_instance_id)
                return CompositionView(
                    step=CompositionStep.COMPLETE,
                    instance_id=supplement.instance_id,
                    supplement_token=self._token(supplement.instance_id),
                    supplement_revision=supplement.revision,
                    name=supplement.name,
                    unit_label=supplement.unit_label,
                    substance_key=amount.substance_key,
                    nutrient_name=self._subject_name(amount.analyte_id),
                    value=amount.value,
                    unit=amount.unit,
                )
        except (IndexError, ValueError):
            return CompositionView(step=CompositionStep.INVALID)
        except DuplicateCompositionFact:
            return CompositionView(step=CompositionStep.DUPLICATE)
        except (
            InvalidCompositionState,
            StaleCompositionAction,
            SupplementInvalidTransition,
            StaleAction,
            RecordNotFound,
        ):
            return CompositionView(step=CompositionStep.STALE)

        return CompositionView(step=CompositionStep.INVALID)

    def composition(self, telegram_user_id: int) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        records = self._base_store.list_supplements(user_id)
        if not records:
            return Screen(
                text=(
                    "Состав\n\nСначала добавьте добавку и подтвердите её название и единицу. "
                    "Никакие значения состава не будут придуманы автоматически."
                ),
                rows=((Button("Добавить добавку", "a"),),),
            )

        lines = [
            "Состав",
            "",
            "Выберите добавку. Здесь сохраняются только значения, которые вы явно подтвердили.",
        ]
        rows: list[tuple[Button, ...]] = []
        for record in records:
            keys = self._store.manual_substance_keys(user_id, record.instance_id)
            suffix = f" — {len(keys)} подтверждено" if keys else " — состав не указан"
            lines.append(f"• {record.name}{suffix}")
            rows.append(
                (
                    Button(
                        f"Состав: {record.name[:28]}",
                        f"k122c:{self._token(record.instance_id)}:{record.revision}",
                    ),
                )
            )
        rows.append((Button("Итоги за день", "k122tot"),))
        return Screen(text="\n".join(lines), rows=tuple(rows))

    def totals_view(self, telegram_user_id: int) -> RegimenTotalsView:
        user_id = self._base_store.ensure_user(telegram_user_id)
        view = self._build_view(user_id)
        aggregation = view.aggregation

        if not view.snapshot.supplements:
            return RegimenTotalsView(status=RegimenTotalsStatus.NO_SUPPLEMENTS)

        unresolved_total = len(aggregation.unresolved_contributors)
        if not aggregation.aggregates:
            return RegimenTotalsView(
                status=RegimenTotalsStatus.NO_AGGREGATES,
                unresolved_contributor_count=unresolved_total,
            )

        names = {item.instance_id: item.name for item in view.snapshot.supplements}
        nutrients: list[NutrientTotalsView] = []
        for aggregate in aggregation.aggregates:
            unresolved_count = sum(
                1
                for contributor in aggregation.unresolved_contributors
                if contributor.expected_subject_kind is aggregate.key.subject_kind
                and contributor.expected_subject_id == aggregate.key.subject_id
                and contributor.expected_amount_basis is aggregate.key.amount_basis
                and contributor.expected_equivalence_basis == aggregate.key.equivalence_basis
            )
            contributors = tuple(
                NutrientContributorView(
                    tracked_instance_id=contributor.tracked_instance_id,
                    name=names.get(
                        contributor.tracked_instance_id,
                        "Подтверждённая добавка",
                    ),
                    value=contributor.normalized_value,
                    unit=contributor.normalized_unit,
                )
                for contributor in aggregate.contributors
            )
            nutrients.append(
                NutrientTotalsView(
                    subject_id=aggregate.key.subject_id,
                    name=self._subject_name(aggregate.key.subject_id),
                    total=aggregate.known_total if aggregate.is_complete else None,
                    unit=aggregate.unit if aggregate.is_complete else None,
                    is_complete=aggregate.is_complete,
                    contributors=contributors,
                    unresolved_contributor_count=unresolved_count,
                    issue_codes=tuple(issue.value for issue in aggregate.issues),
                    suppressed_exact_repeat_count=len(aggregate.suppressed_exact_repeat_ids),
                    substance_key=self._substance_key_for_subject(aggregate.key.subject_id),
                )
            )

        return RegimenTotalsView(
            status=RegimenTotalsStatus.READY,
            nutrients=tuple(nutrients),
            unresolved_contributor_count=unresolved_total,
        )

    def totals(self, telegram_user_id: int) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        view = self._build_view(user_id)
        aggregation = view.aggregation
        aggregates = aggregation.aggregates
        if not view.snapshot.supplements:
            return Screen(
                text=(
                    "Итоги за день\n\nДобавок пока нет. "
                    "Итог появляется только из подтверждённого состава и текущего плана."
                ),
                rows=((Button("Добавить добавку", "a"),),),
            )
        if not aggregates:
            return Screen(
                text=(
                    "Итоги за день\n\nПока не из чего посчитать полный итог. "
                    "Нужны подтверждённый состав и сохранённый план с количеством единиц.\n\n"
                    "Неизвестное значение не считается нулём."
                ),
                rows=(
                    (Button("Добавить состав", "k122comp"),),
                    (Button("План", "k120p"), Button("Сегодня", "k120today")),
                ),
            )

        names = {item.instance_id: item.name for item in view.snapshot.supplements}
        lines = [
            "Итоги за день",
            "",
            "Расчёт только из подтверждённых строк состава и текущих версий плана.",
        ]
        for aggregate in aggregates:
            name = self._subject_name(aggregate.key.subject_id)
            if (
                aggregate.is_complete
                and aggregate.known_total is not None
                and aggregate.unit is not None
            ):
                total = f"{self._decimal(aggregate.known_total)} {self._unit_label(aggregate.unit)}"
                lines.append(f"\n{name}: {total}")
            else:
                lines.append(f"\n{name}: итог неполный — полное значение не показываю")
            for contributor in aggregate.contributors:
                contributor_name = names.get(
                    contributor.tracked_instance_id,
                    "Подтверждённая добавка",
                )
                lines.append(
                    f"  • {contributor_name}: "
                    f"{self._decimal(contributor.normalized_value)} "
                    f"{self._unit_label(contributor.normalized_unit)}"
                )
            if aggregate.issues:
                lines.append("  Нужна проверка: один или несколько вкладов нельзя считать полными.")
            if aggregate.suppressed_exact_repeat_ids:
                lines.append("  Точный повтор одного и того же вклада не посчитан второй раз.")

        if aggregation.unresolved_contributors:
            lines.extend(
                [
                    "",
                    "Есть неподтверждённые или неоднозначные вклады. "
                    "Они не превращены в ноль и не добавлены к полному итогу.",
                ]
            )
        rows: list[tuple[Button, ...]] = [
            (Button("Проверка", "k122safe"),),
            (Button("Почему так распределено?", "k122rules"),),
        ]
        for aggregate in aggregates:
            substance_key = self._substance_key_for_subject(aggregate.key.subject_id)
            if substance_key is None:
                continue
            rows.append(
                (
                    Button(
                        f"О веществе · {self._subject_name(aggregate.key.subject_id)}",
                        f"k146c:{substance_key}",
                    ),
                )
            )
        rows.extend(
            [
                (Button("Сегодня", "k120today"), Button("План", "k120p")),
                (Button("Состав", "k122comp"),),
            ]
        )
        return Screen(text="\n".join(lines), rows=tuple(rows))

    def rules(self, telegram_user_id: int) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        view = self._build_view(user_id)
        result = view.rule_result

        lines = ["Планирование", ""]
        if result.global_status is RuleEngineGlobalStatus.WITHHELD_HIGH_RISK_CONTEXT:
            lines.append(
                "Автоматическое планирование остановлено: текущий контекст требует "
                "отдельно подтверждённого правила. Это не вывод о безопасности."
            )
        elif not result.scheduling_results:
            lines.append(
                "Недостаточно подтверждённых данных для доказательного правила планирования. "
                "Текущие Morning / Day / Evening остаются вашими организационными метками."
            )
        else:
            for rule in result.scheduling_results:
                item_names = tuple(
                    view.item_names.get(item_id, "Подтверждённая позиция")
                    for item_id in rule.item_ids
                )
                label = ", ".join(dict.fromkeys(item_names))
                if rule.status is RuleStatus.MATCHED_PREFERENCE:
                    if rule.event_relation is EventRelation.AVOID_SAME_EVENT:
                        lines.append(
                            f"• {label}: предпочтение — не размещать в одном приёме. "
                            "Точный интервал не установлен. Это не медицинская необходимость."
                        )
                    elif rule.rule_type is RuleType.MEAL_CONTEXT:
                        lines.append(
                            f"• {label}: найдено доказательное предпочтение, связанное с едой. "
                            "Это предпочтение, а не обязательное медицинское указание."
                        )
                    else:
                        lines.append(
                            f"• {label}: найдено доказательное предпочтение по распределению "
                            "уже запланированных единиц. Оно не создаёт новую дозу."
                        )
                elif rule.status is RuleStatus.NO_SUPPORTED_RULE_FOUND:
                    lines.append(
                        f"• {label}: поддерживаемое правило не найдено. "
                        "Это не подтверждение совместимости или безопасности."
                    )
                elif rule.status is RuleStatus.INSUFFICIENT_EVIDENCE:
                    lines.append(
                        f"• {label}: данных недостаточно. "
                        "План автоматически не усиливается и не дополняется догадкой."
                    )
                elif rule.status is RuleStatus.CANNOT_OPTIMIZE_FIXED_COMBINATION:
                    lines.append(
                        f"• {label}: состав одной единицы нельзя разнести по компонентам. "
                        "План не пытается разделить неделимую добавку."
                    )
                else:
                    lines.append(
                        f"• {label}: более приоритетный подтверждённый контекст не позволяет "
                        "автоматически применить это предпочтение."
                    )
                for warning in rule.warnings:
                    lines.append(f"  Важно: {self._rule_warning_text(warning)}")

        lines.extend(
            [
                "",
                "Morning / Day / Evening — организационные метки пользователя. "
                "VitaminBot не выводит из них биологическое преимущество времени суток.",
                "Отсутствие правила не означает, что сочетание безопасно.",
            ]
        )
        short_revision = self._short_revision(view.snapshot.context_revision)
        return Screen(
            text="\n".join(lines),
            rows=(
                (Button("Источники правил", f"k122why:{short_revision}"),),
                (Button("Сегодня", "k120today"), Button("План", "k120p")),
                (Button("Итоги", "k122tot"),),
            ),
        )

    def safety_envelopes(self, telegram_user_id: int) -> tuple[SafetyEnvelope, ...]:
        user_id = self._base_store.ensure_user(telegram_user_id)
        view = self._build_view(user_id)
        bound = self._bound_applicability(telegram_user_id, view.snapshot.context_revision)
        context_revision = (
            view.snapshot.context_revision if bound is None else bound.context_revision
        )
        return self._reference_envelopes(view, bound) + (
            self._scope_envelope(view, context_revision=context_revision),
        )

    def safety(self, telegram_user_id: int) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        view = self._build_view(user_id)
        if self._applicability_controller is not None:
            prompt = self._applicability_controller.prompt_for_pairs(
                telegram_user_id,
                pairs=self._reference_pairs(view),
                base_revision=view.snapshot.context_revision,
            )
            if prompt is not None:
                return prompt
        bound = self._bound_applicability(telegram_user_id, view.snapshot.context_revision)
        context_revision = (
            view.snapshot.context_revision if bound is None else bound.context_revision
        )
        envelopes = self._reference_envelopes(view, bound) + (
            self._scope_envelope(view, context_revision=context_revision),
        )
        short_revision = self._short_revision(context_revision)
        rows: list[tuple[Button, ...]] = [
            (Button("Почему / источники", f"k122src:{short_revision}"),),
            (Button("Итоги", "k122tot"), Button("Сегодня", "k120today")),
        ]
        if self._applicability_controller is not None:
            rows.append((Button("Контекст применимости", "k174profile"),))
            if bound is not None and any(
                substance_key == "iron" for substance_key, _ in self._reference_pairs(view)
            ):
                scope_token = bound.iron_scope_key.removeprefix("iron:")
                rows.append(
                    (
                        Button(
                            "Контекст текущего приёма железа",
                            f"k174iron:{scope_token}",
                        ),
                    )
                )
        return Screen(
            text=render_safety_envelopes(envelopes),
            rows=tuple(rows),
        )

    def has_pending_text(self, telegram_user_id: int) -> bool:
        user_id = self._base_store.ensure_user(telegram_user_id)
        base_session = self._base_store.get_session(user_id)
        if (
            base_session is not None
            and base_session.state == "composition_serving_quantity"
        ):
            return True
        session = self._store.session(user_id)
        return session is not None and session.state == "amount_input"

    def text(
        self,
        telegram_user_id: int,
        text: str,
        *,
        action_key: str,
    ) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        session = self._store.session(user_id)
        if session is None or session.state != "amount_input":
            return Screen(
                text=("Сейчас я не жду значение состава. Откройте «Состав» и выберите нутриент.")
            )

        parsed = self._parse_amount(text)
        if parsed is None:
            return Screen(
                text=(
                    f"{session.display_name}\n\n"
                    "Отправьте количество с единицей массы, например: 100 mg, 250 мкг или 1 g. "
                    "Значение не будет пересчитано в другую химическую форму."
                ),
                rows=((Button("Отмена", "k122cancel"),),),
            )
        value, unit = parsed
        try:
            updated = self._store.set_amount(
                user_id,
                action_key,
                value=value,
                unit=unit,
            )
        except (InvalidCompositionState, StaleCompositionAction):
            return self._stale_screen()
        return self._review_screen(updated)

    def callback(
        self,
        telegram_user_id: int,
        data: str,
        *,
        action_key: str,
    ) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        parts = data.split(":")
        action = parts[0]
        try:
            if action == "k122comp":
                return self.composition(telegram_user_id)
            if action == "k122tot":
                return self.totals(telegram_user_id)
            if action == "k122rules":
                return self.rules(telegram_user_id)
            if action == "k122safe":
                return self.safety(telegram_user_id)
            if action == "k122cancel":
                self._store.cancel(user_id)
                return Screen(
                    text="Ввод состава отменён. Подтверждённые данные не изменены.",
                    rows=((Button("Состав", "k122comp"),),),
                )
            if action == "k122c":
                record = self._record_from_token(user_id, parts[1], int(parts[2]))
                return self._substance_picker(user_id, record)
            if action == "k122n":
                record = self._record_from_token(user_id, parts[1], int(parts[2]))
                substance_key = parts[3]
                subject_id = self._subject_for_substance(substance_key)
                display_name = _RU_SUBSTANCE_NAMES.get(substance_key)
                if subject_id is None or display_name is None:
                    raise ValueError("unsupported substance")
                session = self._store.begin_amount(
                    user_id,
                    action_key,
                    tracked_instance_id=record.instance_id,
                    expected_supplement_revision=record.revision,
                    substance_key=substance_key,
                    analyte_id=subject_id,
                    display_name=display_name,
                )
                return Screen(
                    text=(
                        f"{session.display_name} — {record.name}\n\n"
                        "Введите количество на одну порцию с этикетки вместе с единицей массы. "
                        "Пример: 100 mg или 250 мкг.\n\n"
                        "Я сохраню только введённый факт. Это не рекомендация по дозе."
                    ),
                    rows=((Button("Отмена", "k122cancel"),),),
                )
            if action == "k122ok":
                confirmed_amount = self._store.confirm_amount(
                    user_id,
                    action_key,
                    expected_session_revision=int(parts[1]),
                )
                supplement = self._base_store.supplement(
                    user_id, confirmed_amount.tracked_instance_id
                )
                rows: list[tuple[Button, ...]] = [
                    (Button("Добавить ещё строку состава", "k122comp"),),
                ]
                manual_token = self._manual_token(supplement.instance_id)
                if manual_token is not None:
                    rows.extend(
                        [
                            (
                                Button(
                                    "Открыть добавку",
                                    f"o:{manual_token}:{supplement.revision}",
                                ),
                            ),
                            (
                                Button(
                                    "Настроить план",
                                    f"p:{manual_token}:{supplement.revision}",
                                ),
                            ),
                        ]
                    )
                rows.extend(
                    [
                        (Button("Итоги за день", "k122tot"),),
                        (Button("Сегодня", "k120today"),),
                    ]
                )
                return Screen(
                    text=(
                        f"Состав подтверждён\n\n"
                        f"{self._subject_name(confirmed_amount.analyte_id)}: "
                        f"{self._decimal(confirmed_amount.value)} "
                        f"{self._unit_label(confirmed_amount.unit)} "
                        "на подтверждённую порцию этикетки.\n\n"
                        "Это запись факта с этикетки, а не вывод о безопасности "
                        "и не рекомендация по дозе."
                    ),
                    rows=tuple(rows),
                )
            if action == "k122why":
                return self._rule_sources(telegram_user_id, parts[1])
            if action == "k122src":
                return self._reference_sources(telegram_user_id, parts[1])
        except (IndexError, ValueError):
            return Screen(
                text="Это действие больше нельзя применить. Откройте текущий экран ещё раз."
            )
        except DuplicateCompositionFact:
            return Screen(
                text=(
                    "Для этого нутриента уже есть подтверждённая ручная строка. "
                    "Я не заменяю её молча. Удаление/коррекция должны быть "
                    "отдельным явным действием."
                ),
                rows=((Button("Состав", "k122comp"),),),
            )
        except (InvalidCompositionState, StaleCompositionAction):
            return self._stale_screen()
        return Screen(text="Это действие сейчас недоступно.")

    def decorate_operational_screen(self, screen: Screen) -> Screen:
        """Add vertical navigation without changing the underlying domain transition."""
        callbacks = {button.callback_data for row in screen.rows for button in row}
        rows = list(screen.rows)
        if any(value.startswith("p:") for value in callbacks):
            rows.append(
                (
                    Button("Состав", "k122comp"),
                    Button("Итоги", "k122tot"),
                )
            )
        if "k120p" in callbacks or "k120h" in callbacks or "k120today" in callbacks:
            if "k122tot" not in callbacks:
                rows.append((Button("Итоги", "k122tot"), Button("Почему?", "k122rules")))
        return Screen(text=screen.text, rows=tuple(rows))

    def _serving_quantity_view(
        self,
        record: SupplementRecord,
        *,
        input_error: bool = False,
    ) -> CompositionView:
        return CompositionView(
            step=CompositionStep.SERVING_QUANTITY,
            instance_id=record.instance_id,
            supplement_token=self._token(record.instance_id),
            supplement_revision=record.revision,
            name=record.name,
            unit_label=record.unit_label,
            input_error=input_error,
        )

    def _composition_nutrient_view(
        self,
        user_id: UUID,
        record: SupplementRecord,
    ) -> CompositionView:
        existing = set(self._store.manual_substance_keys(user_id, record.instance_id))
        nutrients = tuple(
            CompositionNutrientOption(substance_key=key, name=name)
            for key, name in _RU_SUBSTANCE_NAMES.items()
            if key not in existing and self._subject_for_substance(key) is not None
        )
        return CompositionView(
            step=CompositionStep.NUTRIENT,
            instance_id=record.instance_id,
            supplement_token=self._token(record.instance_id),
            supplement_revision=record.revision,
            name=record.name,
            unit_label=record.unit_label,
            nutrients=nutrients,
        )

    @staticmethod
    def _amount_input_view(
        session: CompositionSession,
        *,
        input_error: bool = False,
    ) -> CompositionView:
        return CompositionView(
            step=CompositionStep.AMOUNT,
            instance_id=session.tracked_instance_id,
            supplement_revision=session.expected_supplement_revision,
            substance_key=session.substance_key,
            nutrient_name=session.display_name,
            session_revision=session.revision,
            input_error=input_error,
        )

    @staticmethod
    def _review_view(session: CompositionSession) -> CompositionView:
        return CompositionView(
            step=CompositionStep.REVIEW,
            instance_id=session.tracked_instance_id,
            supplement_revision=session.expected_supplement_revision,
            substance_key=session.substance_key,
            nutrient_name=session.display_name,
            value=session.pending_value,
            unit=session.pending_unit,
            session_revision=session.revision,
        )

    def _substance_picker(self, user_id: UUID, record: SupplementRecord) -> Screen:
        existing = set(self._store.manual_substance_keys(user_id, record.instance_id))
        options = [
            (key, name, self._subject_for_substance(key))
            for key, name in _RU_SUBSTANCE_NAMES.items()
            if key not in existing
        ]
        options = [(key, name, subject_id) for key, name, subject_id in options if subject_id]
        if not options:
            return Screen(
                text=(
                    f"Состав — {record.name}\n\n"
                    "Все поддерживаемые в этом ручном MVP списке позиции уже подтверждены. "
                    "Я не создаю дубликаты автоматически."
                ),
                rows=((Button("Итоги", "k122tot"),),),
            )
        token = self._token(record.instance_id)
        manual_token = self._manual_token(record.instance_id)
        if manual_token is None:
            raise ValueError("unsupported supplement reference")
        rows = tuple(
            (Button(name, f"k122n:{token}:{record.revision}:{key}"),) for key, name, _ in options
        )
        return Screen(
            text=(
                f"Состав — {record.name}\n\n"
                "Выберите нутриент только если именно он указан на этикетке. "
                "Следующим сообщением вы подтвердите количество на порцию.\n\n"
                "Выбор названия не означает, что добавка безопасна или подходит вам."
            ),
            rows=rows
            + (
                (
                    Button(
                        "Назад к добавке",
                        f"o:{manual_token}:{record.revision}",
                    ),
                ),
            ),
        )

    @staticmethod
    def _review_screen(session: CompositionSession) -> Screen:
        assert session.pending_value is not None
        assert session.pending_unit is not None
        return Screen(
            text=(
                f"Проверьте состав\n\n"
                f"{session.display_name}: {KIR122Controller._decimal(session.pending_value)} "
                f"{KIR122Controller._unit_label(session.pending_unit)} "
                "на одну подтверждённую порцию этикетки.\n\n"
                "Подтверждение означает только «это совпадает с тем, что я ввёл». "
                "Оно не означает «безопасно», «подходит» или «рекомендовано»."
            ),
            rows=(
                (Button("Подтвердить", f"k122ok:{session.revision}"),),
                (Button("Отмена / ввести заново", "k122cancel"),),
            ),
        )

    def _build_view(self, user_id: UUID) -> VerticalView:
        snapshot = self._store.snapshot(
            user_id,
            semantic_versions=(DATASET_VERSION, RULESET_VERSION, "kir145.accepted.v1"),
        )
        contributions: list[ConfirmedPlannedContribution] = []
        scheduling_items: list[SchedulingItem] = []
        item_names: dict[str, str] = {}

        for supplement in snapshot.supplements:
            if (
                supplement.plan_id is None
                or supplement.plan_version is None
                or not supplement.events
            ):
                continue
            serving = self._serving(supplement)
            plan = IntakePlan(
                plan_id=supplement.plan_id,
                tracked_instance_id=supplement.instance_id,
                version=supplement.plan_version,
                events=tuple(
                    PlannedIntakeEvent(
                        event_id=event.event_id,
                        consumption_unit_id=event.consumption_unit_id,
                        consumption_units=event.consumption_units,
                        schedule_label=event.schedule_label,
                    )
                    for event in supplement.events
                ),
            )
            per_unit: list[tuple[SnapshotAmount, NormalizationOutcome]] = []
            for source_amount in supplement.amounts:
                amount_record = self._amount_record(source_amount)
                if amount_record is None or source_amount.amount_basis is None:
                    continue
                if source_amount.source_superseded_by is not None:
                    outcome = NormalizationOutcome(
                        status=ResolutionStatus.AMBIGUOUS,
                        reason=UnresolvedReason.INPUT_UNRESOLVED,
                    )
                else:
                    try:
                        outcome = normalize_per_consumption_unit(amount_record, serving)
                    except ValueError:
                        outcome = NormalizationOutcome(
                            status=ResolutionStatus.AMBIGUOUS,
                            reason=UnresolvedReason.INPUT_UNRESOLVED,
                        )
                per_unit.append((source_amount, outcome))
                if outcome.status is ResolutionStatus.RESOLVED and outcome.amount is not None:
                    daily = normalize_planned_daily_amount(outcome.amount, plan)
                else:
                    daily = outcome
                contributions.append(
                    ConfirmedPlannedContribution(
                        contribution_id=f"kir122:{source_amount.amount_id}",
                        confirmation_ref=f"confirmed:{source_amount.amount_id}",
                        product_id=supplement.product_id,
                        formulation_id=supplement.formulation_id,
                        tracked_instance_id=supplement.instance_id,
                        plan_id=supplement.plan_id,
                        plan_version=supplement.plan_version,
                        expected_subject_kind=SubjectKind(source_amount.subject_kind),
                        expected_subject_id=source_amount.subject_id,
                        expected_amount_basis=AmountBasis(source_amount.amount_basis),
                        expected_equivalence_basis=source_amount.equivalence_basis,
                        expected_unit=(
                            None if source_amount.unit is None else Unit(source_amount.unit)
                        ),
                        outcome=daily,
                    )
                )

            for event in supplement.events:
                event_amounts: list[ComputedAmount] = []
                for _, outcome in per_unit:
                    if outcome.status is not ResolutionStatus.RESOLVED or outcome.amount is None:
                        continue
                    computed_amount = outcome.amount
                    event_amounts.append(
                        ComputedAmount(
                            subject_kind=computed_amount.subject_kind,
                            subject_id=computed_amount.subject_id,
                            value=computed_amount.value * event.consumption_units,
                            unit=computed_amount.unit,
                            amount_basis=computed_amount.amount_basis,
                            quantity_basis=QuantityBasis.ABSOLUTE,
                            source_quantity_basis_ids=computed_amount.source_quantity_basis_ids,
                            source_amount_ids=computed_amount.source_amount_ids,
                            source_ids=computed_amount.source_ids,
                            traces=computed_amount.traces
                            + (
                                ComputationTrace(
                                    operation="kir122_event_snapshot",
                                    rule_id="KIR-122",
                                    rule_version="1",
                                    plan_id=supplement.plan_id,
                                    plan_version=supplement.plan_version,
                                ),
                            ),
                            chemical_form_id=computed_amount.chemical_form_id,
                            equivalence_basis=computed_amount.equivalence_basis,
                        )
                    )
                if not event_amounts:
                    continue
                item_id = f"item:{self._token(supplement.instance_id)}:{event.event_id}"
                item_names[item_id] = supplement.name
                integral_units = (
                    event.consumption_units == event.consumption_units.to_integral_value()
                )
                scheduling_items.append(
                    SchedulingItem(
                        item_id=item_id,
                        product_id=supplement.product_id,
                        formulation_id=supplement.formulation_id,
                        tracked_instance_id=supplement.instance_id,
                        plan_id=supplement.plan_id,
                        plan_version=supplement.plan_version,
                        event_id=event.event_id,
                        context_revision=snapshot.context_revision,
                        source_kind=ItemSourceKind.SUPPLEMENT,
                        amounts=tuple(event_amounts),
                        confirmed_consumption_units=event.consumption_units,
                        units_independently_schedulable=(
                            supplement.unit_label in _INTACT_UNIT_LABELS and integral_units
                        ),
                        fixed_combination_id=supplement.formulation_id,
                    )
                )

        aggregation = aggregate_daily_contributions(contributions)
        bound = BoundDailyAggregation(
            aggregation=aggregation,
            context_revision=snapshot.context_revision,
        )
        rule_result = evaluate_rule_engine(
            RuleEvaluationContext(
                context_revision=snapshot.context_revision,
                items=tuple(scheduling_items),
            ),
            aggregation=bound,
        )
        return VerticalView(
            snapshot=snapshot,
            aggregation=aggregation,
            rule_result=rule_result,
            item_names=item_names,
        )

    @staticmethod
    def _serving(supplement: SnapshotSupplement) -> ServingDefinition:
        return ServingDefinition(
            basis_id=supplement.serving_basis_id,
            basis_type=QuantityBasis(supplement.serving_basis_type),
            label_text=supplement.serving_label_text,
            source_id=supplement.serving_source_id,
            basis_quantity=supplement.serving_quantity,
            basis_unit=None if supplement.serving_unit is None else Unit(supplement.serving_unit),
            consumption_unit_id=supplement.unit_id,
        )

    @staticmethod
    def _amount_record(amount: SnapshotAmount) -> AmountRecord | None:
        try:
            return AmountRecord(
                amount_id=amount.amount_id,
                subject_kind=SubjectKind(amount.subject_kind),
                subject_id=amount.subject_id,
                source_id=amount.source_id,
                resolution_status=ResolutionStatus(amount.resolution_status),
                evidence_status=EvidenceStatus(amount.evidence_status),
                value=amount.value,
                unit=None if amount.unit is None else Unit(amount.unit),
                amount_basis=(
                    None if amount.amount_basis is None else AmountBasis(amount.amount_basis)
                ),
                quantity_basis=(
                    None if amount.quantity_basis is None else QuantityBasis(amount.quantity_basis)
                ),
                quantity_basis_id=amount.quantity_basis_id,
                equivalence_basis=amount.equivalence_basis,
                raw_text=amount.raw_text,
            )
        except ValueError:
            return None

    @staticmethod
    def _scope_envelope(
        view: VerticalView,
        *,
        context_revision: str | None = None,
    ) -> SafetyEnvelope:
        return SafetyEnvelope(
            subject_name="Границы персональной оценки",
            status=SafetyStatus.CANNOT_ASSESS,
            classification="personal_safety_scope",
            known_facts=(
                SafetyFact(
                    key="covered_scope",
                    value=(
                        "Этот экран показывает только подтверждённые факты состава, "
                        "агрегацию и применимые справочные сравнения."
                    ),
                ),
            ),
            unknown_or_ambiguous=(
                SafetyFact(
                    key="medication_interactions",
                    value=(
                        "Лекарственные взаимодействия не проверяются этим MVP-экраном "
                        "без отдельного подтверждённого источника и контекста."
                    ),
                ),
                SafetyFact(
                    key="special_population_context",
                    value=(
                        "Беременность/лактация, детский возраст и болезни почек/печени "
                        "не предполагаются и не выводятся автоматически."
                    ),
                ),
            ),
            withheld_conclusion=("Персональный вывод о безопасности всей схемы добавок не сделан."),
            provenance=(),
            resolution_path=(
                "Для персонального вывода нужен отдельно подтверждённый применимый "
                "контекст и принятые источники; отсутствующие данные не подставляются."
            ),
            escalation_path=None,
            non_droppable_warnings=(
                "Отсутствие справочного сигнала не означает совместимость "
                "или безопасность всей схемы.",
                "Отсутствие данных о взаимодействии не означает отсутствие взаимодействия.",
            ),
            comparison_context=None,
            contributors=(),
            evidence_state=SafetyEvidenceState.MISSING,
            context_revision=context_revision or view.snapshot.context_revision,
        )

    def _reference_envelopes(
        self,
        view: VerticalView,
        bound: BoundApplicabilityContext | None = None,
    ) -> tuple[SafetyEnvelope, ...]:
        rows: list[SafetyEnvelope] = []
        names = {item.instance_id: item.name for item in view.snapshot.supplements}
        for aggregate in view.aggregation.aggregates:
            candidates = tuple(
                record
                for record in EU_EFSA_REFERENCE_DATASET.records
                if record.lifecycle is ReferenceLifecycle.ACTIVE
                and record.subject_kind is aggregate.key.subject_kind
                and record.subject_id == aggregate.key.subject_id
                and record.amount_basis is aggregate.key.amount_basis
                and record.equivalence_basis == aggregate.key.equivalence_basis
            )
            pairs = sorted(
                {(record.substance_key, record.reference_type) for record in candidates},
                key=lambda item: (item[0], item[1].value),
            )
            if not pairs:
                continue

            subject_name = self._subject_name(aggregate.key.subject_id)
            amount = self._aggregate_amount(aggregate)
            contributors = tuple(
                SafetyContributor(
                    tracked_instance_id=contributor.tracked_instance_id,
                    display_name=names.get(
                        contributor.tracked_instance_id,
                        "Подтверждённая добавка",
                    ),
                    normalized_amount=(
                        f"{self._decimal(contributor.normalized_value)} "
                        f"{self._unit_label(contributor.normalized_unit)}"
                    ),
                )
                for contributor in aggregate.contributors
            )
            daily_fact = (
                ()
                if amount is None
                else (
                    SafetyFact(
                        key="confirmed_daily_total",
                        value=(
                            f"Подтверждённый дневной итог: {self._decimal(amount.value)} "
                            f"{self._unit_label(amount.unit)}."
                        ),
                    ),
                )
            )

            for substance_key, reference_type in pairs:
                context_revision = (
                    view.snapshot.context_revision if bound is None else bound.context_revision
                )
                profile = PopulationProfile() if bound is None else bound.profile
                exposure = (
                    ExposureContext()
                    if bound is None or substance_key != "iron"
                    else bound.iron_exposure
                )
                lookup = lookup_reference(
                    EU_EFSA_REFERENCE_DATASET,
                    ReferenceQuery(
                        substance_key=substance_key,
                        reference_type=reference_type,
                        profile=profile,
                        exposure=exposure,
                        context_revision=context_revision,
                    ),
                )
                comparison_context = SafetyComparisonContext(
                    reference_type=self._reference_label(reference_type),
                    reference_record_id=None,
                    amount_basis=aggregate.key.amount_basis.value,
                    equivalence_basis=aggregate.key.equivalence_basis,
                    relation=None,
                    dataset_version=DATASET_VERSION,
                )
                if lookup.status is not LookupStatus.MATCHED or lookup.match is None:
                    evidence_state = (
                        SafetyEvidenceState.AMBIGUOUS
                        if lookup.status
                        in {
                            LookupStatus.AMBIGUOUS,
                            LookupStatus.INDETERMINATE,
                            LookupStatus.PARTIAL_COVERAGE,
                        }
                        else SafetyEvidenceState.MISSING
                    )
                    rows.append(
                        SafetyEnvelope(
                            subject_name=subject_name,
                            status=SafetyStatus.CANNOT_ASSESS,
                            classification="reference_applicability",
                            known_facts=daily_fact,
                            unknown_or_ambiguous=(
                                SafetyFact(
                                    key="reference_applicability",
                                    value=(
                                        "Не установлена точная применимость справочного "
                                        "значения к текущему контексту."
                                    ),
                                ),
                            ),
                            withheld_conclusion=(
                                "Персональный вывод о безопасности по этому "
                                "справочному значению не сделан."
                            ),
                            provenance=(),
                            resolution_path=(
                                "Нужен подтверждённый контекст применимости по принятой "
                                "политике; взрослое значение по умолчанию не используется."
                            ),
                            escalation_path=None,
                            non_droppable_warnings=(
                                "Неизвестная применимость не означает отсутствие риска.",
                                "Справочное значение нельзя превращать в персональную дозу.",
                            ),
                            comparison_context=comparison_context,
                            contributors=contributors,
                            evidence_state=evidence_state,
                            context_revision=context_revision,
                        )
                    )
                    continue

                record = lookup.match.record
                source = lookup.match.source
                provenance = (
                    SafetyProvenance(
                        source_key=record.source_key,
                        title=source.title,
                        source_url=source.source_url,
                        version=source.version_label,
                        source_locator=record.source_locator,
                        jurisdiction=record.jurisdiction.value,
                        reference_type=record.reference_type.value,
                        applicability_status=lookup.match.applicability.status.value,
                        scope_note=record.provenance_note or None,
                    ),
                )
                comparison_context = SafetyComparisonContext(
                    reference_type=self._reference_label(record.reference_type),
                    reference_record_id=record.record_id,
                    amount_basis=record.amount_basis.value,
                    equivalence_basis=record.equivalence_basis,
                    relation=None,
                    dataset_version=record.dataset_version,
                )
                reference_fact = SafetyFact(
                    key="reference_state",
                    value=self._reference_state_text(record),
                )

                if record.status not in {
                    ReferenceStatus.ESTABLISHED_NUMERIC,
                    ReferenceStatus.CONDITIONAL_NUMERIC,
                }:
                    rows.append(
                        SafetyEnvelope(
                            subject_name=subject_name,
                            status=SafetyStatus.CANNOT_ASSESS,
                            classification="reference_limit_availability",
                            known_facts=daily_fact + (reference_fact,),
                            unknown_or_ambiguous=(
                                SafetyFact(
                                    key="numeric_reference_limit",
                                    value=(
                                        "Для этого справочного типа нет применимого "
                                        "числового значения."
                                    ),
                                ),
                            ),
                            withheld_conclusion=(
                                "Числовой верхний предел и персональный вывод о "
                                "безопасности не выведены."
                            ),
                            provenance=provenance,
                            resolution_path=(
                                "Использовать только применимый типизированный источник; "
                                "отсутствующее числовое значение не подставляется."
                            ),
                            escalation_path=None,
                            non_droppable_warnings=(
                                "Отсутствие числового UL не означает неограниченную безопасность.",
                                "Справочное значение нельзя превращать в персональную дозу.",
                            ),
                            comparison_context=comparison_context,
                            contributors=contributors,
                            evidence_state=SafetyEvidenceState.SUPPORTED,
                            context_revision=context_revision,
                        )
                    )
                    continue

                if amount is None or record.value is None:
                    rows.append(
                        SafetyEnvelope(
                            subject_name=subject_name,
                            status=SafetyStatus.CANNOT_ASSESS,
                            classification="daily_exposure_comparison",
                            known_facts=(reference_fact,),
                            unknown_or_ambiguous=(
                                SafetyFact(
                                    key="complete_daily_exposure",
                                    value=(
                                        "Полный подтверждённый дневной итог для "
                                        "сопоставления недоступен."
                                    ),
                                ),
                            ),
                            withheld_conclusion=(
                                "Сопоставление дневного итога и персональный вывод "
                                "о безопасности не сделаны."
                            ),
                            provenance=provenance,
                            resolution_path=(
                                "Нужно разрешить состав, единицы, порцию и текущий план "
                                "для всех учитываемых вкладов."
                            ),
                            escalation_path=None,
                            non_droppable_warnings=(
                                "Неполный итог не считается нулевым.",
                                "Справочное значение нельзя превращать в персональную дозу.",
                            ),
                            comparison_context=comparison_context,
                            contributors=contributors,
                            evidence_state=SafetyEvidenceState.AMBIGUOUS,
                            context_revision=context_revision,
                        )
                    )
                    continue

                comparison = compare_amount_to_reference(
                    amount,
                    lookup,
                    context_revision=context_revision,
                )
                relation = None if comparison.relation is None else comparison.relation.value
                if relation is None:
                    rows.append(
                        SafetyEnvelope(
                            subject_name=subject_name,
                            status=SafetyStatus.CANNOT_ASSESS,
                            classification="reference_comparison",
                            known_facts=daily_fact + (reference_fact,),
                            unknown_or_ambiguous=(
                                SafetyFact(
                                    key="comparison",
                                    value="Сопоставление не удалось выполнить однозначно.",
                                ),
                            ),
                            withheld_conclusion=("Персональный вывод о безопасности не сделан."),
                            provenance=provenance,
                            resolution_path=(
                                "Нужно устранить несовместимость основы, единицы "
                                "или контекста справочного значения."
                            ),
                            escalation_path=None,
                            non_droppable_warnings=(
                                "Неоднозначное сопоставление не является "
                                "отрицательным результатом.",
                            ),
                            comparison_context=comparison_context,
                            contributors=contributors,
                            evidence_state=SafetyEvidenceState.AMBIGUOUS,
                            context_revision=context_revision,
                        )
                    )
                    continue

                comparison_context = SafetyComparisonContext(
                    reference_type=self._reference_label(record.reference_type),
                    reference_record_id=record.record_id,
                    amount_basis=record.amount_basis.value,
                    equivalence_basis=record.equivalence_basis,
                    relation=relation,
                    dataset_version=record.dataset_version,
                )
                status = SafetyStatus.INFORMATION
                warnings = [
                    "Сопоставление само по себе не устанавливает персональную безопасность.",
                    "Справочное значение нельзя превращать в персональную дозу.",
                ]
                withheld: str | None = None
                if record.reference_type is ReferenceType.UL and relation == "above":
                    status = SafetyStatus.POTENTIAL_REFERENCE_LIMIT_CONCERN
                    withheld = (
                        "Это сопоставление не является диагнозом токсичности "
                        "или подтверждением вреда."
                    )
                    warnings.append(
                        "Превышение UL — потенциальный справочный сигнал, а не диагноз токсичности."
                    )
                elif record.reference_type is ReferenceType.SAFE_LEVEL:
                    warnings.append(
                        "SAFE_LEVEL — отдельный справочный тип: это не UL, не максимум "
                        "и не персональная доза."
                    )
                    if relation == "above":
                        status = SafetyStatus.CAUTION
                        withheld = (
                            "Сопоставление с SAFE_LEVEL не превращено в UL или диагноз токсичности."
                        )

                rows.append(
                    SafetyEnvelope(
                        subject_name=subject_name,
                        status=status,
                        classification="reference_comparison",
                        known_facts=daily_fact + (reference_fact,),
                        unknown_or_ambiguous=(),
                        withheld_conclusion=withheld,
                        provenance=provenance,
                        resolution_path=None,
                        escalation_path=None,
                        non_droppable_warnings=tuple(warnings),
                        comparison_context=comparison_context,
                        contributors=contributors,
                        evidence_state=SafetyEvidenceState.SUPPORTED,
                        context_revision=context_revision,
                    )
                )
        return tuple(rows)

    def _bound_applicability(
        self,
        telegram_user_id: int,
        base_revision: str,
    ) -> BoundApplicabilityContext | None:
        if self._applicability_controller is None:
            return None
        return self._applicability_controller.bound_context(
            telegram_user_id,
            base_revision=base_revision,
        )

    @staticmethod
    def _reference_pairs(
        view: VerticalView,
    ) -> tuple[tuple[str, ReferenceType], ...]:
        pairs: set[tuple[str, ReferenceType]] = set()
        for aggregate in view.aggregation.aggregates:
            for record in EU_EFSA_REFERENCE_DATASET.records:
                if (
                    record.lifecycle is ReferenceLifecycle.ACTIVE
                    and record.subject_kind is aggregate.key.subject_kind
                    and record.subject_id == aggregate.key.subject_id
                    and record.amount_basis is aggregate.key.amount_basis
                    and record.equivalence_basis == aggregate.key.equivalence_basis
                ):
                    pairs.add((record.substance_key, record.reference_type))
        return tuple(sorted(pairs, key=lambda item: (item[0], item[1].value)))

    @staticmethod
    def _aggregate_amount(aggregate: DailyAggregate) -> ComputedAmount | None:
        if (
            not aggregate.is_complete
            or aggregate.known_total is None
            or aggregate.unit is None
            or not aggregate.contributors
        ):
            return None
        contributors = aggregate.contributors
        return ComputedAmount(
            subject_kind=aggregate.key.subject_kind,
            subject_id=aggregate.key.subject_id,
            value=aggregate.known_total,
            unit=aggregate.unit,
            amount_basis=aggregate.key.amount_basis,
            quantity_basis=QuantityBasis.PER_DAY,
            source_quantity_basis_ids=tuple(
                sorted(
                    {
                        basis
                        for contributor in contributors
                        for basis in contributor.original_amount.source_quantity_basis_ids
                    }
                )
            ),
            source_amount_ids=tuple(
                sorted(
                    {
                        amount_id
                        for contributor in contributors
                        for amount_id in contributor.original_amount.source_amount_ids
                    }
                )
            ),
            source_ids=tuple(
                sorted(
                    {
                        source_id
                        for contributor in contributors
                        for source_id in contributor.original_amount.source_ids
                    }
                )
            ),
            traces=tuple(
                trace
                for contributor in contributors
                for trace in contributor.original_amount.traces
            ),
            equivalence_basis=aggregate.key.equivalence_basis,
        )

    @staticmethod
    def _reference_state_text(record: ReferenceRecord) -> str:
        if record.status in {
            ReferenceStatus.ESTABLISHED_NUMERIC,
            ReferenceStatus.CONDITIONAL_NUMERIC,
        }:
            if record.value is not None:
                value = KIR122Controller._decimal(record.value)
                unit = KIR122Controller._unit_label(record.unit)
                suffix = " (не UL)" if record.reference_type is ReferenceType.SAFE_LEVEL else ""
                return (
                    f"{record.reference_type.value}{suffix}: {value} {unit}/день. "
                    "Это типизированное справочное значение, а не персональная рекомендуемая доза."
                )
            return (
                f"{record.reference_type.value}: справочное значение задано диапазоном. "
                "Оно не является персональной рекомендуемой дозой."
            )
        if record.status is ReferenceStatus.NO_UL_INSUFFICIENT_DATA:
            return (
                "UL не установлен из-за недостаточности данных. "
                "Это не означает отсутствие риска или неограниченную безопасность."
            )
        if record.status is ReferenceStatus.NO_NUMERIC_UL_NO_DEFINED_ADVERSE_EFFECTS:
            return (
                "Числовой UL не установлен в этом источнике. "
                "Это не означает неограниченную безопасность."
            )
        if record.status is ReferenceStatus.NO_UL_SAFE_LEVEL_IDENTIFIED:
            return (
                "UL не установлен; SAFE_LEVEL рассматривается как отдельный тип справочного "
                "значения и не является UL или персональной дозой."
            )
        return (
            "Числовое справочное значение не установлено. "
            "Отсутствие значения не означает безопасность."
        )

    def _rule_sources(self, telegram_user_id: int, expected_revision: str) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        view = self._build_view(user_id)
        if self._short_revision(view.snapshot.context_revision) != expected_revision:
            return self._stale_screen()
        sources: dict[str, tuple[str, str, str, str, str, str, str]] = {}
        for result in view.rule_result.scheduling_results:
            for source in result.source_provenance:
                sources[source.source_key] = (
                    source.title,
                    source.authority,
                    source.jurisdiction_note,
                    source.version_label,
                    source.retrieved_on.isoformat(),
                    source.locator,
                    source.source_url,
                )
        lines = [
            "Почему / источники правил",
            "",
            "Источники принадлежат принятому детерминированному набору правил. "
            "Текст интерфейса не создаёт новые научные правила.",
        ]
        if not sources:
            lines.append(
                "Для текущего результата подтверждённое правило с источником не применилось. "
                "Это не подтверждение совместимости или безопасности."
            )
        else:
            for (
                title,
                authority,
                jurisdiction_note,
                version,
                retrieved_on,
                locator,
                url,
            ) in sorted(sources.values()):
                lines.extend(
                    [
                        f"• {title}",
                        f"  автор/организация: {authority}",
                        f"  область применимости источника: {jurisdiction_note}",
                        f"  версия: {version}",
                        f"  получен: {retrieved_on}",
                        f"  раздел/идентификатор: {locator}",
                        f"  {url}",
                    ]
                )
        return Screen(text="\n".join(lines), rows=((Button("Назад", "k122rules"),),))

    def _reference_sources(self, telegram_user_id: int, expected_revision: str) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        view = self._build_view(user_id)
        bound = self._bound_applicability(telegram_user_id, view.snapshot.context_revision)
        context_revision = (
            view.snapshot.context_revision if bound is None else bound.context_revision
        )
        if self._short_revision(context_revision) != expected_revision:
            return self._stale_screen()
        envelopes = self._reference_envelopes(view, bound)
        sources = {
            (
                source.source_key,
                source.title,
                source.source_url,
                source.version,
                source.source_locator,
                source.jurisdiction,
                source.reference_type,
                source.applicability_status,
                source.scope_note,
            )
            for envelope in envelopes
            for source in envelope.provenance
        }
        lines = [
            "Почему / источники",
            "",
            f"Набор справочных данных: {DATASET_VERSION}.",
            "Показываются только источники записей, которые совпали с текущим контекстом.",
        ]
        if not sources:
            lines.append(
                "Совпавшего справочного источника для текущего контекста нет. "
                "Значение не было угадано или подставлено."
            )
        else:
            for (
                _source_key,
                title,
                url,
                version,
                source_locator,
                jurisdiction,
                reference_type,
                applicability_status,
                scope_note,
            ) in sorted(sources, key=lambda item: (item[1], item[4], item[6] or "")):
                lines.extend(
                    [
                        f"• {title}",
                        f"  версия: {version}",
                        f"  раздел источника: {source_locator}",
                    ]
                )
                if jurisdiction is not None:
                    lines.append(f"  юрисдикция: {jurisdiction}")
                if reference_type is not None:
                    lines.append(f"  тип справочного значения: {reference_type}")
                if applicability_status == "match":
                    lines.append("  применимость: запись совпала с текущим контекстом")
                if scope_note is not None:
                    lines.append(f"  область/ограничение: {scope_note}")
                lines.append(f"  {url}")
        return Screen(text="\n".join(lines), rows=((Button("Назад", "k122safe"),),))

    def _record_from_token(
        self,
        user_id: UUID,
        token: str,
        expected_revision: int,
    ) -> SupplementRecord:
        manual_instance_id = (
            f"instance:manual:{token}" if re.fullmatch(r"[0-9a-f]{16}", token) else None
        )
        matches = tuple(
            record
            for record in self._base_store.list_supplements(user_id)
            if self._token(record.instance_id) == token
            or (manual_instance_id is not None and record.instance_id == manual_instance_id)
        )
        if len(matches) != 1:
            raise ValueError("stale supplement token")
        record = matches[0]
        if record.revision != expected_revision:
            raise StaleCompositionAction("supplement changed")
        return record

    @staticmethod
    def _subject_for_substance(substance_key: str) -> str | None:
        ids = {
            record.subject_id
            for record in EU_EFSA_REFERENCE_DATASET.records
            if record.lifecycle is ReferenceLifecycle.ACTIVE
            and record.substance_key == substance_key
            and record.subject_kind is SubjectKind.ANALYTE
        }
        return next(iter(ids)) if len(ids) == 1 else None

    @staticmethod
    def _substance_key_for_subject(subject_id: str) -> str | None:
        keys = {
            record.substance_key
            for record in EU_EFSA_REFERENCE_DATASET.records
            if record.lifecycle is ReferenceLifecycle.ACTIVE
            and record.subject_id == subject_id
            and record.subject_kind is SubjectKind.ANALYTE
            and record.substance_key in _RU_SUBSTANCE_NAMES
        }
        return next(iter(keys)) if len(keys) == 1 else None

    @staticmethod
    def _subject_name(subject_id: str) -> str:
        for key, name in _RU_SUBSTANCE_NAMES.items():
            ids = {
                record.subject_id
                for record in EU_EFSA_REFERENCE_DATASET.records
                if record.lifecycle is ReferenceLifecycle.ACTIVE and record.substance_key == key
            }
            if subject_id in ids:
                return name
        return "Подтверждённый нутриент"

    @staticmethod
    def _parse_positive_count(value: str) -> Decimal | None:
        match = _COUNT_PATTERN.fullmatch(value)
        if match is None:
            return None
        try:
            number = Decimal(match.group(1).replace(",", "."))
        except InvalidOperation:
            return None
        if not number.is_finite() or number <= 0:
            return None
        return number

    @staticmethod
    def _parse_amount(value: str) -> tuple[Decimal, str] | None:
        match = _AMOUNT_PATTERN.fullmatch(value)
        if match is None:
            return None
        try:
            number = Decimal(match.group(1).replace(",", "."))
        except InvalidOperation:
            return None
        if not number.is_finite() or number < 0:
            return None
        unit = _UNIT_ALIASES[match.group(2).lower()]
        return number, unit

    @staticmethod
    def _token(instance_id: str) -> str:
        return hashlib.sha256(instance_id.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _manual_token(instance_id: str) -> str | None:
        token = instance_id.removeprefix("instance:manual:")
        return token if re.fullmatch(r"[0-9a-f]{16}", token) else None

    @staticmethod
    def _short_revision(context_revision: str) -> str:
        return context_revision.removeprefix("kir122:")[:12]

    @staticmethod
    def _decimal(value: Decimal) -> str:
        rendered = format(value.normalize(), "f")
        return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered

    @staticmethod
    def _unit_label(unit: object) -> str:
        raw = unit.value if isinstance(unit, Unit) else str(unit)
        return _RU_UNIT.get(raw, raw)

    @staticmethod
    def _rule_warning_text(warning: RuleWarning) -> str:
        return {
            RuleWarning.PREFERENCE_NOT_MEDICAL_NECESSITY: (
                "Это предпочтение, а не медицинская необходимость."
            ),
            RuleWarning.NO_RULE_NOT_SAFETY_CLEARANCE: (
                "Отсутствие поддерживаемого правила не подтверждает совместимость или безопасность."
            ),
            RuleWarning.NULL_GAP_MUST_REMAIN_NULL: (
                "Точный интервал не установлен и не должен быть придуман."
            ),
            RuleWarning.NO_PERSONALIZED_DOSE: (
                "Правило не создаёт и не изменяет персональную дозу."
            ),
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
        }[warning]

    @staticmethod
    def _reference_label(reference_type: ReferenceType) -> str:
        if reference_type is ReferenceType.UL:
            return "UL (верхний допустимый уровень)"
        if reference_type is ReferenceType.SAFE_LEVEL:
            return "SAFE_LEVEL (отдельный тип, не UL)"
        return reference_type.value

    @staticmethod
    def _stale_screen() -> Screen:
        return Screen(
            text=(
                "Экран устарел: состав, порция или план уже изменились. "
                "Я не применил старое действие и не переименовал старый расчёт как новый."
            ),
            rows=((Button("Обновить итоги", "k122tot"),),),
        )
