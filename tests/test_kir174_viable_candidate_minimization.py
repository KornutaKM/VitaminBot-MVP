from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from vitaminbot.application.kir116 import Screen
from vitaminbot.application.kir174 import KIR174Controller
from vitaminbot.nutrition.reference_values import (
    EU_EFSA_REFERENCE_DATASET,
    ExposureBasis,
    ExposureContext,
    Jurisdiction,
    LookupStatus,
    ReferenceLifecycle,
    ReferenceQuery,
    ReferenceType,
    lookup_reference,
)
from vitaminbot.persistence import migrate
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir174 import KIR174Store


@pytest.fixture
def applicability_stack() -> Iterator[tuple[KIR174Store, KIR174Controller, UUID]]:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is required for KIR-174 integration tests")

    schema = f"kir174_viable_{uuid4().hex}"
    migrate(database_url, schema=schema)
    base_store = KIR116Store(database_url, schema=schema)
    store = KIR174Store(database_url, schema=schema)
    controller = KIR174Controller(base_store=base_store, store=store)
    user_id = base_store.ensure_user(174170)
    try:
        yield store, controller, user_id
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def _button(screen: Screen, label: str) -> str:
    for row in screen.rows:
        for button in row:
            if button.label == label:
                return button.callback_data
    raise AssertionError(f"button not found: {label}")


def test_adult_zinc_phytate_gap_stops_before_unneeded_profile_questions(
    applicability_stack: tuple[KIR174Store, KIR174Controller, UUID],
) -> None:
    store, controller, user_id = applicability_stack
    exposure = ExposureContext(exposure_basis=ExposureBasis.DIETARY_TOTAL)
    base_revision = "kir170:zinc-pri"

    age_prompt = controller.prompt_for_pairs(
        174170,
        pairs=(("zinc", ReferenceType.PRI),),
        derived_exposure_by_substance={"zinc": exposure},
        base_revision=base_revision,
    )
    assert age_prompt is not None
    assert "возрастные группы" in age_prompt.text

    age_input = controller.callback(
        174170,
        _button(age_prompt, "2 года и старше"),
        action_key="kir170:age:begin",
    )
    assert "полных лет" in age_input.text
    controller.text(174170, "30", action_key="kir170:age:save")

    after_age = store.profile(user_id)
    assert after_age.revision == 1
    assert after_age.completed_years == 30
    assert after_age.sex_applicability is None
    assert after_age.life_stage is None
    assert after_age.physiological_condition is None

    adult_candidates = tuple(
        record
        for record in EU_EFSA_REFERENCE_DATASET.records
        if record.lifecycle is ReferenceLifecycle.ACTIVE
        and record.jurisdiction is Jurisdiction.EU
        and record.substance_key == "zinc"
        and record.reference_type is ReferenceType.PRI
        and (record.population.age_min_months is None or record.population.age_min_months <= 360)
        and (
            record.population.age_max_months_exclusive is None
            or 360 < record.population.age_max_months_exclusive
        )
    )
    assert adult_candidates
    assert all(record.dietary_phytate_mg_per_day is not None for record in adult_candidates)

    prompt_after_age = controller.prompt_for_pairs(
        174170,
        pairs=(("zinc", ReferenceType.PRI),),
        derived_exposure_by_substance={"zinc": exposure},
        base_revision=base_revision,
    )

    after_prescreen = store.profile(user_id)
    assert prompt_after_age is None
    assert after_prescreen == after_age
    assert after_prescreen.revision == 1
    assert after_prescreen.sex_applicability is None
    assert after_prescreen.life_stage is None
    assert after_prescreen.physiological_condition is None

    bound = controller.bound_context(174170, base_revision=base_revision)
    lookup = lookup_reference(
        EU_EFSA_REFERENCE_DATASET,
        ReferenceQuery(
            substance_key="zinc",
            reference_type=ReferenceType.PRI,
            profile=bound.profile,
            exposure=exposure,
            context_revision=bound.context_revision,
        ),
    )
    assert lookup.status is LookupStatus.INDETERMINATE
