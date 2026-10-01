from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
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

from vitaminbot.application.account import AccountController
from vitaminbot.application.applicability import ApplicabilityController
from vitaminbot.application.intake import (
    HistoryActionStatus,
    IntakeController,
    PlanActionStatus,
    TodayActionStatus,
)
from vitaminbot.application.nutrition import (
    NutrientCardRenderer,
    NutrientReferenceController,
    NutritionController,
)
from vitaminbot.application.supplements import Button, Screen, SupplementController
from vitaminbot.config import Settings
from vitaminbot.nutrition.card_content import APPROVED_CARD_CONTENT
from vitaminbot.nutrition.reference_values import EU_EFSA_REFERENCE_DATASET
from vitaminbot.observability import (
    NULL_METRICS,
    MetricsSink,
    build_logging_metrics_sink,
)
from vitaminbot.persistence.account import AccountStore
from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir120 import KIR120Store, RoutineTimes
from vitaminbot.persistence.kir122 import KIR122Store
from vitaminbot.persistence.kir174 import KIR174Store
from vitaminbot.presentation.telegram import (
    render_account_deletion,
    render_adherence,
    render_composition,
    render_history,
    render_history_action_result,
    render_inventory_edit,
    render_plan,
    render_plan_action_result,
    render_quick_add,
    render_regimen_totals,
    render_safety,
    render_safety_sources,
    render_supplement_detail,
    render_today,
    render_today_action_result,
)
from vitaminbot.telegram.presentation import (
    project_v02_scientific_shell,
    project_v02_screen,
)


def _account_controller(context: ContextTypes.DEFAULT_TYPE) -> AccountController | None:
    value = context.application.bot_data.get("account_controller")
    return None if value is None else cast(AccountController, value)


def _metrics(context: ContextTypes.DEFAULT_TYPE) -> MetricsSink:
    value = context.application.bot_data.get("metrics")
    return NULL_METRICS if value is None else cast(MetricsSink, value)


def _controller(context: ContextTypes.DEFAULT_TYPE) -> SupplementController:
    return cast(SupplementController, context.application.bot_data["kir116_controller"])


def _schedule_controller(context: ContextTypes.DEFAULT_TYPE) -> IntakeController | None:
    value = context.application.bot_data.get("kir120_controller")
    return None if value is None else cast(IntakeController, value)


def _nutrient_controller(context: ContextTypes.DEFAULT_TYPE) -> NutrientReferenceController | None:
    value = context.application.bot_data.get("kir146_controller")
    return None if value is None else cast(NutrientReferenceController, value)


def _applicability_controller(
    context: ContextTypes.DEFAULT_TYPE,
) -> ApplicabilityController | None:
    value = context.application.bot_data.get("kir174_controller")
    return None if value is None else cast(ApplicabilityController, value)


def _vertical_controller(context: ContextTypes.DEFAULT_TYPE) -> NutritionController | None:
    value = context.application.bot_data.get("kir122_controller")
    return None if value is None else cast(NutritionController, value)


def _only_applicability_actions(screen: Screen) -> bool:
    callbacks = tuple(button.callback_data for row in screen.rows for button in row)
    return bool(callbacks) and all(value.startswith("k174") for value in callbacks)


def _operational_screen(
    context: ContextTypes.DEFAULT_TYPE,
    screen: Screen,
    *,
    surface: str | None = None,
) -> Screen:
    controller = _vertical_controller(context)
    if controller is not None:
        screen = controller.decorate_operational_screen(screen)
    if _only_applicability_actions(screen):
        return screen
    return project_v02_screen(screen, surface=surface)


def _scientific_screen(screen: Screen) -> Screen:
    if _only_applicability_actions(screen):
        return screen
    return project_v02_scientific_shell(screen)


def _callback_surface(data: str) -> str | None:
    if data == "ls":
        return "supplements"
    if data == "pf":
        return "profile"
    if data in {"a", "h", "m", "x"} or data.startswith(("mu:", "me:", "mc:")):
        return "add"
    if data.startswith(("o:", "p:", "pb:", "en:", "es:", "eu:", "rp:", "rc:")):
        return "supplement"
    if data == "k120today" or data.startswith(("k120t:", "k120s:", "k120l:")):
        return "today"
    if data == "k120p" or data.startswith(("k120b:", "k120e:")):
        return "plan"
    if data == "k120h" or data.startswith("k120c:"):
        return "history"
    if data.startswith("k120q:"):
        return "history_confirmation"
    if data.startswith("k120w:"):
        return "why"
    if data in {"k122comp", "k122cancel"} or data.startswith(("k122c:", "k122n:", "k122ok:")):
        return "composition"
    if data == "k122tot":
        return "totals"
    if data == "k122rules":
        return "rules"
    if data.startswith("k122why:"):
        return "sources"
    if data == "k122safe":
        return "safety"
    if data.startswith("k122src:"):
        return "sources"
    return None


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


def _resolve_start_screen(
    base: SupplementController,
    schedule: IntakeController | None,
    telegram_user_id: int,
) -> tuple[Screen, str]:
    if base.has_supplements(telegram_user_id) and schedule is not None:
        return render_today(schedule.today_view(telegram_user_id)), "today"
    return base.start(telegram_user_id), "start"


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return

    screen, surface = await asyncio.to_thread(
        _resolve_start_screen,
        _controller(context),
        _schedule_controller(context),
        telegram_user_id,
    )
    await _reply(update, _operational_screen(context, screen, surface=surface))


async def _add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    message = update.effective_message
    chat = update.effective_chat
    if telegram_user_id is None or message is None or chat is None:
        return
    view = await asyncio.to_thread(
        _controller(context).quick_add_start,
        telegram_user_id,
        action_key=f"cmd:add:{chat.id}:{message.message_id}",
    )
    await _reply(update, render_quick_add(view))


async def _supplements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).supplements, telegram_user_id)
    await _reply(update, _operational_screen(context, screen, surface="supplements"))


async def _profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    screen = await asyncio.to_thread(_controller(context).profile, telegram_user_id)
    if _applicability_controller(context) is not None:
        screen = Screen(
            text=screen.text,
            rows=screen.rows + ((Button("Контекст применимости", "k174profile"),),),
        )
    await _reply(update, _operational_screen(context, screen, surface="profile"))


async def _help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return
    await asyncio.to_thread(_controller(context).start, telegram_user_id)
    screen = Screen(
        text=(
            "VitaminBot — помощь\n\n"
            "Основные разделы:\n"
            "• /today — что запланировано на сегодня\n"
            "• /add — добавить добавку\n"
            "• /supplements — добавки и их подтверждённые данные\n"
            "• /plan — повторяющийся план\n"
            "• /history — история и исправления\n"
            "• /stats — сводка отметок за 7 и 30 дней\n"
            "• /totals — итоги нутриентов по подтверждённому составу и плану\n"
            "• /profile — технические настройки\n"
            "• /export — выгрузить данные аккаунта в JSON\n"
            "• /delete_account — удалить аккаунт и связанные данные\n"
            "• /help — эта справка\n\n"
            "Если данных или доказательств недостаточно, VitaminBot покажет это явно. "
            "Отсутствие поддерживаемого правила не означает совместимость или безопасность."
        ),
        rows=(
            (Button("Сегодня", "k120today"),),
            (Button("Добавить добавку", "a"),),
            (Button("Добавки", "ls"), Button("План", "k120p")),
            (Button("История", "k120h"),),
            (Button("Итоги", "k122tot"), Button("Статистика", "k120a")),
        ),
    )
    await _reply(update, project_v02_screen(screen, surface="help"))


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
    await _reply(update, _scientific_screen(screen))


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    if telegram_user_id is None:
        return

    base_controller = _controller(context)
    quick_waiting = await asyncio.to_thread(
        base_controller.quick_add_pending,
        telegram_user_id,
    )
    if quick_waiting:
        quick_add_view = await asyncio.to_thread(
            base_controller.quick_add_callback,
            telegram_user_id,
            "qac",
            action_key="cmd:cancel:quick-add",
        )
        await _reply(update, render_quick_add(quick_add_view))
        return

    inventory_waiting = await asyncio.to_thread(
        base_controller.inventory_edit_pending,
        telegram_user_id,
    )
    if inventory_waiting:
        inventory_view = await asyncio.to_thread(
            base_controller.inventory_edit_cancel,
            telegram_user_id,
        )
        await _reply(update, render_inventory_edit(inventory_view))
        return

    applicability_controller = _applicability_controller(context)
    if applicability_controller is not None:
        waiting = await asyncio.to_thread(
            applicability_controller.has_pending_text,
            telegram_user_id,
        )
        if waiting:
            screen = await asyncio.to_thread(
                applicability_controller.callback,
                telegram_user_id,
                "k174skip",
                action_key="cmd:cancel:applicability",
            )
            await _reply(update, screen)
            return

    vertical_controller = _vertical_controller(context)
    if vertical_controller is not None:
        waiting = await asyncio.to_thread(
            vertical_controller.has_pending_text,
            telegram_user_id,
        )
        if waiting:
            composition_view = await asyncio.to_thread(
                vertical_controller.apply_composition_action_view,
                telegram_user_id,
                "k122cancel",
                action_key="cmd:cancel:composition",
            )
            await _reply(update, render_composition(composition_view))
            return

    schedule_controller = _schedule_controller(context)
    if schedule_controller is not None:
        waiting = await asyncio.to_thread(
            schedule_controller.has_pending_text,
            telegram_user_id,
        )
        if waiting:
            result = await asyncio.to_thread(
                schedule_controller.cancel_plan_edit_view,
                telegram_user_id,
            )
            await _reply(update, render_plan_action_result(result))
            return
    screen = await asyncio.to_thread(_controller(context).cancel, telegram_user_id)
    await _reply(update, _operational_screen(context, screen))


async def _today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _schedule_controller(context)
    if telegram_user_id is None or controller is None:
        return
    view = await asyncio.to_thread(controller.today_view, telegram_user_id)
    await _reply(update, render_today(view))


async def _plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _schedule_controller(context)
    if telegram_user_id is None or controller is None:
        return
    view = await asyncio.to_thread(controller.plan_view, telegram_user_id)
    await _reply(update, render_plan(view))


async def _history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _schedule_controller(context)
    if telegram_user_id is None or controller is None:
        return
    view = await asyncio.to_thread(controller.history_view, telegram_user_id)
    await _reply(update, render_history(view))


async def _stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _schedule_controller(context)
    if telegram_user_id is None or controller is None:
        return
    view = await asyncio.to_thread(controller.adherence_view, telegram_user_id)
    await _reply(update, render_adherence(view))


async def _export_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    message = update.effective_message
    controller = _account_controller(context)
    if telegram_user_id is None or message is None or controller is None:
        return

    export = await asyncio.to_thread(controller.export_data, telegram_user_id)
    if export is None:
        await _reply(update, Screen(text="Аккаунт не найден. Экспортировать нечего.", rows=()))
        return

    await message.reply_document(
        document=InputFile(export.payload, filename=export.filename),
        caption=(
            "Экспорт данных VitaminBot. Файл содержит данные вашего аккаунта на момент выгрузки."
        ),
    )


async def _delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _account_controller(context)
    if telegram_user_id is None or controller is None:
        return
    view = await asyncio.to_thread(controller.begin_deletion, telegram_user_id)
    await _reply(update, render_account_deletion(view))


async def _composition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _vertical_controller(context)
    if telegram_user_id is None or controller is None:
        return
    view = await asyncio.to_thread(controller.composition_view, telegram_user_id)
    await _reply(update, render_composition(view))


async def _totals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _vertical_controller(context)
    if telegram_user_id is None or controller is None:
        return
    view = await asyncio.to_thread(controller.totals_view, telegram_user_id)
    await _reply(update, render_regimen_totals(view))


async def _safety(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    controller = _vertical_controller(context)
    if telegram_user_id is None or controller is None:
        return
    prompt = await asyncio.to_thread(controller.safety_prompt, telegram_user_id)
    if prompt is not None:
        await _reply(update, prompt)
        return
    view = await asyncio.to_thread(controller.safety_view, telegram_user_id)
    await _reply(update, render_safety(view))


async def _text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _telegram_user_id(update)
    message = update.effective_message
    if telegram_user_id is None or message is None or message.text is None:
        return
    chat = update.effective_chat
    if chat is None:
        return

    action_key = f"msg:{chat.id}:{message.message_id}"
    base_controller = _controller(context)
    quick_waiting = await asyncio.to_thread(
        base_controller.quick_add_pending,
        telegram_user_id,
    )
    if quick_waiting:
        quick_add_view = await asyncio.to_thread(
            base_controller.quick_add_text,
            telegram_user_id,
            message.text,
            action_key=action_key,
        )
        await _reply(update, render_quick_add(quick_add_view))
        return

    inventory_waiting = await asyncio.to_thread(
        base_controller.inventory_edit_pending,
        telegram_user_id,
    )
    if inventory_waiting:
        inventory_view = await asyncio.to_thread(
            base_controller.inventory_edit_text,
            telegram_user_id,
            message.text,
            action_key=action_key,
        )
        await _reply(update, render_inventory_edit(inventory_view))
        return

    applicability_controller = _applicability_controller(context)
    if applicability_controller is not None:
        waiting = await asyncio.to_thread(
            applicability_controller.has_pending_text,
            telegram_user_id,
        )
        if waiting:
            screen = await asyncio.to_thread(
                applicability_controller.text,
                telegram_user_id,
                message.text,
                action_key=action_key,
            )
            await _reply(update, screen)
            return

    vertical_controller = _vertical_controller(context)
    if vertical_controller is not None:
        waiting = await asyncio.to_thread(
            vertical_controller.has_pending_text,
            telegram_user_id,
        )
        if waiting:
            composition_view = await asyncio.to_thread(
                vertical_controller.composition_text_view,
                telegram_user_id,
                message.text,
                action_key=action_key,
            )
            await _reply(update, render_composition(composition_view))
            return

    schedule_controller = _schedule_controller(context)
    if schedule_controller is not None:
        waiting = await asyncio.to_thread(
            schedule_controller.has_pending_text,
            telegram_user_id,
        )
        if waiting:
            result = await asyncio.to_thread(
                schedule_controller.apply_plan_text_view,
                telegram_user_id,
                message.text,
                action_key=action_key,
            )
            await _reply(update, render_plan_action_result(result))
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
    applicability_controller = _applicability_controller(context)
    account_controller = _account_controller(context)
    scientific = False
    applicability_action = False
    structured_today = False
    structured_add = False
    structured_supplement = False
    structured_inventory = False
    structured_adherence = False
    structured_account = False
    structured_totals = False
    structured_plan = False
    structured_history = False
    structured_composition = False
    structured_safety = False
    if query.data == "a":
        quick_add_view = await asyncio.to_thread(
            _controller(context).quick_add_start,
            telegram_user_id,
            action_key=action_key,
        )
        screen = render_quick_add(quick_add_view)
        structured_add = True
    elif query.data == "qac" or query.data.startswith(("qau:", "qaq:", "qab:")):
        quick_add_view = await asyncio.to_thread(
            _controller(context).quick_add_callback,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
        screen = render_quick_add(quick_add_view)
        structured_add = True
    elif query.data.startswith("o:"):
        supplement_view = await asyncio.to_thread(
            _controller(context).supplement_detail_callback_view,
            telegram_user_id,
            query.data,
        )
        screen = render_supplement_detail(supplement_view)
        structured_supplement = True
    elif query.data.startswith(("ps:", "rs:")):
        supplement_view = await asyncio.to_thread(
            _controller(context).supplement_lifecycle_callback_view,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
        screen = render_supplement_detail(supplement_view)
        structured_supplement = True
    elif query.data.startswith("iv:"):
        inventory_view = await asyncio.to_thread(
            _controller(context).inventory_edit_start,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
        screen = render_inventory_edit(inventory_view)
        structured_inventory = True
    elif query.data == "ivc":
        inventory_view = await asyncio.to_thread(
            _controller(context).inventory_edit_cancel,
            telegram_user_id,
        )
        screen = render_inventory_edit(inventory_view)
        structured_inventory = True
    elif query.data.startswith(("ad:y:", "ad:n:")) and account_controller is not None:
        account_view = await asyncio.to_thread(
            account_controller.deletion_callback,
            telegram_user_id,
            query.data,
        )
        screen = render_account_deletion(account_view)
        structured_account = True
    elif query.data.startswith("k174") and applicability_controller is not None:
        applicability_action = True
        screen = await asyncio.to_thread(
            applicability_controller.callback,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
    elif query.data == "k122tot" and vertical_controller is not None:
        totals_view = await asyncio.to_thread(
            vertical_controller.totals_view,
            telegram_user_id,
        )
        screen = render_regimen_totals(totals_view)
        structured_totals = True
    elif (
        query.data in {"k122comp", "k122cancel"}
        or query.data.startswith(("k122c:", "k122n:", "k122ok:"))
    ) and vertical_controller is not None:
        composition_view = await asyncio.to_thread(
            vertical_controller.apply_composition_action_view,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
        screen = render_composition(composition_view)
        structured_composition = True
    elif query.data == "k122safe" and vertical_controller is not None:
        prompt = await asyncio.to_thread(
            vertical_controller.safety_prompt,
            telegram_user_id,
        )
        if prompt is not None:
            screen = prompt
            applicability_action = True
        else:
            safety_view = await asyncio.to_thread(
                vertical_controller.safety_view,
                telegram_user_id,
            )
            screen = render_safety(safety_view)
            structured_safety = True
    elif query.data.startswith("k122src:") and vertical_controller is not None:
        expected_revision = query.data.removeprefix("k122src:")
        sources_view = await asyncio.to_thread(
            vertical_controller.safety_sources_view,
            telegram_user_id,
            expected_revision,
        )
        screen = render_safety_sources(sources_view)
        structured_safety = True
    elif query.data.startswith("k122") and vertical_controller is not None:
        screen = await asyncio.to_thread(
            vertical_controller.callback,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
    elif query.data.startswith("k146") and nutrient_controller is not None:
        scientific = True
        screen = await asyncio.to_thread(
            nutrient_controller.callback,
            telegram_user_id,
            query.data,
        )
    elif query.data == "k120p" and schedule_controller is not None:
        plan_view = await asyncio.to_thread(
            schedule_controller.plan_view,
            telegram_user_id,
        )
        screen = render_plan(plan_view)
        structured_plan = True
    elif query.data == "k120pc" and schedule_controller is not None:
        plan_result = await asyncio.to_thread(
            schedule_controller.cancel_plan_edit_view,
            telegram_user_id,
        )
        screen = render_plan_action_result(plan_result)
        structured_plan = True
    elif query.data.startswith(("k120b:", "k120e:")) and schedule_controller is not None:
        plan_result = await asyncio.to_thread(
            schedule_controller.apply_plan_action_view,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
        if plan_result.status is PlanActionStatus.STALE:
            _metrics(context).increment("stale_callback_count")
        screen = render_plan_action_result(plan_result)
        structured_plan = True
    elif query.data == "k120today" and schedule_controller is not None:
        today_view = await asyncio.to_thread(
            schedule_controller.today_view,
            telegram_user_id,
        )
        screen = render_today(today_view)
        structured_today = True
    elif query.data == "k120a" and schedule_controller is not None:
        adherence_view = await asyncio.to_thread(
            schedule_controller.adherence_view,
            telegram_user_id,
        )
        screen = render_adherence(adherence_view)
        structured_adherence = True
    elif query.data == "k120h" and schedule_controller is not None:
        history_view = await asyncio.to_thread(
            schedule_controller.history_view,
            telegram_user_id,
        )
        screen = render_history(history_view)
        structured_history = True
    elif query.data.startswith(("k120q:", "k120c:")) and schedule_controller is not None:
        history_result = await asyncio.to_thread(
            schedule_controller.apply_history_action_view,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
        if history_result.status is HistoryActionStatus.STALE:
            _metrics(context).increment("stale_callback_count")
        screen = render_history_action_result(history_result)
        structured_history = True
    elif query.data.startswith(("k120t:", "k120s:", "k120l:")) and schedule_controller is not None:
        result = await asyncio.to_thread(
            schedule_controller.apply_today_action_view,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
        if result.status is TodayActionStatus.STALE:
            _metrics(context).increment("stale_callback_count")
        screen = render_today_action_result(result)
        structured_today = True
    elif query.data.startswith("k120") and schedule_controller is not None:
        screen = await asyncio.to_thread(
            schedule_controller.callback,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
    else:
        screen = await asyncio.to_thread(
            _controller(context).callback,
            telegram_user_id,
            query.data,
            action_key=action_key,
        )
    if not applicability_action:
        if (
            structured_today
            or structured_add
            or structured_supplement
            or structured_inventory
            or structured_adherence
            or structured_account
            or structured_totals
            or structured_plan
            or structured_history
            or structured_composition
            or structured_safety
        ):
            pass
        elif scientific:
            screen = _scientific_screen(screen)
        else:
            screen = _operational_screen(
                context,
                screen,
                surface=_callback_surface(query.data),
            )
    await _project_callback(update, context, screen)


def build_application(
    token: str,
    controller: SupplementController,
    schedule_controller: IntakeController | None = None,
    nutrient_controller: NutrientReferenceController | None = None,
    vertical_controller: NutritionController | None = None,
    applicability_controller: ApplicabilityController | None = None,
    account_controller: AccountController | None = None,
    metrics: MetricsSink = NULL_METRICS,
) -> Application[Any, Any, Any, Any, Any, Any]:
    application = ApplicationBuilder().token(token).concurrent_updates(False).build()
    application.bot_data["kir116_controller"] = controller
    application.bot_data["metrics"] = metrics
    if schedule_controller is not None:
        application.bot_data["kir120_controller"] = schedule_controller
    if nutrient_controller is not None:
        application.bot_data["kir146_controller"] = nutrient_controller
    if vertical_controller is not None:
        application.bot_data["kir122_controller"] = vertical_controller
    if applicability_controller is not None:
        application.bot_data["kir174_controller"] = applicability_controller
    if account_controller is not None:
        application.bot_data["account_controller"] = account_controller

    application.add_handler(CommandHandler("start", _start))
    application.add_handler(CommandHandler("add", _add))
    application.add_handler(CommandHandler("supplements", _supplements))
    application.add_handler(CommandHandler("profile", _profile))
    if schedule_controller is not None:
        application.add_handler(CommandHandler("today", _today))
        application.add_handler(CommandHandler("plan", _plan))
        application.add_handler(CommandHandler("history", _history))
        application.add_handler(CommandHandler("stats", _stats))
    application.add_handler(CommandHandler("help", _help))
    if account_controller is not None:
        application.add_handler(CommandHandler("export", _export_data))
        application.add_handler(CommandHandler("delete_account", _delete_account))
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
    kir116_controller = SupplementController(kir116_store)
    account_store = AccountStore(settings.database_url)
    account_controller = AccountController(account_store)

    routine_times = RoutineTimes.from_strings(
        settings.reminder_morning_time,
        settings.reminder_day_time,
        settings.reminder_evening_time,
    )
    kir120_store = KIR120Store(
        settings.database_url,
        routine_times=routine_times,
    )
    kir120_controller = IntakeController(
        kir120_store,
        later_delay=timedelta(minutes=settings.reminder_later_minutes),
    )
    applicability_store = KIR174Store(settings.database_url)
    applicability_controller = ApplicabilityController(
        base_store=kir116_store,
        store=applicability_store,
    )
    nutrient_renderer = NutrientCardRenderer(
        registry=APPROVED_CARD_CONTENT,
        dataset=EU_EFSA_REFERENCE_DATASET,
    )
    nutrient_controller = NutrientReferenceController(
        nutrient_renderer,
        context_provider=applicability_controller.card_context,
        jit_prompt_provider=applicability_controller.prompt_for_card,
    )
    kir122_store = KIR122Store(settings.database_url)
    kir122_controller = NutritionController(
        base_store=kir116_store,
        store=kir122_store,
        applicability_controller=applicability_controller,
    )
    application = build_application(
        settings.telegram_bot_token,
        kir116_controller,
        schedule_controller=kir120_controller,
        nutrient_controller=nutrient_controller,
        vertical_controller=kir122_controller,
        applicability_controller=applicability_controller,
        account_controller=account_controller,
        metrics=build_logging_metrics_sink(),
    )
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
