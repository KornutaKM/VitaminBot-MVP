from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from vitaminbot.application.kir116 import Button, Screen
from vitaminbot.application.kir146 import CardContext, CardRender
from vitaminbot.domain import LifeStage, SexApplicability
from vitaminbot.nutrition.reference_values import (
    EU_EFSA_REFERENCE_DATASET,
    ApplicabilityReason,
    ExposureContext,
    Jurisdiction,
    LookupResult,
    LookupStatus,
    PhysiologicalCondition,
    PopulationProfile,
    ReferenceLifecycle,
    ReferenceQuery,
    ReferenceRecord,
    ReferenceType,
    lookup_reference,
)
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir174 import (
    ApplicabilityProfileRecord,
    KIR174Store,
    StaleApplicabilityAction,
)


class ApplicabilityField(StrEnum):
    AGE = "age"
    SEX = "sex"
    LIFE_STAGE = "life_stage"
    PHYSIOLOGICAL_CONDITION = "physiological_condition"
    IRON_MEDICAL_SUPERVISION = "iron_medical_supervision"


@dataclass(frozen=True, slots=True)
class BoundApplicabilityContext:
    profile: PopulationProfile
    iron_exposure: ExposureContext
    context_revision: str
    profile_revision: int
    iron_scope_key: str
    iron_scope_revision: int


_REASON_FIELD_ORDER = (
    (ApplicabilityReason.MISSING_AGE, ApplicabilityField.AGE),
    (ApplicabilityReason.MISSING_SEX, ApplicabilityField.SEX),
    (ApplicabilityReason.MISSING_LIFE_STAGE, ApplicabilityField.LIFE_STAGE),
    (
        ApplicabilityReason.MISSING_PHYSIOLOGICAL_CONDITION,
        ApplicabilityField.PHYSIOLOGICAL_CONDITION,
    ),
    (
        ApplicabilityReason.MISSING_MEDICAL_SUPERVISION_STATUS,
        ApplicabilityField.IRON_MEDICAL_SUPERVISION,
    ),
)


class KIR174Controller:
    """Lookup-driven JIT applicability flow defined by accepted KIR-173."""

    def __init__(self, *, base_store: KIR116Store, store: KIR174Store) -> None:
        self._base_store = base_store
        self._store = store

    @staticmethod
    def iron_scope_key(base_revision: str) -> str:
        digest = hashlib.sha256(base_revision.encode("utf-8")).hexdigest()[:16]
        return f"iron:{digest}"

    def bound_context(
        self,
        telegram_user_id: int,
        *,
        base_revision: str,
    ) -> BoundApplicabilityContext:
        user_id = self._base_store.ensure_user(telegram_user_id)
        profile_record = self._store.profile(user_id)
        scope_key = self.iron_scope_key(base_revision)
        supervision = self._store.iron_supervision(user_id, scope_key)
        profile = self._population_profile(profile_record)
        exposure = ExposureContext(
            under_medical_supervision=supervision.under_medical_supervision
        )
        revision_material = (
            f"{base_revision}|profile:{profile_record.revision}|"
            f"iron:{scope_key}:{supervision.revision}"
        )
        revision = hashlib.sha256(revision_material.encode("utf-8")).hexdigest()
        return BoundApplicabilityContext(
            profile=profile,
            iron_exposure=exposure,
            context_revision=revision,
            profile_revision=profile_record.revision,
            iron_scope_key=scope_key,
            iron_scope_revision=supervision.revision,
        )

    def card_context(self, telegram_user_id: int, _substance_key: str) -> CardContext:
        base_revision = f"kir174-card:{EU_EFSA_REFERENCE_DATASET.version}"
        bound = self.bound_context(telegram_user_id, base_revision=base_revision)
        return CardContext(
            profile=bound.profile,
            exposure=bound.iron_exposure if _substance_key == "iron" else ExposureContext(),
            jurisdiction=Jurisdiction.EU.value,
            context_revision=bound.context_revision,
            locale="en",
        )

    def has_pending_text(self, telegram_user_id: int) -> bool:
        user_id = self._base_store.ensure_user(telegram_user_id)
        return self._store.age_session(user_id) is not None

    def text(
        self,
        telegram_user_id: int,
        text: str,
        *,
        action_key: str,
    ) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        session = self._store.age_session(user_id)
        if session is None:
            return Screen(text="Сейчас я не жду значение применимости.")
        try:
            value = int(text.strip())
        except ValueError:
            return self._age_input_screen(session.age_unit)

        try:
            profile = self._store.save_age(user_id, action_key, value=value)
        except ValueError:
            return self._age_input_screen(session.age_unit)
        except StaleApplicabilityAction:
            return self._stale_screen()
        return Screen(
            text=(
                "Контекст применимости обновлён. "
                "Справочное значение будет пересчитано из текущего подтверждённого контекста."
            ),
            rows=(
                (Button("Вернуться к справочным значениям", "k122safe"),),
                (Button("Карточки нутриентов", "k146list"),),
            ),
        )

    def profile_screen(self, telegram_user_id: int) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        record = self._store.profile(user_id)
        lines = [
            "Контекст применимости",
            "",
            "Показываются только факты, которые вы уже подтвердили для справочных значений.",
        ]
        rows: list[tuple[Button, ...]] = []

        if record.completed_months is not None:
            lines.append(f"Возраст: {record.completed_months} полных мес.")
            rows.append((Button("Изменить возраст", f"k174edit:age:{record.revision}"),))
            rows.append((Button("Удалить возраст", f"k174del:age:{record.revision}"),))
        elif record.completed_years is not None:
            lines.append(f"Возраст: {record.completed_years} полных лет")
            rows.append((Button("Изменить возраст", f"k174edit:age:{record.revision}"),))
            rows.append((Button("Удалить возраст", f"k174del:age:{record.revision}"),))

        for field, label, value in (
            ("sex_applicability", "Категория пола источника", record.sex_applicability),
            ("life_stage", "Жизненный этап", record.life_stage),
            (
                "physiological_condition",
                "Контекст железа до/после менопаузы",
                record.physiological_condition,
            ),
        ):
            if value is not None:
                lines.append(f"{label}: {self._profile_value_label(field, value)}")
                short = self._field_short(field)
                rows.append((Button(f"Изменить: {label}", f"k174edit:{short}:{record.revision}"),))
                rows.append((Button(f"Удалить: {label}", f"k174del:{short}:{record.revision}"),))

        if len(lines) == 3:
            lines.append("Подтверждённых пользовательских фактов пока нет.")
        lines.extend(
            [
                "",
                "Эти данные не являются медицинским профилем и не используются для вывода «безопасно для вас».",
            ]
        )
        return Screen(text="\n".join(lines), rows=tuple(rows))

    def iron_scope_screen(self, telegram_user_id: int, scope_token: str) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        record = self._store.iron_supervision(user_id, f"iron:{scope_token}")
        if record.under_medical_supervision is None:
            text = (
                "Контекст текущего приёма железа\n\n"
                "Статус медицинского наблюдения не подтверждён."
            )
        else:
            answer = "да" if record.under_medical_supervision else "нет"
            text = (
                "Контекст текущего приёма железа\n\n"
                f"Приём под медицинским наблюдением: {answer}."
            )
        rows = (
            (
                Button("Да", f"k174med:{scope_token}:{record.revision}:yes"),
                Button("Нет", f"k174med:{scope_token}:{record.revision}:no"),
            ),
            (
                Button(
                    "Удалить ответ",
                    f"k174mdel:{scope_token}:{record.revision}",
                ),
            ),
            (Button("Назад", "k122safe"),),
        )
        return Screen(text=text, rows=rows)

    def prompt_for_pairs(
        self,
        telegram_user_id: int,
        *,
        pairs: tuple[tuple[str, ReferenceType], ...],
        base_revision: str,
    ) -> Screen | None:
        bound = self.bound_context(telegram_user_id, base_revision=base_revision)
        for substance_key, reference_type in pairs:
            exposure = (
                bound.iron_exposure
                if substance_key == "iron"
                else ExposureContext()
            )
            if self._all_candidates_blocked_by_non_user_gap(
                substance_key, reference_type, exposure
            ):
                continue
            lookup = lookup_reference(
                EU_EFSA_REFERENCE_DATASET,
                ReferenceQuery(
                    substance_key=substance_key,
                    reference_type=reference_type,
                    profile=bound.profile,
                    exposure=exposure,
                    context_revision=bound.context_revision,
                ),
            )
            prompt = self._prompt_for_lookup(lookup, bound)
            if prompt is not None:
                return prompt
        return None

    def prompt_for_card(self, telegram_user_id: int, render: CardRender) -> Screen | None:
        if render.binding is None:
            return None
        pairs: list[tuple[str, ReferenceType]] = []
        for snapshot in render.binding.references:
            try:
                reference_type = ReferenceType(snapshot.reference_type)
            except ValueError:
                continue
            pairs.append((snapshot.subject_key, reference_type))
        return self.prompt_for_pairs(
            telegram_user_id,
            pairs=tuple(pairs),
            base_revision=f"kir174-card:{EU_EFSA_REFERENCE_DATASET.version}",
        )

    def callback(
        self,
        telegram_user_id: int,
        data: str,
        *,
        action_key: str,
    ) -> Screen:
        user_id = self._base_store.ensure_user(telegram_user_id)
        parts = data.split(":")
        try:
            if data == "k174profile":
                return self.profile_screen(telegram_user_id)
            if data == "k174skip":
                if self._store.age_session(user_id) is not None:
                    self._store.cancel_age_input(user_id)
                return Screen(
                    text=(
                        "Ничего не сохранено. Применимость остаётся неизвестной, "
                        "поэтому вывод остаётся недоступным."
                    ),
                    rows=(
                        (Button("Назад к справочным значениям", "k122safe"),),
                        (Button("Карточки нутриентов", "k146list"),),
                    ),
                )
            if parts[0] == "k174age" and len(parts) == 3:
                unit = {"m": "months", "y": "years"}[parts[1]]
                revision = int(parts[2])
                self._store.begin_age_input(
                    user_id,
                    action_key,
                    age_unit=unit,
                    expected_revision=revision,
                )
                return self._age_input_screen(unit)
            if parts[0] == "k174set" and len(parts) == 4:
                field = self._field_name(parts[1])
                revision = int(parts[2])
                value = parts[3]
                self._store.save_profile_fact(
                    user_id,
                    action_key,
                    field=field,
                    value=value,
                    expected_revision=revision,
                )
                return Screen(
                    text="Контекст применимости обновлён.",
                    rows=(
                        (Button("Назад к справочным значениям", "k122safe"),),
                        (Button("Карточки нутриентов", "k146list"),),
                    ),
                )
            if parts[0] == "k174med" and len(parts) == 4:
                scope_key = f"iron:{parts[1]}"
                revision = int(parts[2])
                value = {"yes": True, "no": False}[parts[3]]
                self._store.save_iron_supervision(
                    user_id,
                    action_key,
                    scope_key=scope_key,
                    value=value,
                    expected_revision=revision,
                )
                return Screen(
                    text="Контекст текущего приёма железа обновлён.",
                    rows=((Button("Назад к справочным значениям", "k122safe"),),),
                )
            if parts[0] == "k174iron" and len(parts) == 2:
                return self.iron_scope_screen(telegram_user_id, parts[1])
            if parts[0] == "k174mdel" and len(parts) == 3:
                scope_key = f"iron:{parts[1]}"
                revision = int(parts[2])
                self._store.delete_iron_supervision(
                    user_id,
                    action_key,
                    scope_key=scope_key,
                    expected_revision=revision,
                )
                return self.iron_scope_screen(telegram_user_id, parts[1])
            if parts[0] == "k174edit" and len(parts) == 3:
                revision = int(parts[2])
                return self._edit_prompt(parts[1], revision)
            if parts[0] == "k174del" and len(parts) == 3:
                field = self._field_name(parts[1])
                revision = int(parts[2])
                self._store.delete_profile_fact(
                    user_id,
                    action_key,
                    field="age" if parts[1] == "age" else field,
                    expected_revision=revision,
                )
                return self.profile_screen(telegram_user_id)
        except (KeyError, ValueError, StaleApplicabilityAction):
            return self._stale_screen()
        return Screen(text="Это действие применимости сейчас недоступно.")

    def _prompt_for_lookup(
        self,
        lookup: LookupResult,
        bound: BoundApplicabilityContext,
    ) -> Screen | None:
        if lookup.status is not LookupStatus.INDETERMINATE:
            return None
        reasons = set(lookup.reasons)
        for reason, field in _REASON_FIELD_ORDER:
            if reason not in reasons:
                continue
            if field is ApplicabilityField.AGE:
                return self._age_choice_screen(bound.profile_revision)
            if field is ApplicabilityField.SEX:
                return self._sex_screen(bound.profile_revision)
            if field is ApplicabilityField.LIFE_STAGE:
                return self._life_stage_screen(bound.profile_revision)
            if field is ApplicabilityField.PHYSIOLOGICAL_CONDITION:
                return self._physiology_screen(bound.profile_revision)
            if field is ApplicabilityField.IRON_MEDICAL_SUPERVISION:
                token = bound.iron_scope_key.removeprefix("iron:")
                return Screen(
                    text=(
                        "Для текущего SAFE_LEVEL железа источник исключает приём под "
                        "медицинским наблюдением. Нужно знать только относится ли это "
                        "к текущему приёму железа."
                    ),
                    rows=(
                        (
                            Button(
                                "Да",
                                f"k174med:{token}:{bound.iron_scope_revision}:yes",
                            ),
                            Button(
                                "Нет",
                                f"k174med:{token}:{bound.iron_scope_revision}:no",
                            ),
                        ),
                        (Button("Не сейчас", "k174skip"),),
                    ),
                )
        return None

    @staticmethod
    def _population_profile(record: ApplicabilityProfileRecord) -> PopulationProfile:
        age_months: int | None
        if record.completed_months is not None:
            age_months = record.completed_months
        elif record.completed_years is not None:
            age_months = record.completed_years * 12
        else:
            age_months = None
        return PopulationProfile(
            age_months=age_months,
            sex=(
                None
                if record.sex_applicability is None
                else SexApplicability(record.sex_applicability)
            ),
            life_stage=(
                None if record.life_stage is None else LifeStage(record.life_stage)
            ),
            physiological_condition=(
                None
                if record.physiological_condition is None
                else PhysiologicalCondition(record.physiological_condition)
            ),
        )

    @staticmethod
    def _all_candidates_blocked_by_non_user_gap(
        substance_key: str,
        reference_type: ReferenceType,
        exposure: ExposureContext,
    ) -> bool:
        candidates = tuple(
            record
            for record in EU_EFSA_REFERENCE_DATASET.records
            if record.lifecycle is ReferenceLifecycle.ACTIVE
            and record.jurisdiction is Jurisdiction.EU
            and record.substance_key == substance_key
            and record.reference_type is reference_type
        )
        if not candidates:
            return False

        def blocked(record: ReferenceRecord) -> bool:
            return bool(
                (record.exposure_match_required and exposure.exposure_basis is None)
                or record.dietary_phytate_mg_per_day is not None
                or record.requires_minimal_cutaneous_synthesis
                or (record.allowed_source_classes and exposure.source_class is None)
                or (record.allowed_dha_forms and exposure.dha_form is None)
                or (
                    record.requires_epa_and_dha_amounts
                    and (exposure.epa_mg_per_day is None or exposure.dha_mg_per_day is None)
                )
                or (
                    record.excludes_background_dietary_dha
                    and (
                        exposure.amount_includes_background_dietary_dha is None
                        or exposure.coverage is None
                    )
                )
            )

        return all(blocked(record) for record in candidates)

    @staticmethod
    def _age_choice_screen(revision: int) -> Screen:
        return Screen(
            text=(
                "Для этого справочного значения источник использует возрастные группы. "
                "Нужен возраст только для выбора подходящей группы."
            ),
            rows=(
                (
                    Button("Младше 2 лет", f"k174age:m:{revision}"),
                    Button("2 года и старше", f"k174age:y:{revision}"),
                ),
                (Button("Не сейчас", "k174skip"),),
            ),
        )

    @staticmethod
    def _age_input_screen(unit: str) -> Screen:
        if unit == "months":
            instruction = "Отправьте число полных месяцев от 0 до 23."
        else:
            instruction = "Отправьте число полных лет, начиная с 2. Дата рождения не нужна."
        return Screen(text=instruction, rows=((Button("Не сейчас", "k174skip"),),))

    @staticmethod
    def _sex_screen(revision: int) -> Screen:
        return Screen(
            text=(
                "Для этого справочного значения источник приводит разные значения по полу. "
                "Этот ответ нужен только для выбора подходящей записи источника."
            ),
            rows=(
                (
                    Button("Мужской", f"k174set:sex:{revision}:male"),
                    Button("Женский", f"k174set:sex:{revision}:female"),
                ),
                (Button("Не сейчас", "k174skip"),),
            ),
        )

    @staticmethod
    def _life_stage_screen(revision: int) -> Screen:
        return Screen(
            text=(
                "Для этого справочного значения источник отдельно рассматривает "
                "беременность, грудное вскармливание и контекст вне них."
            ),
            rows=(
                (Button("Вне беременности/лактации", f"k174set:life:{revision}:general"),),
                (Button("Беременность", f"k174set:life:{revision}:pregnancy"),),
                (Button("Грудное вскармливание", f"k174set:life:{revision}:lactation"),),
                (Button("Не сейчас", "k174skip"),),
            ),
        )

    @staticmethod
    def _physiology_screen(revision: int) -> Screen:
        return Screen(
            text=(
                "Для справочных значений железа у взрослых в текущем источнике "
                "различаются периоды до и после менопаузы."
            ),
            rows=(
                (
                    Button(
                        "До менопаузы",
                        f"k174set:phys:{revision}:premenopausal",
                    ),
                    Button(
                        "После менопаузы",
                        f"k174set:phys:{revision}:postmenopausal",
                    ),
                ),
                (Button("Не сейчас", "k174skip"),),
            ),
        )

    def _edit_prompt(self, field: str, revision: int) -> Screen:
        if field == "age":
            return self._age_choice_screen(revision)
        if field == "sex":
            return self._sex_screen(revision)
        if field == "life":
            return self._life_stage_screen(revision)
        if field == "phys":
            return self._physiology_screen(revision)
        raise ValueError("unsupported edit field")

    @staticmethod
    def _field_name(short: str) -> str:
        return {
            "sex": "sex_applicability",
            "life": "life_stage",
            "phys": "physiological_condition",
            "age": "age",
        }[short]

    @staticmethod
    def _field_short(field: str) -> str:
        return {
            "sex_applicability": "sex",
            "life_stage": "life",
            "physiological_condition": "phys",
        }[field]

    @staticmethod
    def _profile_value_label(field: str, value: str) -> str:
        labels = {
            ("sex_applicability", "male"): "мужской",
            ("sex_applicability", "female"): "женский",
            ("life_stage", "general"): "вне беременности/лактации",
            ("life_stage", "pregnancy"): "беременность",
            ("life_stage", "lactation"): "грудное вскармливание",
            ("physiological_condition", "premenopausal"): "до менопаузы",
            ("physiological_condition", "postmenopausal"): "после менопаузы",
        }
        return labels[(field, value)]

    @staticmethod
    def _stale_screen() -> Screen:
        return Screen(
            text=(
                "Контекст применимости изменился. Старое действие не применено. "
                "Откройте справочный экран ещё раз."
            ),
            rows=((Button("Справочные значения", "k122safe"),),),
        )
