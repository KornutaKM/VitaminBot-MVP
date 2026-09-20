from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from vitaminbot.application.kir116 import Button, Screen


_TEXT_REPLACEMENTS: Final[tuple[tuple[str, str], ...]] = (
    (
        "Welcome to VitaminBot",
        "VitaminBot",
    ),
    (
        "Add the supplements you use, confirm what you entered, and organize your routine. "
        "I’ll keep uncertain information explicit and won’t generate medical dose "
        "recommendations during onboarding.",
        "Добавьте добавки, которые вы используете, подтвердите введённые данные и настройте "
        "режим. Неопределённость будет показана явно; при онбординге VitaminBot не создаёт "
        "медицинские рекомендации по дозировке.",
    ),
    (
        "Manual entry is available in this MVP slice.",
        "В MVP доступен ручной ввод.",
    ),
    ("VitaminBot MVP", "VitaminBot MVP"),
    ("Available now:", "Сейчас доступно:"),
    ("• /add — add a supplement manually", "• /add — добавить добавку"),
    ("• /supplements — list tracked supplements", "• /supplements — мои добавки"),
    ("• /plan — recurring schedule preferences", "• /plan — настройки повторяющегося плана"),
    ("• /today — today’s generated occurrences", "• /today — события на сегодня"),
    ("• /history — Taken / Skip / correction history", "• /history — история и исправления"),
    ("• /profile — review or correct technical profile fields", "• /profile — технический профиль"),
    ("• /cancel — cancel pending input", "• /cancel — отменить текущий ввод"),
    (
        "Photo and barcode capture are hidden until those flows are actually shipped.",
        "Фото и штрихкод не показываются, пока соответствующий путь не готов к использованию.",
    ),
    (
        "Nutrient cards: /nutrient <name> — approved educational content with provenance.",
        "Карточки веществ: /nutrient <name> — принятый образовательный материал с источниками. "
        "Сам научный текст карточек пока показывается в принятой English-версии.",
    ),
    ("Add a supplement", "Добавить добавку"),
    (
        "Choose photo or manual entry. Photo processing fails closed to manual entry until an "
        "authorized production recognition provider is configured.",
        "Выберите фото или ручной ввод. Пока авторизованный production-провайдер распознавания "
        "не настроен, фото-путь завершается безопасным переходом на ручной ввод.",
    ),
    ("No supplements yet.", "Пока нет добавок."),
    ("Add one manually to get started.", "Добавьте первую вручную."),
    ("My supplements —", "Мои добавки —"),
    (" — plan set", " — план задан"),
    (" — no plan yet", " — план не задан"),
    (
        "Pending input cancelled. No confirmed supplement or plan was changed.",
        "Ввод отменён. Подтверждённая добавка и план не изменены.",
    ),
    (
        "I’m not waiting for free-form input right now. Use /add, /supplements, or /profile.",
        "Сейчас VitaminBot не ждёт текст. Используйте /add, /supplements или /profile.",
    ),
    ("This input state is not supported.", "Этот шаг ввода не поддерживается."),
    ("How it works", "Как это работает"),
    (
        "Product/label facts and your intake plan are stored as different things.",
        "Факты о продукте/этикетке и ваш план хранятся отдельно.",
    ),
    (
        "Manual confirmation means “this matches what I entered”, not “this is safe”.",
        "Ручное подтверждение означает «это соответствует введённым данным», а не «это безопасно».",
    ),
    (
        "Technical profile fields are optional here and can be reviewed or corrected.",
        "Технические поля профиля можно проверить и исправить.",
    ),
    (
        "Safety/applicability questions are requested only when a governed feature needs them.",
        "Данные для safety/applicability запрашиваются только когда они нужны управляемой функции.",
    ),
    ("Enter manually", "Ввести вручную"),
    (
        "Send the supplement name exactly as you want this tracked record to appear.",
        "Отправьте название добавки так, как оно должно отображаться.",
    ),
    ("Product unit —", "Единица продукта —"),
    (
        "Choose the unit printed or used for this product. This identifies a product unit; "
        "it does not convert nutrient quantities.",
        "Выберите единицу продукта с упаковки. Это идентифицирует единицу продукта и не "
        "пересчитывает количество вещества.",
    ),
    ("Serving —", "Порция —"),
    ("How many ", "Сколько "),
    (" units make one label serving?", " единиц составляют одну порцию на этикетке?"),
    (
        "Enter a positive number. I won’t convert it into a nutrient dose.",
        "Введите положительное число. Оно не будет превращено в медицинскую дозировку.",
    ),
    ("Edit manual entry", "Исправить ручной ввод"),
    ("Current name:", "Текущее название:"),
    ("not set", "не задано"),
    ("Send the supplement name you want recorded.", "Отправьте нужное название добавки."),
    (
        "Manual entry confirmed. This records what you entered; it does not mean the "
        "supplement is safe or appropriate for you.",
        "Ручной ввод подтверждён. Записано только то, что вы ввели; это не означает, что "
        "добавка безопасна или подходит вам.",
    ),
    ("Add to plan", "Добавить в план"),
    (
        "How many product units do you plan to take in this routine event?",
        "Сколько единиц продукта вы планируете для этого события режима?",
    ),
    (
        "Enter a positive number. This is your plan, not a medical dose recommendation.",
        "Введите положительное число. Это ваш план, а не медицинская рекомендация по дозе.",
    ),
    ("Choose a routine bucket", "Выберите часть дня"),
    ("Planned quantity:", "Запланировано:"),
    ("product units.", "единиц продукта."),
    (
        "Morning / Day / Evening are routine labels only. "
        "No biological timing claim is being made.",
        "Утро / День / Вечер — только метки режима. "
        "Биологическое преимущество времени не заявляется.",
    ),
    ("Edit timezone", "Изменить часовой пояс"),
    (
        "Send an IANA timezone such as Europe/Helsinki. This technical field is used for local "
        "scheduling when reminder features need it.",
        "Отправьте IANA-часовой пояс, например Europe/Helsinki. Это техническое поле для "
        "локального расписания и напоминаний.",
    ),
    ("Edit locale", "Изменить язык/локаль"),
    (
        "Send a locale such as en, fi, or en-GB. This controls presentation only; it is not a "
        "medical applicability field.",
        "Отправьте локаль, например ru, en или en-GB. Это влияет только на отображение и не "
        "является медицинским полем applicability.",
    ),
    ("Edit name —", "Изменить название —"),
    ("Send the new tracked supplement name.", "Отправьте новое название добавки."),
    ("New serving unit:", "Новая единица порции:"),
    ("Enter a positive number.", "Введите положительное число."),
    (
        "Supplement removed. The tracked record, its saved plan, and linked intake history were "
        "removed. Manual support rows created only for this tracked record were also deleted.",
        "Добавка удалена вместе с её планом и связанной историей. Технические строки, созданные "
        "только для этой записи, также удалены.",
    ),
    (
        "Pending input cancelled. Confirmed records were not changed.",
        "Ввод отменён. Подтверждённые записи не изменены.",
    ),
    (
        "That action payload is invalid. Please reopen the current view.",
        "Эта кнопка больше невалидна. Откройте актуальный экран.",
    ),
    ("That action is not available in this MVP slice.", "Это действие недоступно в текущем MVP."),
    ("The manual draft is no longer available.", "Черновик ручного ввода больше недоступен."),
    ("Review manual entry —", "Проверьте ручной ввод —"),
    ("Product name:", "Название продукта:"),
    ("Label serving:", "Порция на этикетке:"),
    ("Source: You entered these facts manually.", "Источник: эти факты введены вами вручную."),
    (
        "Confirming means this matches what you entered. It does not mean the supplement is safe "
        "or appropriate for you.",
        "Подтверждение означает только соответствие введённым данным. Оно не означает, что "
        "добавка безопасна или подходит вам.",
    ),
    ("Profile", "Профиль"),
    ("Timezone:", "Часовой пояс:"),
    ("Locale:", "Локаль:"),
    (
        "Only technical profile fields are collected here. Medical/applicability fields are not "
        "collected speculatively.",
        "Здесь собираются только технические поля. Медицинские/applicability-данные не "
        "запрашиваются заранее без необходимости.",
    ),
    ("Status: Confirmed manual entry", "Статус: ручной ввод подтверждён"),
    ("Your plan:", "Ваш план:"),
    (
        "Product facts and your plan are stored separately.",
        "Факты о продукте и ваш план хранятся отдельно.",
    ),
    ("Saved plan note:", "Примечание к сохранённому плану:"),
    (
        "Review the plan if you want to change it.",
        "Измените план, если хотите обновить эту настройку.",
    ),
    ("Remove ", "Удалить "),
    (
        "This removes the tracked supplement, its saved plan, and linked intake history.",
        "Будут удалены добавка, её сохранённый план и связанная история.",
    ),
    (
        "Manual support rows created only for this tracked record are removed as part of the same "
        "database transaction.",
        "Технические строки, принадлежащие только этой записи, удаляются в той же транзакции.",
    ),
    (
        "This action does not silently merge or modify any other tracked supplement.",
        "Другие добавки не объединяются и не изменяются.",
    ),
    ("Edit serving —", "Изменить порцию —"),
    ("Current serving:", "Текущая порция:"),
    ("Choose the new product-unit label.", "Выберите новую единицу продукта."),
    (
        "This action is out of date, so I didn’t apply it.",
        "Действие устарело, поэтому оно не применено.",
    ),
    (
        "Open the current supplement state and try again.",
        "Откройте актуальную карточку и повторите.",
    ),
    ("Start again from Add supplement.", "Начните заново через «Добавить добавку»."),
    ("Please send a non-empty supplement name.", "Отправьте непустое название добавки."),
    (
        "The supplement name is too long for this MVP entry field.",
        "Название слишком длинное для поля MVP.",
    ),
    (
        "The supplement name contains unsupported control characters.",
        "Название содержит неподдерживаемые управляющие символы.",
    ),
    # KIR-120.
    (
        "Pending Plan input cancelled. The recurring plan and Today occurrences were unchanged.",
        "Ввод для Плана отменён. Повторяющийся план и события Сегодня не изменены.",
    ),
    (
        "Today needs your timezone before reminders can be placed on a local day.",
        "Для экрана Сегодня нужен часовой пояс.",
    ),
    (
        "Set a timezone in Profile. This is a technical scheduling field, not a medical "
        "applicability field.",
        "Укажите часовой пояс в Профиле. Это техническое поле расписания, "
        "не медицинское applicability-поле.",
    ),
    (
        "Today could not resolve one of your local schedule times across a DST transition. "
        "Nothing was moved automatically.",
        "Не удалось однозначно разрешить локальное время при переходе DST. "
        "Ничего не перенесено автоматически.",
    ),
    (
        "Review the Plan and choose an unambiguous local time.",
        "Проверьте План и выберите однозначное локальное время.",
    ),
    (
        "Today could not resolve the stored schedule safely. No reminder occurrence was guessed.",
        "Не удалось безопасно разрешить сохранённое расписание. Время напоминания не угадывалось.",
    ),
    ("Plan", "План"),
    ("No confirmed supplement plan exists yet.", "Подтверждённого плана добавок пока нет."),
    ("Add or edit a supplement plan first.", "Сначала добавьте или измените план добавки."),
    ("These are your recurring routine preferences.", "Это ваши повторяющиеся настройки режима."),
    (
        "Morning / Day / Evening are routine buckets, not biological timing claims.",
        "Утро / День / Вечер — части вашего режима, а не биологические рекомендации времени.",
    ),
    (
        "Evidence-backed planning notes are shown only when a governed rule is attached.",
        "Доказательные заметки показываются только когда применимо управляемое правило.",
    ),
    ("History", "История"),
    (
        "No Taken / Skip / Later actions have been recorded yet.",
        "Действий Принято / Пропустить / Позже пока нет.",
    ),
    (
        "History is an audit/correction view. Reminder delivery is not intake proof.",
        "История предназначена для аудита и исправлений. Доставка напоминания не доказывает приём.",
    ),
    ("No Plan field is waiting for text input.", "План сейчас не ждёт текстового ввода."),
    (
        "This Plan edit is out of date. Open the current Plan and try again.",
        "Редактирование Плана устарело. Откройте актуальный План и повторите.",
    ),
    (
        "Exact local time saved. The planned product-unit amount was not changed.",
        "Точное локальное время сохранено. Количество единиц продукта не изменено.",
    ),
    ("Routine preference updated.", "Настройка режима обновлена."),
    ("Exact local time", "Точное локальное время"),
    (
        "Send a local time as HH:MM, for example 08:30.",
        "Отправьте локальное время в формате HH:MM, например 08:30.",
    ),
    (
        "If that clock time is ambiguous or nonexistent on a DST transition day, VitaminBot "
        "will fail closed rather than silently shift it.",
        "Если время неоднозначно или отсутствует в день перехода DST, VitaminBot остановится "
        "без молчаливого сдвига.",
    ),
    (
        "This action is out of date or no longer valid. No duplicate intake action was recorded.",
        "Действие устарело или больше невалидно. Повторный факт приёма не записан.",
    ),
    ("Unsupported Today/Plan action.", "Это действие Сегодня/Плана не поддерживается."),
    ("Today", "Сегодня"),
    (
        "No scheduled occurrences for this local day.",
        "На этот локальный день нет запланированных событий.",
    ),
    ("Plan is the recurring-template view.", "План — экран повторяющегося шаблона."),
    (
        "Today shows generated occurrences. Plan edits affect the recurring template; existing "
        "Today occurrences keep their original quantity/unit snapshot.",
        "Сегодня показывает сгенерированные события. Изменение Плана меняет повторяющийся шаблон; "
        "уже созданные события Сегодня сохраняют исходный snapshot количества/единицы.",
    ),
    ("Why this time? —", "Почему это время? —"),
    (
        "Timing source: Your preference. No evidence-backed planning note is attached to this "
        "occurrence. VitaminBot is not inferring a biological Morning/Day/Evening advantage.",
        "Источник времени: ваша настройка. Доказательная заметка к этому событию не прикреплена; "
        "VitaminBot не выводит биологическое преимущество Утра/Дня/Вечера.",
    ),
    ("not scheduled", "не запланировано"),
    ("entered in error", "ошибочная запись"),
)

_BUTTON_EXACT: Final[dict[str, str]] = {
    "Add first supplement": "Добавить первую добавку",
    "How it works": "Как это работает",
    "Add supplement": "Добавить добавку",
    "📷 Photo label": "📷 Фото этикетки",
    "Enter manually": "Ввести вручную",
    "My supplements": "Мои добавки",
    "Capsule": "Капсула",
    "Tablet": "Таблетка",
    "Softgel": "Мягкая капсула",
    "Scoop": "Мерная ложка",
    "Drop": "Капля",
    "Cancel": "Отмена",
    "Confirm entry": "Подтвердить",
    "Edit": "Исправить",
    "Morning": "Утро",
    "Day": "День",
    "Evening": "Вечер",
    "Add / edit plan": "План",
    "Composition / totals": "Состав и суммы",
    "Edit name": "Изменить название",
    "Edit serving": "Изменить порцию",
    "Remove supplement…": "Удалить добавку…",
    "Back to supplements": "К добавкам",
    "Remove supplement": "Удалить добавку",
    "Edit timezone": "Изменить часовой пояс",
    "Edit locale": "Изменить язык/локаль",
    "Open profile": "Открыть профиль",
    "Open Plan": "Открыть План",
    "Today": "Сегодня",
    "Plan": "План",
    "History": "История",
    "Taken": "Принято",
    "Later": "Позже",
    "Skip": "Пропустить",
    "Why?": "Почему?",
    "Back to Today": "К Сегодня",
}

_PREFIXES: Final[tuple[tuple[str, str], ...]] = (
    ("Open ", "Открыть "),
    ("Exact time for ", "Точное время: "),
    ("Correct ", "Исправить "),
)


@dataclass(frozen=True, slots=True)
class RussianFirstPresenter:
    """Presentation-only Russian projection for non-governed Telegram shell copy.

    It does not translate KIR-146 governed scientific claims. The underlying callback
    identities and state-machine semantics remain unchanged.
    """

    def project(self, surface: str, screen: Screen) -> Screen:
        if surface not in {"kir116", "kir120"}:
            return screen
        text = screen.text
        for source, target in _TEXT_REPLACEMENTS:
            text = text.replace(source, target)
        text = _translate_dynamic_text(text)
        rows = tuple(
            tuple(Button(_translate_button(button.label), button.callback_data) for button in row)
            for row in screen.rows
        )
        return Screen(text=text, rows=rows)


def _translate_button(label: str) -> str:
    exact = _BUTTON_EXACT.get(label)
    if exact is not None:
        return exact
    for prefix, target in _PREFIXES:
        if label.startswith(prefix):
            return target + label[len(prefix) :]
    return label


def _translate_dynamic_text(text: str) -> str:
    replacements = (
        ("Morning", "Утро"),
        ("Day", "День"),
        ("Evening", "Вечер"),
        ("pending", "ожидает"),
        ("taken", "принято"),
        ("skipped", "пропущено"),
        ("capsule", "капсула"),
        ("tablet", "таблетка"),
        ("softgel", "мягкая капсула"),
        ("scoop", "мерная ложка"),
        ("drop", "капля"),
    )
    for source, target in replacements:
        text = re.sub(rf"\b{re.escape(source)}\b", target, text, flags=re.IGNORECASE)
    return text
