from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import timedelta
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

from vitaminbot.application.kir116 import Button, KIR116Controller, Screen
from vitaminbot.application.kir120 import KIR120Controller
from vitaminbot.application.kir122 import KIR122Controller
from vitaminbot.application.kir146 import KIR146Controller, NutrientCardRenderer
from vitaminbot.config import Settings
from vitaminbot.nutrition.card_content import APPROVED_CARD_CONTENT
from vitaminbot.nutrition.reference_values import EU_EFSA_REFERENCE_DATASET
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir120 import KIR120Store, RoutineTimes
from vitaminbot.persistence.kir122 import KIR122Store
from vitaminbot.telegram.presentation import localize_operational_screen
from vitaminbot.telegram.reminders import TelegramReminderRunner


def _controller(context: ContextTypes.DEFAULT_TYPE) -> KIR116Controller:
    return cast(KIR116Controller, context.application.bot_data["kir116_controller"])


def _schedule_controller(context: ContextTypes.DEFAULT_TYPE) -> KIR120Controller | None:
    value = context.application.bot_data.get("kir120_controller")
    return None if value is None else cast(KIR120Controller, value)


def _nutrient_controller(context: ContextTypes.DEFAULT_TYPE) -> KIR146Controller | None:
    value = context.application.bot_data.get("kir146_controller")
    return None if value is None else cast(KIR146Controller, value)


def _vertical_controller(context: ContextTypes.DEFAULT_TYPE) -> KIR122Controller | None:
    value = context.application.bot_data.get("kir122_controller")
    return None if value is None else cast(KIR122Controller, value)


def _operational_screen(context: ContextTypes.DEFAULT_TYPE, screen: Screen) -> Screen:
    controller = _vertical_controller(context)
    if controller is not None:
        screen = controller.decorate_operational_screen(screen)
    return localize_operational_screen(screen)


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
    await _reply(update, _operational_screen(context, screen))


async def _add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).add, telegram_user_id)
    await _reply(update, _operational_screen(context, screen))


async def _supplements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).supplements, telegram_user_id)
    await _reply(update, _operational_screen(context, screen))


async def _profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).profile, telegram_user_id)
    await _reply(update, _operational_screen(context, screen))


async def _help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    if _vertical_controller(context) is not None:
        screen = Screen(
            text=(
                "VitaminBot — помощь\n\n"
                "• /today — что запланировано на сегодня\n"
                "• /add — добавить добавку\n"
                "• /composition — подтвердить состав с этикетки\n"
                "• /totals — дневные итоги и вклад добавок\n"
                "• /safety — справочные значения и ограничения\n"
                "• /plan — повторяющийся план\n"
                "• /history — история и исправления\n"
                "• /profile — технические настройки\n"
                "• /nutrient <name> — принятая справочная карточка с источниками\n\n"
                "Неизвестное состояние не считается безопасным, а отсутствие правила "
                "не означает совместимость."
            ),
            rows=(
                (Button("Сегодня", "k120today"), Button("Итоги", "k122tot")),
                (Button("Добавить добавку", "a"), Button("Состав", "k122comp")),
            ),
        )
    else:
        screen = await asyncio.to_thread(_controller(context).help, telegram_user_id)
        if _nutrient_controller(context) is not None:
            screen = Screen(
                text=screen.text
                + (
                    "\n\nNutrient cards: /nutrient <name> — approved educational "
                    "content with provenance."
                ),
                rows=screen.rows,
            )
        screen = _operational_screen(context, screen)
    await _reply(update, screen)


async def _nutrient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _nutrient_controller(context)
    if telegram_user_id is None or controller is None:
        return
    query = " ".join(context.args or ()).strip()
    if query:
        screen = await asyncio.to_thread(controller.open, telegram_user_id, query)
    else:
        screen = controller.list_cards()
    await _reply(update, screen)


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    vertical_controller = _vertical_controller(context)
    if vertical_controller is not None:
        waiting = await asyncio.to_thread(
            vertical_controller.has_pending_text,
            telegram_user_id,
        )
        if waiting:
            screen = await asyncio.to_thread(
                vertical_controller.callback,
                telegram_user_id,
                "k122cancel",
                action_key="cmd:cancel:composition",
            )
            await _reply(update, screen)
            return

    schedule_controller = _schedule_controller(context)
    if schedule_controller is not None:
        waiting = await asyncio.to_thread(
            schedule_controller.has_pending_text,
            telegram_user_id,
        )
        if waiting:
            screen = await asyncio.to_thread(schedule_controller.cancel, telegram_user_id)
            await _reply(update, _operational_screen(context, screen))
            return
    screen = await asyncio.to_thread(_controller(context).cancel, telegram_user_id)
    await _reply(update, _operational_screen(context, screen))


async def _today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _schedule_controller(context)
    if telegram_user_id is None or controller is None:
        return
    screen = await asyncio.to_thread(controller.today, telegram_user_id)
    await _reply(update, _operational_screen(context, screen))


async def _plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _schedule_controller(context)
    if telegram_user_id is None or controller is None:
        return
    screen = await asyncio.to_thread(controller.plan, telegram_user_id)
    await _reply(update, _operational_screen(context, screen))


async def _history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _schedule_controller(context)
    if telegram_user_id is None or controller is None:
        return
    screen = await asyncio.to_thread(controller.history, telegram_user_id)
    await _reply(update, _operational_screen(context, screen))


async def _composition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _vertical_controller(context)
    if telegram_user_id is None or controller is None:
        return
    screen = await asyncio.to_thread(controller.composition, telegram_user_id)
    await _reply(update, screen)


async def _totals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _vertical_controller(context)
    if telegram_user_id is None or controller is None:
        return
    screen = await asyncio.to_thread(controller.totals, telegram_user_id)
    await _reply(update, screen)


async def _safety(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _vertical_controller(context)
    if telegram_user_id is None or controller is None:
        return
    screen = await asyncio.to_thread(controller.safety, telegram_user_id)
    await _reply(update, screen)


async def _text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    message = update.effective_message
    if telegram_user_id is None or message is None or message.text is None:
        return
    chat = update.effective_chat
    if chat is None:
        return

    action_key = f"msg:{chat.id}:{message.message_id}"
    vertical_controller = _vertical_controller(context)
    if vertical_controller is not None:
        waiting = await asyncio.to_thread(
            vertical_controller.has_pending_text,
            telegram_user_id,
        )
        if waiting:
            screen = await asyncio.to_thread(
                vertical_controller.text,
                telegram_user_id,
                message.text,
                action_key=action_key,
            )
            await _reply(update, _operational_screen(context, screen))
            return

    schedule_controller = _schedule_controller(context)
    if schedule_controller is not None:
        waiting = await asyncio.to_thread(
            schedule_controller.has_pending_text,
            telegram_user_id,
        )
        if waiting:
            screen = await asyncio.to_thread(
                schedule_controller.text,
                telegram_user_id,
                message.text,
                action_key=action_key,
            )
            await _reply(update, _operational_screen(context, screen))
            return

    screen = await asyncio.to_thread(
        _controller(context).text,
        telegram_user_id,
        message.text,
        action_key=action_key,
    )
    await _reply(update, _operational_screen(context, screen))


async def _callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    query = update.callback_query
    if telegram_user_id is None or query is None or not isinstance(query.data, str):
        return

    await query.answer()
    action_key = f"cb:{query.id}"
    vertical_controller = _vertical_controller(context)
    nutrient_controller = _nutrient_controller(context)
    schedule_controller = _schedule_controller(context)
    operational = False
    if query.data.startswith("k122") and vertical_controller is not None:
        screen = await asyncio.to_thread(
            vertical_controller.callback,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
    elif query.data.startswith("k146") and nutrient_controller is not None:
        screen = await asyncio.to_thread(
            nutrient_controller.callback,
            telegram_user_id,
            query.data,
        )
    elif query.data.startswith("k120") and schedule_controller is not None:
        operational = True
        screen = await asyncio.to_thread(
            schedule_controller.callback,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
    else:
        operational = True
        screen = await asyncio.to_thread(
            _controller(context).callback,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
    if operational:
        screen = _operational_screen(context, screen)
    await _project_callback(update, context, screen)


async def _reminder_post_init(
    application: Application[Any, Any, Any, Any, Any, Any],
) -> None:
    runner_value = application.bot_data.get("reminder_runner")
    if runner_value is None:
        return
    runner = cast(TelegramReminderRunner, runner_value)
    application.bot_data["reminder_task"] = asyncio.create_task(runner.run_forever(application.bot))


async def _reminder_post_shutdown(
    application: Application[Any, Any, Any, Any, Any, Any],
) -> None:
    task_value = application.bot_data.get("reminder_task")
    if not isinstance(task_value, asyncio.Task):
        return
    task_value.cancel()
    with suppress(asyncio.CancelledError):
        await task_value


def build_application(
    token: str,
    controller: KIR116Controller,
    schedule_controller: KIR120Controller | None = None,
    reminder_runner: TelegramReminderRunner | None = None,
    nutrient_controller: KIR146Controller | None = None,
    vertical_controller: KIR122Controller | None = None,
) -> Application[Any, Any, Any, Any, Any, Any]:
    builder = ApplicationBuilder().token(token).concurrent_updates(False)
    if reminder_runner is not None:
        builder = builder.post_init(_reminder_post_init).post_shutdown(_reminder_post_shutdown)
    application = builder.build()
    application.bot_data["kir116_controller"] = controller
    if schedule_controller is not None:
        application.bot_data["kir120_controller"] = schedule_controller
    if reminder_runner is not None:
        application.bot_data["reminder_runner"] = reminder_runner
    if nutrient_controller is not None:
        application.bot_data["kir146_controller"] = nutrient_controller
    if vertical_controller is not None:
        application.bot_data["kir122_controller"] = vertical_controller

    application.add_handler(CommandHandler("start", _start))
    application.add_handler(CommandHandler("add", _add))
    application.add_handler(CommandHandler("supplements", _supplements))
    application.add_handler(CommandHandler("profile", _profile))
    if schedule_controller is not None:
        application.add_handler(CommandHandler("today", _today))
        application.add_handler(CommandHandler("plan", _plan))
        application.add_handler(CommandHandler("history", _history))
    application.add_handler(CommandHandler("help", _help))
    if nutrient_controller is not None:
        application.add_handler(CommandHandler("nutrient", _nutrient))
    if vertical_controller is not None:
        application.add_handler(CommandHandler("composition", _composition))
        application.add_handler(CommandHandler("totals", _totals))
        application.add_handler(CommandHandler("safety", _safety))
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

    kir116_store = KIR116Store(settings.database_url)
    kir116_controller = KIR116Controller(kir116_store)

    routine_times = RoutineTimes.from_strings(
        settings.reminder_morning_time,
        settings.reminder_day_time,
        settings.reminder_evening_time,
    )
    kir120_store = KIR120Store(
        settings.database_url,
        routine_times=routine_times,
    )
    kir120_controller = KIR120Controller(
        kir120_store,
        later_delay=timedelta(minutes=settings.reminder_later_minutes),
    )
    reminder_runner = TelegramReminderRunner(
        kir120_store,
        poll_seconds=settings.reminder_poll_seconds,
    )
    nutrient_renderer = NutrientCardRenderer(
        registry=APPROVED_CARD_CONTENT,
        dataset=EU_EFSA_REFERENCE_DATASET,
    )
    nutrient_controller = KIR146Controller(nutrient_renderer)
    kir122_store = KIR122Store(settings.database_url)
    kir122_controller = KIR122Controller(
        base_store=kir116_store,
        store=kir122_store,
    )
    application = build_application(
        settings.telegram_bot_token,
        kir116_controller,
        schedule_controller=kir120_controller,
        reminder_runner=reminder_runner,
        nutrient_controller=nutrient_controller,
        vertical_controller=kir122_controller,
    )
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
