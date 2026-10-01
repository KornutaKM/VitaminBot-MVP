from __future__ import annotations

import json
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from vitaminbot.application.views.account import (
    AccountDeletionStatus,
    AccountDeletionView,
    AccountExport,
)
from vitaminbot.persistence.account import AccountStore


class AccountController:
    def __init__(
        self,
        store: AccountStore,
        *,
        deletion_ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        if deletion_ttl <= timedelta(0):
            raise ValueError("deletion_ttl must be positive")
        self._store = store
        self._deletion_ttl = deletion_ttl

    def export_data(
        self,
        telegram_user_id: int,
        *,
        now: datetime | None = None,
    ) -> AccountExport | None:
        snapshot = self._store.export_snapshot(telegram_user_id)
        if snapshot is None:
            return None

        current = _utc_now(now)
        document = {
            "schema": "vitaminbot.account-export.v1",
            "exported_at": current.isoformat(),
            "data": snapshot,
        }
        payload = json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=_json_default,
        ).encode("utf-8")
        return AccountExport(
            filename=f"vitaminbot-export-{current.date().isoformat()}.json",
            payload=payload,
        )

    def begin_deletion(
        self,
        telegram_user_id: int,
        *,
        now: datetime | None = None,
    ) -> AccountDeletionView:
        current = _utc_now(now)
        token = secrets.token_hex(12)
        expires_at = current + self._deletion_ttl
        created = self._store.begin_deletion(
            telegram_user_id,
            token=token,
            expires_at=expires_at,
        )
        if not created:
            return AccountDeletionView(status=AccountDeletionStatus.NOT_FOUND)
        return AccountDeletionView(
            status=AccountDeletionStatus.CONFIRM,
            token=token,
            expires_at=expires_at,
        )

    def deletion_callback(
        self,
        telegram_user_id: int,
        data: str,
        *,
        now: datetime | None = None,
    ) -> AccountDeletionView:
        parts = data.split(":")
        if len(parts) != 3 or parts[0] != "ad" or parts[1] not in {"y", "n"}:
            return AccountDeletionView(status=AccountDeletionStatus.STALE)

        token = parts[2]
        if len(token) != 24 or any(char not in "0123456789abcdef" for char in token):
            return AccountDeletionView(status=AccountDeletionStatus.STALE)

        if parts[1] == "n":
            cancelled = self._store.cancel_deletion(telegram_user_id, token=token)
            return AccountDeletionView(
                status=(
                    AccountDeletionStatus.CANCELLED
                    if cancelled
                    else AccountDeletionStatus.STALE
                )
            )

        outcome = self._store.delete_account(
            telegram_user_id,
            token=token,
            now=_utc_now(now),
        )
        if outcome == "deleted":
            status = AccountDeletionStatus.DELETED
        elif outcome == "not_found":
            status = AccountDeletionStatus.NOT_FOUND
        else:
            status = AccountDeletionStatus.STALE
        return AccountDeletionView(status=status)


def _json_default(value: object) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"unsupported account export value: {type(value).__name__}")


def _utc_now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(UTC)
