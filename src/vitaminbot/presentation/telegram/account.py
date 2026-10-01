from __future__ import annotations

from vitaminbot.application.supplements import Button, Screen
from vitaminbot.application.views.account import (
    AccountDeletionStatus,
    AccountDeletionView,
)


def render_account_deletion(view: AccountDeletionView) -> Screen:
    if view.status is AccountDeletionStatus.NOT_FOUND:
        return Screen(
            text="Аккаунт не найден. Удалять нечего.",
            rows=(),
        )
    if view.status is AccountDeletionStatus.DELETED:
        return Screen(
            text=(
                "Аккаунт и связанные с ним данные удалены.\n\n"
                "Если вы снова начнёте пользоваться ботом, будет создан новый аккаунт."
            ),
            rows=(),
        )
    if view.status is AccountDeletionStatus.CANCELLED:
        return Screen(
            text="Удаление аккаунта отменено. Данные не изменены.",
            rows=(),
        )
    if view.status is AccountDeletionStatus.STALE:
        return Screen(
            text=(
                "Запрос на удаление устарел или уже был использован. "
                "Ничего не удалено. Запустите /delete_account заново, если это всё ещё нужно."
            ),
            rows=(),
        )

    if view.token is None or view.expires_at is None:
        return Screen(
            text="Запрос на удаление нельзя безопасно подтвердить. Ничего не удалено.",
            rows=(),
        )

    return Screen(
        text=(
            "Удалить аккаунт?\n\n"
            "Будут безвозвратно удалены профиль, добавки, планы, история отметок, "
            "напоминания, запасы, введённый состав и сохранённые данные подтверждения.\n\n"
            "Если нужен архив, сначала используйте /export. "
            "Подтверждение действует ограниченное время."
        ),
        rows=(
            (Button("Удалить аккаунт", f"ad:y:{view.token}"),),
            (Button("Отмена", f"ad:n:{view.token}"),),
        ),
    )
