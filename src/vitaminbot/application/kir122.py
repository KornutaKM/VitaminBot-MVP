from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Final

from vitaminbot.application.kir116 import Button, Screen
from vitaminbot.application.kir146 import CardContext
from vitaminbot.domain import (
    AmountBasis,
    QuantityBasis,
    ResolutionStatus,
    SubjectKind,
    Unit,
)
from vitaminbot.nutrition.aggregation import (
    DailyAggregate,
    DailyAggregationResult,
    ConfirmedPlannedContribution,
    aggregate_daily_contributions,
)
from vitaminbot.nutrition.normalization import (
    ComputationTrace,
    ComputedAmount,
    NormalizationError,
    NormalizationOutcome,
    UnresolvedReason,
    normalize_per_consumption_unit,
    normalize_planned_daily_amount,
)
from vitaminbot.nutrition.reference_values import ExposureContext, PopulationProfile
from vitaminbot.nutrition.rules import (
    BoundDailyAggregation,
    EventRelation,
    ItemSourceKind,
    MealContextPreference,
    RoutineBucket,
    RuleEngineResult,
    RuleEvaluationContext,
    RuleStatus,
    SchedulingItem,
    SplitAction,
    UserRoutinePreference,
    evaluate_rule_engine,
)
from vitaminbot.persistence.kir122 import (
    KIR122InvalidTransition,
    KIR122RecordNotFound,
    KIR122StaleAction,
    KIR122Store,
    NutrientEntrySession,
    SnapshotSupplement,
    VerticalSnapshot,
)


@dataclass(frozen=True, slots=True)
class _SubjectSpec:
    key: str
    display_name_ru: str
    display_name_en: str
    subject_id: str
    amount_basis: AmountBasis


_SUBJECTS: Final[dict[str, _SubjectSpec]] = {
    "vitamin_d": _SubjectSpec(
        "vitamin_d", "Витамин D", "Vitamin D", "analyte:vitamin-d", AmountBasis.ANALYTE
    ),
    "vitamin_c": _SubjectSpec(
        "vitamin_c", "Витамин C", "Vitamin C", "analyte:vitamin-c", AmountBasis.ANALYTE
    ),
    "magnesium": _SubjectSpec(
        "magnesium", "Магний", "Magnesium", "analyte:magnesium", AmountBasis.ELEMENTAL
    ),
    "zinc": _SubjectSpec("zinc", "Цинк", "Zinc", "analyte:zinc", AmountBasis.ELEMENTAL),
    "selenium": _SubjectSpec(
        "selenium", "Селен", "Selenium", "analyte:selenium", AmountBasis.ELEMENTAL
    ),
    "vitamin_b6": _SubjectSpec(
        "vitamin_b6", "Витамин B6", "Vitamin B6", "analyte:vitamin-b6", AmountBasis.ANALYTE
    ),
    "vitamin_b12": _SubjectSpec(
        "vitamin_b12", "Витамин B12", "Vitamin B12", "analyte:vitamin-b12", AmountBasis.ANALYTE
    ),
    "iron": _SubjectSpec("iron", "Железо", "Iron", "analyte:iron", AmountBasis.ELEMENTAL),
    "calcium": _SubjectSpec(
        "calcium", "Кальций", "Calcium", "analyte:calcium", AmountBasis.ELEMENTAL
    ),
}

_ALIASES_RU: Final[dict[str, str]] = {
    "витамин d": "vitamin_d",
    "витамин д": "vitamin_d",
    "витамин c": "vitamin_c",
    "витамин с": "vitamin_c",
    "магний": "magnesium",
    "цинк": "zinc",
    "селен": "selenium",
    "витамин b6": "vitamin_b6",
    "витамин в6": "vitamin_b6",
    "витамин b12": "vitamin_b12",
    "витамин в12": "vitamin_b12",
    "железо": "iron",
    "кальций": "calcium",
}

_ALIASES_EN: Final[dict[str, str]] = {
    "vitamin d": "vitamin_d",
    "vitamin c": "vitamin_c",
    "magnesium": "magnesium",
    "zinc": "zinc",
    "selenium": "selenium",
    "vitamin b6": "vitamin_b6",
    "b6": "vitamin_b6",
    "vitamin b12": "vitamin_b12",
    "b12": "vitamin_b12",
    "iron": "iron",
    "calcium": "calcium",
}


@dataclass(frozen=True, slots=True)
class VerticalAnalysis:
    snapshot: VerticalSnapshot
    aggregation: DailyAggregationResult
    rules: RuleEngineResult
    item_names: tuple[tuple[str, str], ...]


class KIR122AnalysisService:
    """Build the KIR-122 scientific projection from one immutable DB snapshot."""

    def __init__(self, store: KIR122Store) -> None:
        self._store = store

    def analyze(self, telegram_user_id: int) -> VerticalAnalysis:
        user_id = self._store.ensure_user(telegram_user_id)
        snapshot = self._store.snapshot(user_id)
        contributions: list[ConfirmedPlannedContribution] = []
        scheduling_items: list[SchedulingItem] = []
        preferences: list[UserRoutinePreference] = []
        item_names: list[tuple[str, str]] = []

        for supplement in snapshot.supplements:
            if supplement.plan is None:
                continue

            resolved_per_unit: list[ComputedAmount] = []
            for amount in supplement.amounts:
                try:
                    per_unit = normalize_per_consumption_unit(amount, supplement.serving)
                except NormalizationError:
                    per_unit = NormalizationOutcome(
                        status=ResolutionStatus.AMBIGUOUS,
                        reason=UnresolvedReason.INPUT_UNRESOLVED,
                    )

                if per_unit.status is ResolutionStatus.RESOLVED and per_unit.amount is not None:
                    resolved_per_unit.append(per_unit.amount)

                try:
                    daily = (
                        normalize_planned_daily_amount(per_unit.amount, supplement.plan)
                        if per_unit.status is ResolutionStatus.RESOLVED
                        and per_unit.amount is not None
                        else per_unit
                    )
                except NormalizationError:
                    daily = NormalizationOutcome(
                        status=ResolutionStatus.AMBIGUOUS,
                        reason=UnresolvedReason.INPUT_UNRESOLVED,
                    )

                contributions.append(
                    ConfirmedPlannedContribution(
                        contribution_id=(
                            f"{supplement.instance_id}:{amount.amount_id}:{supplement.plan.version}"
                        ),
                        confirmation_ref=f"confirmed:{amount.amount_id}",
                        product_id=supplement.product_id,
                        formulation_id=supplement.formulation_id,
                        tracked_instance_id=supplement.instance_id,
                        plan_id=supplement.plan.plan_id,
                        plan_version=supplement.plan.version,
                        expected_subject_kind=amount.subject_kind,
                        expected_subject_id=amount.subject_id,
                        expected_amount_basis=(
                            amount.amount_basis
                            if amount.amount_basis is not None
                            else AmountBasis.ANALYTE
                        ),
                        expected_equivalence_basis=amount.equivalence_basis,
                        expected_unit=None,
                        outcome=daily,
                    )
                )

            for event in supplement.plan.events:
                event_amounts = tuple(
                    self._event_amount(per_unit, event.consumption_units)
                    for per_unit in resolved_per_unit
                )
                if not event_amounts:
                    continue
                item_id = f"{supplement.instance_id}:{event.event_id}"
                scheduling_items.append(
                    SchedulingItem(
                        item_id=item_id,
                        product_id=supplement.product_id,
                        formulation_id=supplement.formulation_id,
                        tracked_instance_id=supplement.instance_id,
                        plan_id=supplement.plan.plan_id,
                        plan_version=supplement.plan.version,
                        event_id=event.event_id,
                        context_revision=snapshot.context_revision,
                        source_kind=ItemSourceKind.SUPPLEMENT,
                        amounts=event_amounts,
                        confirmed_consumption_units=event.consumption_units,
                        units_independently_schedulable=(
                            supplement.unit_label in {"capsule", "tablet", "softgel"}
                        ),
                    )
                )
                item_names.append((item_id, supplement.name))
                if event.schedule_label in {"morning", "day", "evening"}:
                    preferences.append(
                        UserRoutinePreference(
                            preference_id=f"preference:{item_id}",
                            item_id=item_id,
                            bucket=RoutineBucket(event.schedule_label),
                            context_revision=snapshot.context_revision,
                        )
                    )

        aggregation = aggregate_daily_contributions(contributions)
        context = RuleEvaluationContext(
            context_revision=snapshot.context_revision,
            items=tuple(scheduling_items),
            user_preferences=tuple(preferences),
        )
        rules = evaluate_rule_engine(
            context,
            aggregation=BoundDailyAggregation(
                aggregation=aggregation,
                context_revision=snapshot.context_revision,
            ),
        )
        return VerticalAnalysis(
            snapshot=snapshot,
            aggregation=aggregation,
            rules=rules,
            item_names=tuple(item_names),
        )

    def card_context(self, telegram_user_id: int, substance_key: str) -> CardContext:
        analysis = self.analyze(telegram_user_id)
        spec = _SUBJECTS.get(substance_key)
        confirmed = None
        if spec is not None:
            for aggregate in analysis.aggregation.aggregates:
                if (
                    aggregate.key.subject_id == spec.subject_id
                    and aggregate.key.amount_basis is spec.amount_basis
                    and aggregate.is_complete
                    and aggregate.known_total is not None
                    and aggregate.unit is not None
                ):
                    confirmed = self._aggregate_amount(aggregate)
                    break
        return CardContext(
            profile=PopulationProfile(),
            exposure=ExposureContext(),
            jurisdiction="EU",
            context_revision=analysis.snapshot.context_revision,
            locale="en",
            confirmed_amount=confirmed,
        )

    def rationale_for_instance(
        self,
        telegram_user_id: int,
        instance_id: str,
    ) -> str:
        analysis = self.analyze(telegram_user_id)
        names = dict(analysis.item_names)
        relevant_item_ids = tuple(
            item_id for item_id in names if item_id.startswith(f"{instance_id}:")
        )
        matched = [
            result
            for result in analysis.rules.scheduling_results
            if any(item_id in result.item_ids for item_id in relevant_item_ids)
            and result.status is RuleStatus.MATCHED_PREFERENCE
        ]
        insufficient = [
            result
            for result in analysis.rules.scheduling_results
            if any(item_id in result.item_ids for item_id in relevant_item_ids)
            and result.status is RuleStatus.INSUFFICIENT_EVIDENCE
        ]

        if matched:
            parts: list[str] = []
            for result in matched:
                others = sorted(
                    {
                        names[item_id]
                        for item_id in result.item_ids
                        if item_id in names and not item_id.startswith(f"{instance_id}:")
                    }
                )
                if result.event_relation is EventRelation.AVOID_SAME_EVENT:
                    partner = f" с {', '.join(others)}" if others else ""
                    parts.append(
                        "Доказательная заметка: правило предпочитает разные события"
                        f"{partner}. Точный интервал не установлен и не додумывается."
                    )
                elif result.meal_context_preference in {
                    MealContextPreference.WITH_MEAL,
                    MealContextPreference.MEAL_OR_SNACK_WITH_SOME_FAT,
                }:
                    parts.append(
                        "Доказательная заметка: есть подтверждённое предпочтение контекста еды. "
                        "Morning/Day/Evening остаётся вашим режимом, а не медицинским временем."
                    )
                elif result.split_action is SplitAction.DISTRIBUTE_EXISTING_INTACT_UNITS:
                    parts.append(
                        "Доказательная заметка: правило допускает распределение уже "
                        "запланированных целых единиц; количество не увеличивается."
                    )
            if parts:
                return "\n\n".join(parts)

        if insufficient:
            return (
                "Недостаточно подтверждённых данных для более сильного вывода. "
                "Это не означает совместимость или безопасность."
            )
        return (
            "Время сейчас отражает вашу настройку режима. Поддерживаемого доказательного "
            "правила для изменения этого времени не найдено; отсутствие правила не является "
            "подтверждением совместимости или безопасности."
        )

    @staticmethod
    def _event_amount(per_unit: ComputedAmount, units: Decimal) -> ComputedAmount:
        return ComputedAmount(
            subject_kind=per_unit.subject_kind,
            subject_id=per_unit.subject_id,
            value=_exact_product(per_unit.value, units),
            unit=per_unit.unit,
            amount_basis=per_unit.amount_basis,
            quantity_basis=QuantityBasis.ABSOLUTE,
            source_quantity_basis_ids=per_unit.source_quantity_basis_ids,
            source_amount_ids=per_unit.source_amount_ids,
            source_ids=per_unit.source_ids,
            traces=per_unit.traces
            + (
                ComputationTrace(
                    operation="planned_event_snapshot",
                    rule_id="kir-122-event-snapshot",
                    rule_version="1",
                ),
            ),
            chemical_form_id=per_unit.chemical_form_id,
            equivalence_basis=per_unit.equivalence_basis,
        )

    @staticmethod
    def _aggregate_amount(aggregate: DailyAggregate) -> ComputedAmount:
        contributors = tuple(
            sorted(aggregate.contributors, key=lambda item: item.contribution_id)
        )
        if (
            not aggregate.is_complete
            or aggregate.known_total is None
            or aggregate.unit is None
            or not contributors
        ):
            raise ValueError("aggregate is incomplete")
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
                        for item in contributors
                        for basis in item.original_amount.source_quantity_basis_ids
                    }
                )
            ),
            source_amount_ids=tuple(
                sorted(
                    {
                        amount_id
                        for item in contributors
                        for amount_id in item.original_amount.source_amount_ids
                    }
                )
            ),
            source_ids=tuple(
                sorted(
                    {
                        source_id
                        for item in contributors
                        for source_id in item.original_amount.source_ids
                    }
                )
            ),
            traces=tuple(
                trace for item in contributors for trace in item.original_amount.traces
            ),
            equivalence_basis=aggregate.key.equivalence_basis,
        )


class KIR122Controller:
    """Russian-first Telegram projection for totals and label-nutrient confirmation."""

    def __init__(self, store: KIR122Store, analysis: KIR122AnalysisService) -> None:
        self._store = store
        self._analysis = analysis

    def has_pending_text(self, telegram_user_id: int) -> bool:
        user_id = self._store.ensure_user(telegram_user_id)
        return self._store.has_pending_text(user_id)

    def cancel(self, telegram_user_id: int) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        self._store.cancel(user_id)
        return Screen(
            text="Ввод состава отменён. Уже подтверждённые данные и план не изменены.",
            rows=((Button("К веществам", "k122totals"),),),
        )

    def substances(self, telegram_user_id: int) -> Screen:
        analysis = self._analysis.analyze(telegram_user_id)
        if not analysis.snapshot.supplements:
            return Screen(
                text=(
                    "Вещества\n\nПока нет добавленных добавок. "
                    "Сначала добавьте продукт и подтвердите его данные."
                ),
                rows=((Button("Добавить добавку", "a"),),),
            )

        lines = ["Вещества — сумма по вашему подтверждённому плану", ""]
        rows: list[tuple[Button, ...]] = []
        if not analysis.aggregation.aggregates:
            lines.extend(
                [
                    "Подтверждённых строк состава для запланированных добавок пока нет.",
                    "Неподтверждённые или отсутствующие значения не считаются нулём.",
                ]
            )
        else:
            names_by_instance = {
                supplement.instance_id: supplement.name
                for supplement in analysis.snapshot.supplements
            }
            for aggregate in analysis.aggregation.aggregates:
                spec = _spec_for_subject(
                    aggregate.key.subject_id,
                    aggregate.key.amount_basis,
                )
                name = spec.display_name_ru if spec is not None else "Неопознанное вещество"
                if (
                    not aggregate.is_complete
                    or aggregate.known_total is None
                    or aggregate.unit is None
                ):
                    lines.append(f"• {name}: надёжная сумма недоступна")
                    lines.append(
                        "  Есть неразрешённые или конфликтующие данные; неизвестное не "
                        "трактуется как ноль."
                    )
                else:
                    lines.append(
                        f"• {name}: {_decimal(aggregate.known_total)} "
                        f"{_unit_label(aggregate.unit)} / день"
                    )
                    contributors = sorted(
                        {
                            names_by_instance.get(
                                contributor.tracked_instance_id,
                                "подтверждённый продукт",
                            )
                            for contributor in aggregate.contributors
                        }
                    )
                    if contributors:
                        lines.append(f"  Источники: {', '.join(contributors)}")
                    if spec is not None:
                        rows.append(
                            (
                                Button(
                                    f"{spec.display_name_ru}: источники и нормы",
                                    f"k146c:{spec.key}",
                                ),
                            )
                        )

        if analysis.aggregation.unresolved_contributors:
            lines.extend(
                [
                    "",
                    "Есть строки, которые нельзя включить в надёжную сумму. "
                    "Они не были молча отброшены или заменены нулём.",
                ]
            )
        lines.extend(
            [
                "",
                "Суммы рассчитаны только из подтверждённых label-значений и вашего "
                "текущего плана. Это не персональная рекомендация дозы.",
            ]
        )
        rows.append((Button("Добавить / уточнить состав", "k122add"),))
        rows.append((Button("Сегодня", "k120today"), Button("План", "k120p")))
        return Screen(text="\n".join(lines), rows=tuple(rows))

    def choose_supplement(self, telegram_user_id: int) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        supplements = self._store.list_supplement_refs(user_id)
        if not supplements:
            return Screen(
                text="Сначала добавьте добавку.",
                rows=((Button("Добавить добавку", "a"),),),
            )
        rows = tuple(
            (
                Button(
                    name[:42],
                    f"k122a:{_encode_instance(instance_id)}:{revision}",
                ),
            )
            for instance_id, name, revision in supplements
        )
        return Screen(
            text=(
                "Добавить строку состава\n\n"
                "Выберите продукт. Значение будет записано как то, что вы "
                "явно подтвердили с этикетки, а не как предположение VitaminBot."
            ),
            rows=rows + ((Button("Назад", "k122totals"),),),
        )

    def text(
        self,
        telegram_user_id: int,
        value: str,
        *,
        action_key: str,
    ) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        session = self._store.get_session(user_id)
        if session is None:
            return Screen(text="Сейчас VitaminBot не ждёт текст для состава.")

        try:
            if session.state == "nutrient_name":
                spec = _resolve_subject(value)
                if spec is None:
                    return Screen(
                        text=(
                            "Я не могу однозначно сопоставить это название с поддерживаемым "
                            "каноническим веществом. Ничего не сохранено.\n\n"
                            "Сейчас вручную поддерживаются: "
                            + ", ".join(spec.display_name_ru for spec in _SUBJECTS.values())
                            + "."
                        ),
                        rows=((Button("Отмена", "k122x"),),),
                    )
                self._store.set_subject(
                    user_id,
                    action_key,
                    substance_key=spec.key,
                    subject_kind=SubjectKind.ANALYTE,
                    subject_id=spec.subject_id,
                    amount_basis=spec.amount_basis,
                    equivalence_basis=None,
                    display_name=spec.display_name_en,
                )
                return Screen(
                    text=(
                        f"{spec.display_name_ru}\n\n"
                        "Введите числовое количество ровно для порции, указанной на "
                        "этикетке. Не вводите желаемую или рекомендованную дозу."
                    ),
                    rows=((Button("Отмена", "k122x"),),),
                )
            if session.state == "nutrient_value":
                amount = _positive_or_zero_decimal(value)
                updated = self._store.set_value(user_id, action_key, amount)
                return self._unit_screen(updated)
        except ValueError:
            return Screen(
                text="Введите неотрицательное конечное число, например 200 или 1.4.",
                rows=((Button("Отмена", "k122x"),),),
            )
        except (KIR122InvalidTransition, KIR122StaleAction, KIR122RecordNotFound):
            return self._stale_screen()

        return Screen(
            text="Этот шаг состава больше не ждёт текст. Используйте актуальные кнопки.",
            rows=((Button("К веществам", "k122totals"),),),
        )

    def callback(
        self,
        telegram_user_id: int,
        data: str,
        *,
        action_key: str,
    ) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        try:
            if data == "k122totals":
                return self.substances(telegram_user_id)
            if data == "k122add":
                return self.choose_supplement(telegram_user_id)
            if data == "k122x":
                return self.cancel(telegram_user_id)
            if data == "k122photo":
                return Screen(
                    text=(
                        "Фото этикетки\n\n"
                        "Контур KIR-117 требует авторизованный production-провайдер и "
                        "временное хранилище с TTL. Такой провайдер ещё не выбран, поэтому "
                        "VitaminBot не будет изображать распознавание или подтверждать "
                        "данные из фото. Ничего не сохранено."
                    ),
                    rows=(
                        (Button("Ввести вручную", "m"),),
                        (Button("Назад", "a"),),
                    ),
                )

            parts = data.split(":")
            action = parts[0]
            if action in {"k122", "k122a"}:
                instance_id = _decode_instance(parts[1])
                expected_revision = int(parts[2])
                self._store.begin_nutrient_entry(
                    user_id,
                    action_key,
                    instance_id,
                    expected_revision,
                )
                return Screen(
                    text=(
                        "Состав с этикетки\n\n"
                        "Введите название вещества, например «Магний» или «Vitamin B6». "
                        "Это подтверждение текста этикетки, а не оценка безопасности."
                    ),
                    rows=((Button("Отмена", "k122x"),),),
                )
            if action == "k122u":
                expected_revision = int(parts[1])
                unit = {
                    "mg": Unit.MILLIGRAM,
                    "ug": Unit.MICROGRAM,
                    "g": Unit.GRAM,
                    "iu": Unit.INTERNATIONAL_UNIT,
                }.get(parts[2])
                if unit is None:
                    raise ValueError("unsupported unit")
                session = self._store.set_unit(
                    user_id,
                    action_key,
                    unit,
                    expected_revision,
                )
                return self._review_screen(session)
            if action == "k122c":
                expected_revision = int(parts[1])
                self._store.confirm_amount(user_id, action_key, expected_revision)
                screen = self.substances(telegram_user_id)
                return Screen(
                    text=(
                        "Строка состава подтверждена. Суммы пересчитаны из нового "
                        "неизменяемого snapshot.\n\n" + screen.text
                    ),
                    rows=screen.rows,
                )
        except (IndexError, ValueError, KIR122InvalidTransition, KIR122StaleAction, KIR122RecordNotFound):
            return self._stale_screen()

        return Screen(
            text="Эта кнопка состава не поддерживается.",
            rows=((Button("К веществам", "k122totals"),),),
        )

    @staticmethod
    def _unit_screen(session: NutrientEntrySession) -> Screen:
        if session.display_name is None or session.pending_value is None:
            return KIR122Controller._stale_screen()
        return Screen(
            text=(
                "Единица на этикетке\n\n"
                f"Значение: {_decimal(session.pending_value)}. "
                "Выберите единицу буквально с этикетки. Единицы не угадываются."
            ),
            rows=(
                (
                    Button("mg", f"k122u:{session.revision}:mg"),
                    Button("µg", f"k122u:{session.revision}:ug"),
                    Button("g", f"k122u:{session.revision}:g"),
                ),
                (Button("IU", f"k122u:{session.revision}:iu"),),
                (Button("Отмена", "k122x"),),
            ),
        )

    @staticmethod
    def _review_screen(session: NutrientEntrySession) -> Screen:
        if (
            session.display_name is None
            or session.pending_value is None
            or session.pending_unit is None
        ):
            return KIR122Controller._stale_screen()
        spec = _SUBJECTS.get(session.substance_key or "")
        display = spec.display_name_ru if spec is not None else session.display_name
        return Screen(
            text=(
                "Проверьте строку состава\n\n"
                f"{display}: {_decimal(session.pending_value)} "
                f"{_unit_label(session.pending_unit)} на порцию с этикетки.\n\n"
                "Подтверждение означает только «это соответствует этикетке/моей правке». "
                "Оно не означает, что добавка безопасна или подходит вам."
            ),
            rows=(
                (Button("Подтвердить строку", f"k122c:{session.revision}"),),
                (Button("Отмена", "k122x"),),
            ),
        )

    @staticmethod
    def _stale_screen() -> Screen:
        return Screen(
            text=(
                "Это действие устарело или относится к уже изменённым данным. "
                "Повторная запись не выполнена."
            ),
            rows=((Button("К веществам", "k122totals"),),),
        )


def _resolve_subject(value: str) -> _SubjectSpec | None:
    normalized = " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
    key = _ALIASES_RU.get(normalized) or _ALIASES_EN.get(normalized)
    return None if key is None else _SUBJECTS.get(key)


def _spec_for_subject(subject_id: str, amount_basis: AmountBasis) -> _SubjectSpec | None:
    for spec in _SUBJECTS.values():
        if spec.subject_id == subject_id and spec.amount_basis is amount_basis:
            return spec
    return None


def _exact_product(left: Decimal, right: Decimal) -> Decimal:
    result = Fraction(left) * Fraction(right)
    denominator = result.denominator
    twos = 0
    fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ValueError("finite Decimal inputs unexpectedly produced non-terminating product")
    scale = max(twos, fives)
    numerator = result.numerator * (2 ** (scale - twos)) * (5 ** (scale - fives))
    sign = 1 if numerator < 0 else 0
    digits = tuple(int(digit) for digit in str(abs(numerator)))
    return Decimal((sign, digits, -scale))


def _positive_or_zero_decimal(value: str) -> Decimal:
    parsed = Decimal(value.strip().replace(",", "."))
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("amount must be finite and non-negative")
    return parsed


def _unit_label(unit: Unit) -> str:
    return "µg" if unit is Unit.MICROGRAM else unit.value


def _decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _encode_instance(instance_id: str) -> str:
    return base64.urlsafe_b64encode(instance_id.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_instance(token: str) -> str:
    if re.fullmatch(r"[0-9a-f]{16}", token):
        return f"instance:manual:{token}"
    padding = "=" * (-len(token) % 4)
    raw = base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8")
    if not raw or len(raw) > 120:
        raise ValueError("invalid supplement reference")
    return raw
