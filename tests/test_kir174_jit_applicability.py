from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from vitaminbot.application.kir116 import Screen
from vitaminbot.application.kir146 import NutrientCardRenderer
from vitaminbot.application.kir174 import KIR174Controller
from vitaminbot.domain import LifeStage, SexApplicability
from vitaminbot.nutrition.card_content import APPROVED_CARD_CONTENT
from vitaminbot.nutrition.reference_values import (
    EU_EFSA_REFERENCE_DATASET,
    PhysiologicalCondition,
    ReferenceType,
)
from vitaminbot.persistence import migrate
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir174 import KIR174Store


@pytest.fixture
def applicability_stack() -> Iterator[tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID]]:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for KIR-174 integration tests")

    schema = f"kir174_{uuid4().hex}"
    migrate(database_url, schema=schema)
    base_store = KIR116Store(database_url, schema=schema)
    store = KIR174Store(database_url, schema=schema)
    controller = KIR174Controller(base_store=base_store, store=store)
    user_id = base_store.ensure_user(174001)
    try:
        yield schema, base_store, store, controller, user_id
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def _button(screen: Screen, label: str) -> str:
    for row in screen.rows:
        for button in row:
            if button.label == label:
                return button.callback_data
    raise AssertionError(f"button not found: {label}")


def _all_callbacks(screen: Screen) -> tuple[str, ...]:
    return tuple(button.callback_data for row in screen.rows for button in row)


def _save_adult_female_general(
    controller: KIR174Controller,
    *,
    telegram_user_id: int,
) -> None:
    prompt = controller.prompt_for_pairs(
        telegram_user_id,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:vc",
    )
    assert prompt is not None
    age = controller.callback(
        telegram_user_id,
        _button(prompt, "2 года и старше"),
        action_key="age:begin",
    )
    assert "полных лет" in age.text
    controller.text(
        telegram_user_id,
        "30",
        action_key="age:save",
    )

    sex = controller.prompt_for_pairs(
        telegram_user_id,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:vc",
    )
    assert sex is not None
    assert "разные значения по полу" in sex.text
    controller.callback(
        telegram_user_id,
        _button(sex, "Женский"),
        action_key="sex:save",
    )

    stage = controller.prompt_for_pairs(
        telegram_user_id,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:vc",
    )
    assert stage is not None
    assert "беременность" in stage.text
    controller.callback(
        telegram_user_id,
        _button(stage, "Вне беременности/лактации"),
        action_key="stage:save",
    )


def test_general_profile_is_view_only_and_does_not_speculatively_question(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
) -> None:
    _schema, _base, store, controller, user_id = applicability_stack

    screen = controller.profile_screen(174001)

    assert "Подтверждённых пользовательских фактов пока нет." in screen.text
    assert screen.rows == ()
    profile = store.profile(user_id)
    assert profile.revision == 0
    assert profile.completed_months is None
    assert profile.completed_years is None
    assert profile.sex_applicability is None
    assert profile.life_stage is None
    assert profile.physiological_condition is None


def test_vitamin_c_real_lookup_drives_age_sex_life_stage_in_contract_order(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
) -> None:
    _schema, _base, store, controller, user_id = applicability_stack

    age = controller.prompt_for_pairs(
        174001,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:vc-order",
    )
    assert age is not None
    assert "возрастные группы" in age.text

    controller.callback(
        174001,
        _button(age, "2 года и старше"),
        action_key="order:age:begin",
    )
    controller.text(174001, "30", action_key="order:age:save")

    bound = controller.bound_context(174001, base_revision="base:vc-order")
    assert bound.profile.age_months == 360

    sex = controller.prompt_for_pairs(
        174001,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:vc-order",
    )
    assert sex is not None
    assert "разные значения по полу" in sex.text
    controller.callback(
        174001,
        _button(sex, "Женский"),
        action_key="order:sex:save",
    )

    stage = controller.prompt_for_pairs(
        174001,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:vc-order",
    )
    assert stage is not None
    assert "беременность" in stage.text
    controller.callback(
        174001,
        _button(stage, "Вне беременности/лактации"),
        action_key="order:stage:save",
    )

    final_bound = controller.bound_context(174001, base_revision="base:vc-order")
    assert final_bound.profile.age_months == 360
    assert final_bound.profile.sex is SexApplicability.FEMALE
    assert final_bound.profile.life_stage is LifeStage.GENERAL
    assert (
        controller.prompt_for_pairs(
            174001,
            pairs=(("vitamin_c", ReferenceType.PRI),),
            base_revision="base:vc-order",
        )
        is None
    )
    assert store.profile(user_id).revision == 3


def test_not_now_writes_no_applicability_fact_or_revision(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
) -> None:
    _schema, _base, store, controller, user_id = applicability_stack

    before = controller.bound_context(174001, base_revision="base:skip")
    prompt = controller.prompt_for_pairs(
        174001,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:skip",
    )
    assert prompt is not None
    skipped = controller.callback(
        174001,
        _button(prompt, "Не сейчас"),
        action_key="skip:no-write",
    )
    after = controller.bound_context(174001, base_revision="base:skip")

    assert "Ничего не сохранено" in skipped.text
    assert store.profile(user_id).revision == 0
    assert after.context_revision == before.context_revision
    assert after.profile.age_months is None


def test_age_correction_and_deletion_change_context_revision_and_restore_unknown(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
) -> None:
    _schema, _base, store, controller, user_id = applicability_stack

    prompt = controller.prompt_for_pairs(
        174001,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:revision",
    )
    assert prompt is not None
    controller.callback(
        174001,
        _button(prompt, "2 года и старше"),
        action_key="rev:age:begin",
    )
    controller.text(174001, "30", action_key="rev:age:save")
    first = controller.bound_context(174001, base_revision="base:revision")

    profile = controller.profile_screen(174001)
    edit = controller.callback(
        174001,
        _button(profile, "Изменить возраст"),
        action_key="rev:age:edit",
    )
    controller.callback(
        174001,
        _button(edit, "2 года и старше"),
        action_key="rev:age:rebegin",
    )
    controller.text(174001, "31", action_key="rev:age:resave")
    second = controller.bound_context(174001, base_revision="base:revision")

    assert second.profile.age_months == 372
    assert second.context_revision != first.context_revision

    profile = controller.profile_screen(174001)
    controller.callback(
        174001,
        _button(profile, "Удалить возраст"),
        action_key="rev:age:delete",
    )
    third = controller.bound_context(174001, base_revision="base:revision")

    assert third.profile.age_months is None
    assert third.context_revision != second.context_revision
    assert store.profile(user_id).revision == 3

    restored_prompt = controller.prompt_for_pairs(
        174001,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:revision",
    )
    assert restored_prompt is not None
    assert "возрастные группы" in restored_prompt.text


def test_iron_physiological_condition_is_exact_canonical_enum(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
) -> None:
    _schema, _base, _store, controller, _user_id = applicability_stack
    _save_adult_female_general(controller, telegram_user_id=174001)

    prompt = controller.prompt_for_pairs(
        174001,
        pairs=(("iron", ReferenceType.PRI),),
        base_revision="base:iron-pri",
    )
    assert prompt is not None
    assert "до и после менопаузы" in prompt.text
    controller.callback(
        174001,
        _button(prompt, "До менопаузы"),
        action_key="iron:phys:save",
    )

    bound = controller.bound_context(174001, base_revision="base:iron-pri")
    assert bound.profile.physiological_condition is PhysiologicalCondition.PREMENOPAUSAL


def test_iron_medical_supervision_is_scoped_to_current_exposure_revision(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
) -> None:
    _schema, _base, store, controller, user_id = applicability_stack

    age = controller.prompt_for_pairs(
        174001,
        pairs=(("iron", ReferenceType.SAFE_LEVEL),),
        base_revision="base:iron-a",
    )
    assert age is not None
    controller.callback(
        174001,
        _button(age, "2 года и старше"),
        action_key="iron:age:begin",
    )
    controller.text(174001, "30", action_key="iron:age:save")

    medical = controller.prompt_for_pairs(
        174001,
        pairs=(("iron", ReferenceType.SAFE_LEVEL),),
        base_revision="base:iron-a",
    )
    assert medical is not None
    assert "медицинским наблюдением" in medical.text
    controller.callback(
        174001,
        _button(medical, "Нет"),
        action_key="iron:medical:no",
    )

    a = controller.bound_context(174001, base_revision="base:iron-a")
    b = controller.bound_context(174001, base_revision="base:iron-b")
    assert a.iron_exposure.under_medical_supervision is False
    assert b.iron_exposure.under_medical_supervision is None
    assert store.iron_supervision(user_id, a.iron_scope_key).revision == 1
    assert store.iron_supervision(user_id, b.iron_scope_key).revision == 0


def test_derived_only_dha_gaps_never_create_user_question(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
) -> None:
    _schema, _base, store, controller, user_id = applicability_stack

    prompt = controller.prompt_for_pairs(
        174001,
        pairs=(("dha", ReferenceType.SAFE_LEVEL),),
        base_revision="base:dha",
    )

    assert prompt is None
    assert store.profile(user_id).revision == 0


def test_applicability_schema_contains_no_unapproved_profile_categories(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
) -> None:
    schema, _base, _store, _controller, _user_id = applicability_stack
    database_url = os.environ["DATABASE_URL"]

    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = 'user_applicability_profiles'
            ORDER BY ordinal_position
            """,
            (schema,),
        ).fetchall()

    columns = {row[0] for row in rows}
    assert columns == {
        "user_id",
        "completed_months",
        "completed_years",
        "sex_applicability",
        "life_stage",
        "physiological_condition",
        "revision",
        "updated_at",
    }
    forbidden = {
        "date_of_birth",
        "medications",
        "disease",
        "condition",
        "phytate",
        "skin",
        "sun",
        "location",
    }
    assert not columns.intersection(forbidden)


def test_sensitive_answers_are_not_emitted_to_normal_logs(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
    caplog: pytest.LogCaptureFixture,
) -> None:
    _schema, _base, store, _controller, user_id = applicability_stack
    caplog.set_level(logging.DEBUG)

    store.save_profile_fact(
        user_id,
        "privacy:sex",
        field="sex_applicability",
        value="female",
        expected_revision=0,
    )
    store.save_profile_fact(
        user_id,
        "privacy:stage",
        field="life_stage",
        value="pregnancy",
        expected_revision=1,
    )

    rendered_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "female" not in rendered_logs
    assert "pregnancy" not in rendered_logs


def test_kir146_binding_uses_persisted_context_and_old_render_becomes_stale(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
) -> None:
    _schema, _base, store, controller, user_id = applicability_stack
    _save_adult_female_general(controller, telegram_user_id=174001)

    renderer = NutrientCardRenderer(
        registry=APPROVED_CARD_CONTENT,
        dataset=EU_EFSA_REFERENCE_DATASET,
    )
    first_context = controller.card_context(174001, "vitamin_c")
    first_render = renderer.render_current("vitamin_c", first_context)
    assert first_render.binding is not None
    assert first_context.profile.age_months == 360
    assert first_context.profile.sex is SexApplicability.FEMALE

    current = store.profile(user_id)
    store.save_profile_fact(
        user_id,
        "stale:sex",
        field="sex_applicability",
        value="male",
        expected_revision=current.revision,
    )
    second_context = controller.card_context(174001, "vitamin_c")

    assert second_context.context_revision != first_context.context_revision
    assert renderer.is_stale(
        first_render.binding,
        context_revision=second_context.context_revision,
    )


def test_profile_fact_callbacks_are_revision_bound(
    applicability_stack: tuple[str, KIR116Store, KIR174Store, KIR174Controller, UUID],
) -> None:
    _schema, _base, store, controller, user_id = applicability_stack

    prompt = controller.prompt_for_pairs(
        174001,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:stale",
    )
    assert prompt is not None
    controller.callback(
        174001,
        _button(prompt, "2 года и старше"),
        action_key="stale:age:begin",
    )
    controller.text(174001, "30", action_key="stale:age:save")

    sex = controller.prompt_for_pairs(
        174001,
        pairs=(("vitamin_c", ReferenceType.PRI),),
        base_revision="base:stale",
    )
    assert sex is not None
    stale_callback = _button(sex, "Женский")

    store.save_profile_fact(
        user_id,
        "stale:intervening",
        field="sex_applicability",
        value="male",
        expected_revision=store.profile(user_id).revision,
    )
    result = controller.callback(
        174001,
        stale_callback,
        action_key="stale:old-callback",
    )

    assert "Старое действие не применено" in result.text
    assert store.profile(user_id).sex_applicability == "male"
