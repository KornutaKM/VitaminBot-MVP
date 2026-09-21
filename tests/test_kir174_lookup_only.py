from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from vitaminbot.application.kir174 import KIR174Controller
from vitaminbot.persistence.kir174 import IronSupervisionRecord


class _BaseStore:
    @staticmethod
    def ensure_user(telegram_user_id: int) -> UUID:
        return UUID(int=telegram_user_id)


class _ApplicabilityStore:
    @staticmethod
    def iron_supervision(user_id: UUID, scope_key: str) -> IronSupervisionRecord:
        del user_id
        return IronSupervisionRecord(
            scope_key=scope_key,
            under_medical_supervision=None,
            revision=0,
        )


def test_unknown_iron_scope_is_view_only_until_lookup_requests_fact() -> None:
    controller = KIR174Controller(
        base_store=cast(Any, _BaseStore()),
        store=cast(Any, _ApplicabilityStore()),
    )

    screen = controller.iron_scope_screen(174001, "current-exposure")
    labels = tuple(button.label for row in screen.rows for button in row)

    assert "не подтверждён" in screen.text
    assert labels == ("Назад",)
