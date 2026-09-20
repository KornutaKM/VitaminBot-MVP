from __future__ import annotations

from vitaminbot.application.kir116 import Button, Screen

_LINE_REPLACEMENTS = {
    "Welcome to VitaminBot": "VitaminBot",
    "Add a supplement": "Добавить добавку",
    "Enter manually": "Ввод вручную",
    "Product unit": "Единица продукта",
    "Review manual entry": "Проверьте запись",
    "Edit manual entry": "Редактирование записи",
    "Add to plan": "Добавить в план",
    "Choose a routine bucket": "Выберите часть дня",
    "Profile": "Профиль",
    "My supplements": "Мои добавки",
    "Today": "Сегодня",
    "Plan": "План",
    "History": "История",
    "Exact local time": "Точное местное время",
}

_PHRASE_REPLACEMENTS = (
    (
        "Add the supplements you use, confirm what you entered, and organize your routine. "
        "I’ll keep uncertain information explicit and won’t generate medical dose "
        "recommendations during onboarding.",
        "Добавьте свои добавки, подтвердите введённые данные и настройте привычный режим. "
        "Неопределённость останется видимой, а медицинские дозировки не будут придумываться.",
    ),
    (
        "Manual entry is available in this MVP slice.",
        "В этой версии доступен ручной ввод.",
    ),
    (
        "Manual entry is available in this version. "
        "Photo and barcode options are not shown until their implementation is ready.",
        "Сейчас доступен ручной ввод. Фото и штрихкод не показываются, пока соответствующий "
        "путь не готов к безопасному использованию.",
    ),
    (
        "Photo and barcode capture are hidden until those flows are actually shipped.",
        "Фото и штрихкод скрыты, пока эти пути не готовы к использованию.",
    ),
    (
        "Send the supplement name exactly as you want this tracked record to appear.",
        "Отправьте название добавки так, как хотите видеть его в списке.",
    ),
    (
        "Choose the unit printed or used for this product. "
        "This identifies a product unit; it does not convert nutrient quantities.",
        "Выберите единицу продукта с упаковки. Это только идентифицирует единицу продукта "
        "и не пересчитывает количество нутриентов.",
    ),
    (
        "How many capsule units make one label serving?",
        "Сколько капсул составляет одну порцию по этикетке?",
    ),
    (
        "How many tablet units make one label serving?",
        "Сколько таблеток составляет одну порцию по этикетке?",
    ),
    (
        "How many softgel units make one label serving?",
        "Сколько мягких капсул составляет одну порцию по этикетке?",
    ),
    (
        "How many scoop units make one label serving?",
        "Сколько мерных ложек составляет одну порцию по этикетке?",
    ),
    (
        "How many drop units make one label serving?",
        "Сколько капель составляет одну порцию по этикетке?",
    ),
    (
        "Enter a positive number. I won’t convert it into a nutrient dose.",
        "Введите положительное число. Я не превращу его в дозировку нутриента.",
    ),
    (
        "Source: You entered these facts manually.",
        "Источник: эти данные введены вами вручную.",
    ),
    (
        "Confirming means this matches what you entered. "
        "It does not mean the supplement is safe or appropriate for you.",
        "Подтверждение означает только «это совпадает с тем, что я ввёл». "
        "Оно не означает, что добавка безопасна или подходит вам.",
    ),
    (
        "Manual entry confirmed. This records what you entered; "
        "it is not a safety or dose recommendation.",
        "Ручной ввод подтверждён. Сохранено то, что вы ввели; "
        "это не вывод о безопасности и не рекомендация по дозе.",
    ),
    (
        "Status: Confirmed manual entry",
        "Статус: подтверждённый ручной ввод",
    ),
    ("Label serving:", "Порция по этикетке:"),
    ("Your plan:", "Ваш план:"),
    ("Not set", "Не настроен"),
    (
        "Product facts and your plan are stored separately.",
        "Факты о продукте и ваш план хранятся отдельно.",
    ),
    (
        "How many product units do you plan to take in this routine event?",
        "Сколько единиц продукта вы планируете принимать в этом событии режима?",
    ),
    (
        "Enter a positive number. This is your plan, not a medical dose recommendation.",
        "Введите положительное число. Это ваш план, а не медицинская рекомендация по дозе.",
    ),
    (
        "Morning / Day / Evening are routine labels only. "
        "No biological timing claim is being made.",
        "Утро / День / Вечер — только организационные метки. "
        "Они не означают биологического преимущества времени суток.",
    ),
    (
        "Morning / Day / Evening are routine buckets, not biological timing claims.",
        "Утро / День / Вечер — организационные части дня, "
        "а не утверждения о биологически лучшем времени.",
    ),
    (
        "Evidence-backed planning notes are shown only when a governed rule is attached.",
        "Доказательное пояснение появляется только при наличии принятого правила.",
    ),
    (
        "These are your recurring routine preferences.",
        "Это ваши повторяющиеся настройки режима.",
    ),
    (
        "Plan saved. Morning / Day / Evening are routine buckets, not biological timing claims.",
        "План сохранён. Утро / День / Вечер — организационные метки, "
        "а не утверждения о биологически лучшем времени.",
    ),
    (
        "Today needs your timezone before reminders can be placed on a local day.",
        "Для экрана «Сегодня» нужен часовой пояс, чтобы привязать напоминания к местному дню.",
    ),
    (
        "Set a timezone in Profile. This is a technical scheduling field, "
        "not a medical applicability field.",
        "Укажите часовой пояс в профиле. Это техническая настройка расписания, "
        "а не медицинский параметр.",
    ),
    (
        "Today could not resolve one of your local schedule times across a DST transition. "
        "Nothing was moved automatically. Review the Plan and choose an unambiguous local time.",
        "Одно из местных времён попало в неоднозначный переход летнего времени. "
        "Ничего не было перенесено автоматически. Проверьте план и выберите однозначное время.",
    ),
    (
        "Today could not resolve the stored schedule safely. No reminder occurrence was guessed.",
        "Не удалось безопасно разрешить сохранённое расписание. Время напоминания не было угадано.",
    ),
    (
        "No scheduled occurrences for this local day. Plan is the recurring-template view.",
        "На этот местный день нет запланированных событий. "
        "Повторяющиеся настройки находятся в разделе «План».",
    ),
    (
        "Today shows generated occurrences. Plan edits affect the recurring template; "
        "existing Today occurrences keep their original quantity/unit snapshot.",
        "«Сегодня» показывает уже созданные события. Изменения в «Плане» относятся к "
        "повторяющемуся шаблону; существующие события сохраняют исходный снимок количества "
        "и единицы.",
    ),
    (
        "Timing source: Your preference. "
        "No evidence-backed planning note is attached to this occurrence. "
        "VitaminBot is not inferring a biological Morning/Day/Evening advantage.",
        "Источник времени: ваша настройка. Для этого события нет прикреплённого "
        "доказательного правила. VitaminBot не предполагает биологического преимущества "
        "Утра / Дня / Вечера.",
    ),
    (
        "History is an audit/correction view. Reminder delivery is not intake proof.",
        "«История» — экран аудита и исправлений. Доставка напоминания не доказывает приём.",
    ),
    (
        "No Taken / Skip / Later actions have been recorded yet.",
        "Действия «Принято» / «Пропустить» / «Позже» пока не записаны.",
    ),
    (
        "No confirmed supplement plan exists yet. Add or edit a supplement plan first.",
        "Подтверждённого плана пока нет. Сначала добавьте или измените план добавки.",
    ),
    (
        "Pending Plan input cancelled. The recurring plan and Today occurrences were unchanged.",
        "Ввод для плана отменён. Повторяющийся план и события «Сегодня» не изменены.",
    ),
    (
        "Send a local time as HH:MM, for example 08:30. "
        "If that clock time is ambiguous or nonexistent on a DST transition day, "
        "VitaminBot will fail closed rather than silently shift it.",
        "Отправьте местное время в формате ЧЧ:ММ, например 08:30. "
        "Если время неоднозначно или не существует при переходе летнего времени, "
        "VitaminBot остановится и не сдвинет его молча.",
    ),
    (
        "This action is out of date or no longer valid. No duplicate intake action was recorded.",
        "Это действие устарело или больше недействительно. Повторная запись приёма не создана.",
    ),
    (
        "This action is out of date, so I didn’t apply it.",
        "Это действие устарело, поэтому я его не применил.",
    ),
    (
        "Open the current supplement state and try again.",
        "Откройте текущее состояние добавки и повторите действие.",
    ),
    (
        "Start again from Add supplement.",
        "Начните снова с добавления добавки.",
    ),
    (
        "Pending input cancelled. No confirmed supplement or plan was changed.",
        "Ввод отменён. Подтверждённая добавка и план не изменены.",
    ),
    ("Timezone:", "Часовой пояс:"),
    ("Locale:", "Язык интерфейса:"),
    ("Morning —", "Утро —"),
    ("Day —", "День —"),
    ("Evening —", "Вечер —"),
    ("[pending]", "[ожидает]"),
    ("[taken]", "[принято]"),
    ("[skipped]", "[пропущено]"),
    ("[needs_review]", "[нужна проверка]"),
    ("entered in error", "исправлено как ошибочная запись"),
    ("taken", "принято"),
    ("skip", "пропущено"),
    ("later", "позже"),
)


def localize_operational_screen(screen: Screen) -> Screen:
    """Translate only KIR-116/KIR-120 operational copy.

    Scientific KIR-146 card prose is intentionally not passed through this translator.
    """
    lines = screen.text.splitlines()
    translated_lines = [_LINE_REPLACEMENTS.get(line, line) for line in lines]
    text = "\n".join(translated_lines)
    for source, target in _PHRASE_REPLACEMENTS:
        text = text.replace(source, target)

    rows = tuple(
        tuple(Button(_button_label(button), button.callback_data) for button in row)
        for row in screen.rows
    )
    return Screen(text=text, rows=rows)


def _button_label(button: Button) -> str:
    label = button.label
    data = button.callback_data
    exact = {
        "Add first supplement": "Добавить первую добавку",
        "How it works": "Как это работает",
        "Add supplement": "Добавить добавку",
        "Enter manually": "Ввести вручную",
        "My supplements": "Мои добавки",
        "Confirm entry": "Подтвердить",
        "Edit": "Изменить",
        "Cancel": "Отмена",
        "Add / edit plan": "Добавить / изменить план",
        "Edit name": "Изменить название",
        "Edit serving": "Изменить порцию",
        "Remove supplement…": "Удалить добавку…",
        "Remove supplement": "Удалить добавку",
        "Back to supplements": "К списку добавок",
        "Capsule": "Капсула",
        "Tablet": "Таблетка",
        "Softgel": "Мягкая капсула",
        "Scoop": "Мерная ложка",
        "Drop": "Капля",
        "Morning": "Утро",
        "Day": "День",
        "Evening": "Вечер",
        "Edit timezone": "Изменить часовой пояс",
        "Edit locale": "Изменить язык",
        "Open profile": "Открыть профиль",
        "Open Plan": "Открыть план",
        "Taken": "Принято",
        "Later": "Позже",
        "Skip": "Пропустить",
        "Why?": "Почему?",
        "Plan": "План",
        "History": "История",
        "Today": "Сегодня",
        "Back to Today": "Назад к «Сегодня»",
    }
    if label in exact:
        return exact[label]
    if label.startswith("Open "):
        return "Открыть " + label.removeprefix("Open ")
    if label.startswith("Exact time for "):
        return "Точное время: " + label.removeprefix("Exact time for ")
    if label.startswith("Correct "):
        return "Исправить: " + label.removeprefix("Correct ")
    if data.startswith("k120"):
        return label
    return label
