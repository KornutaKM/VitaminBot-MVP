from decimal import Decimal

from vitaminbot.application.nutrition import (
    CompositionNutrientOption,
    CompositionStep,
    CompositionSupplementView,
    CompositionView,
)
from vitaminbot.presentation.telegram import render_composition


def _callbacks(view: CompositionView) -> list[str]:
    screen = render_composition(view)
    return [button.callback_data for row in screen.rows for button in row]


def test_composition_list_surfaces_missing_label_serving_before_nutrients() -> None:
    view = CompositionView(
        step=CompositionStep.LIST,
        supplements=(
            CompositionSupplementView(
                instance_id="instance:manual:0123456789abcdef",
                token="abc123def456",
                revision=2,
                name="Magnesium Citrate",
                unit_label="capsule",
                serving_basis_type="per_consumption_unit",
                confirmed_count=0,
            ),
        ),
    )

    screen = render_composition(view)

    assert screen.text.startswith("Состав")
    assert "Magnesium Citrate — состав не указан · нужна порция этикетки" in screen.text
    assert _callbacks(view) == ["k122c:abc123def456:2", "k122tot"]


def test_composition_serving_amount_review_and_complete_are_explicit() -> None:
    serving = CompositionView(
        step=CompositionStep.SERVING_QUANTITY,
        instance_id="instance:manual:0123456789abcdef",
        supplement_token="abc123def456",
        supplement_revision=2,
        name="Magnesium Citrate",
        unit_label="capsule",
    )
    serving_screen = render_composition(serving)
    assert "Сколько капсул указано в одной порции на этикетке?" in serving_screen.text
    assert "он не меняет количество в вашем плане" in serving_screen.text
    assert _callbacks(serving) == ["k122cancel"]

    nutrient = CompositionView(
        step=CompositionStep.NUTRIENT,
        instance_id="instance:manual:0123456789abcdef",
        supplement_token="abc123def456",
        supplement_revision=3,
        name="Magnesium Citrate",
        unit_label="capsule",
        nutrients=(
            CompositionNutrientOption(substance_key="magnesium", name="Магний"),
            CompositionNutrientOption(substance_key="zinc", name="Цинк"),
        ),
    )
    assert _callbacks(nutrient) == [
        "k122n:abc123def456:3:magnesium",
        "k122n:abc123def456:3:zinc",
        "k122cancel",
    ]

    amount = render_composition(
        CompositionView(
            step=CompositionStep.AMOUNT,
            nutrient_name="Магний",
        )
    )
    assert "100 mg, 250 мкг, 1 g" not in amount.text
    assert "не является рекомендацией по дозе" in amount.text

    review_view = CompositionView(
        step=CompositionStep.REVIEW,
        nutrient_name="Магний",
        value=Decimal("100"),
        unit="mg",
        session_revision=7,
    )
    review = render_composition(review_view)
    assert "Магний: 100 мг на одну порцию этикетки." in review.text
    assert _callbacks(review_view) == ["k122ok:7", "k122cancel"]

    complete_view = CompositionView(
        step=CompositionStep.COMPLETE,
        instance_id="instance:manual:0123456789abcdef",
        supplement_revision=3,
        nutrient_name="Магний",
        value=Decimal("100"),
        unit="mg",
    )
    complete = render_composition(complete_view)
    assert complete.text.startswith("Состав подтверждён")
    assert "не вывод о безопасности" in complete.text
    assert "o:0123456789abcdef:3" in _callbacks(complete_view)
    assert "k122tot" in _callbacks(complete_view)


def test_composition_fail_closed_states_do_not_claim_unknown_is_zero() -> None:
    empty = render_composition(CompositionView(step=CompositionStep.EMPTY))
    assert "Состав не будет придуман автоматически." in empty.text

    duplicate = render_composition(CompositionView(step=CompositionStep.DUPLICATE))
    assert "не была заменена молча" in duplicate.text

    stale = render_composition(CompositionView(step=CompositionStep.STALE))
    assert "Старое действие не было применено." in stale.text

    cancelled = render_composition(CompositionView(step=CompositionStep.CANCELLED))
    assert "Подтверждённые данные не изменены." in cancelled.text

    invalid = render_composition(CompositionView(step=CompositionStep.INVALID))
    assert "Подтверждённые данные не изменены." in invalid.text
