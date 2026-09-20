from __future__ import annotations

import asyncio
from typing import Any, cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from vitaminbot.application.kir116 import KIR116Controller, Screen
from vitaminbot.config import Settings
from vitaminbot.persistence.kir116 import KIR116Store


def _controller(context: ContextTypes.DEFAULT_TYPE) -> KIR116Controller:
    return cast(KIR116Controller, context.application.bot_data["kir116_controller"])


def _keyboard(screen: Screen) -> InlineKeyboardMarkup | None:
    if not screen.rows:
        return None

    rows: list[list[InlineKeyboardButton]] = []
    for row in screen.rows:
        rendered: list[InlineKeyboardButton] = []
        for button in row:
            if len(button.callback_data.encode("utf-8")) > 64:
                raise ValueError("callback_data exceeds Telegram Bot API limit")
            rendered.append(
                InlineKeyboardButton(
                    text=button.label,
                    callback_data=button.callback_data,
                )
            )
        rows.append(rendered)
    return InlineKeyboardMarkup(rows)


async def _reply(update: Update, screen: Screen) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(screen.text, reply_markup=_keyboard(screen))


async def _project_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    screen: Screen,
) -> None:
    query = update.callback_query
    if query is None:
        return
    markup = _keyboard(screen)
    try:
        await query.edit_message_text(screen.text, reply_markup=markup)
    except BadRequest:
        chat = update.effective_chat
        if chat is not None:
            await context.bot.send_message(
                chat_id=chat.id,
                text=screen.text,
                reply_markup=markup,
            )


def _telegram_user_id(update: Update) -> int | None:
    user = update.effective_user
    return None if user is None else user.id


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).start, telegram_user_id)
    await _reply(update, screen)


async def _add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).add, telegram_user_id)
    await _reply(update, screen)


async def _supplements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).supplements, telegram_user_id)
    await _reply(update, screen)


async def _profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).profile, telegram_user_id)
    await _reply(update, screen)


async def _help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).help, telegram_user_id)
    await _reply(update, screen)


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).cancel, telegram_user_id)
    await _reply(update, screen)


async def _text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    message = update.effective_message
    if telegram_user_id is None or message is None or message.text is None:
        return
    chat = update.effective_chat
    if chat is None:
        return
    screen = await asyncio.to_thread(
        _controller(context).text,
        telegram_user_id,
        message.text,
        action_key=f"msg:{chat.id}:{message.message_id}",
    )
    await _reply(update, screen)


async def _callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    query = update.callback_query
    if telegram_user_id is None or query is None or not isinstance(query.data, str):
        return

    # Acknowledge transport delivery before database work. Domain mutation is still
    # performed only after server-side user/revision/state validation.
    await query.answer()

    screen = await asyncio.to_thread(
        _controller(context).callback,
        telegram_user_id,
        query.data,
        action_key=f"cb:{query.id}",
    )
    await _project_callback(update, context, screen)


def build_application(
    token: str,
    controller: KIR116Controller,
) -> Application[Any, Any, Any, Any, Any, Any]:
    application = ApplicationBuilder().token(token).concurrent_updates(False).build()
    application.bot_data["kir116_controller"] = controller

    application.add_handler(CommandHandler("start", _start))
    application.add_handler(CommandHandler("add", _add))
    application.add_handler(CommandHandler("supplements", _supplements))
    application.add_handler(CommandHandler("profile", _profile))
    application.add_handler(CommandHandler("help", _help))
    application.add_handler(CommandHandler("cancel", _cancel))
    application.add_handler(CallbackQueryHandler(_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _text))
    return application


def main() -> None:
    settings = Settings.from_environment()
    if settings.telegram_bot_token is None:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL is required")

    store = KIR116Store(settings.database_url)
    controller = KIR116Controller(store)
    application = build_application(settings.telegram_bot_token, controller)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
