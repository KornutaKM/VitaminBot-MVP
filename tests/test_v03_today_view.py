from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from vitaminbot.application.intake import (
    TodayOccurrenceState,
    TodayStatus,
    build_today_view,
)
from vitaminbot.persistence.kir120 import OccurrenceRecord


def _occurrence(
    *,
    occurrence_id: str,
    state: str = "pending",
    later_count: int = 0,
    local_date: date = date(2026, 10, 1),
) -> OccurrenceRecord:
    scheduled = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)
    return OccurrenceRecord(
        occurrence_id=occurrence_id,
        instance_id="supplement:magnesium",
        name="Magnesium Citrate",
        unit_id="capsule",
        unit_label="capsule",
        quantity=Decimal("2"),
        schedule_kind="explicit_time",
        schedule_label="explicit_time",
        timezone="Europe/Amsterdam",
        local_date=local_date,
        scheduled_local_time=time(20, 0),
        scheduled_at=scheduled,
        due_at=scheduled,
        state=state,
        later_count=later_count,
        revision=3,
    )


def test_today_view_exposes_actions_from_occurrence_state() -> None:
    view = build_today_view((_occurrence(occurrence_id="occ:1"),))

    assert view.status is TodayStatus.READY
    assert view.local_date == date(2026, 10, 1)
    assert len(view.occurrences) == 1

    occurrence = view.occurrences[0]
    assert occurrence.state is TodayOccurrenceState.PENDING
    assert occurrence.can_take is True
    assert occurrence.can_later is True
    assert occurrence.can_skip is True
    assert occurrence.can_explain is True


@pytest.mark.parametrize(
    ("state", "later_count", "can_take", "can_later", "can_skip"),
    [
        ("pending", 1, True, False, True),
        ("needs_review", 0, True, False, True),
        ("taken", 0, False, False, False),
        ("skipped", 0, False, False, False),
    ],
)
def test_today_view_preserves_action_permissions(
    state: str,
    later_count: int,
    can_take: bool,
    can_later: bool,
    can_skip: bool,
) -> None:
    view = build_today_view(
        (
            _occurrence(
                occurrence_id=f"occ:{state}",
                state=state,
                later_count=later_count,
            ),
        )
    )
    occurrence = view.occurrences[0]

    assert occurrence.can_take is can_take
    assert occurrence.can_later is can_later
    assert occurrence.can_skip is can_skip


def test_today_view_rejects_mixed_local_dates() -> None:
    with pytest.raises(ValueError, match="one local date"):
        build_today_view(
            (
                _occurrence(occurrence_id="occ:1"),
                _occurrence(
                    occurrence_id="occ:2",
                    local_date=date(2026, 10, 2),
                ),
            )
        )
