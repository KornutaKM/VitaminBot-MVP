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
    "My supplements": "Мои добавки",
    "Exact local time": "Точное местное время",
    "Timezone updated.": "Часовой пояс обновлён.",
    "Locale updated.": "Язык интерфейса обновлён.",
    "Name updated.": "Название обновлено.",
    "Serving updated.": "Порция обновлена.",
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
)

_STRUCTURED_BRACKET_STATUSES = {
    "[pending]": "[ожидает]",
    "[taken]": "[принято]",
    "[skipped]": "[пропущено]",
    "[needs_review]": "[нужна проверка]",
}
_STRUCTURED_HISTORY_STATUSES = {
    "taken": "принято",
    "skip": "пропущено",
    "later": "позже",
    "entered in error": "исправлено как ошибочная запись",
}
_PROFILE_FIELD_PREFIXES = {
    "Timezone: ": "Часовой пояс: ",
    "Locale: ": "Язык интерфейса: ",
}
_ROUTINE_BUCKET_LABELS = {
    "Morning": "Утро",
    "Day": "День",
    "Evening": "Вечер",
}

_SURFACE_HEADINGS = {
    "profile": ("Profile", "Профиль"),
    "today": ("Today", "Сегодня"),
    "plan": ("Plan", "План"),
    "history": ("History", "История"),
}

_DYNAMIC_PREFIX_FIELDS = (
    ("Serving — ", "Порция — "),
    ("Current name: ", "Текущее название: "),
)

_DYNAMIC_IDENTITY_PREFIXES = (
    "Serving — ",
    "Current name: ",
    "Edit name — ",
    "Product unit — ",
    "Review manual entry — ",
    "Product name: ",
    "Edit serving — ",
)


def _source_operational_surface(screen: Screen) -> str | None:
    callbacks = [button.callback_data for row in screen.rows for button in row]
    first = screen.text.splitlines()[0] if screen.text else ""

    if any(data.startswith(("p:", "en:", "es:", "rp:", "rc:")) for data in callbacks):
        return "supplement"
    if first.startswith("My supplements —") or first.startswith("No supplements yet."):
        return "supplements"
    if any(data.startswith(("pt:", "pl:")) for data in callbacks):
        return "profile"
    if any(data.startswith(("k120b:", "k120e:")) for data in callbacks):
        return "plan"
    if any(data.startswith(("k120t:", "k120l:", "k120s:", "k120w:")) for data in callbacks):
        return "today"
    if any(data.startswith("k120c:") for data in callbacks):
        return "history"
    if first == "Profile":
        return "profile"
    if first == "Today":
        return "today"
    if first == "Plan":
        return "plan"
    if first == "History":
        return "history"
    return None


def _supplement_structured_fields(lines: list[str]) -> dict[int, str]:
    for index in range(len(lines) - 2):
        if (
            lines[index] == "Status: Confirmed manual entry"
            and lines[index + 1].startswith("Label serving: ")
            and lines[index + 2].startswith("Your plan: ")
        ):
            return {
                index: "status",
                index + 1: "label_serving",
                index + 2: "plan",
            }
    return {}


def _supplement_name_index(lines: list[str], fields: dict[int, str]) -> int | None:
    status_indices = [index for index, field in fields.items() if field == "status"]
    if not status_indices:
        return None
    for index in range(status_indices[0] - 1, -1, -1):
        if lines[index]:
            return index
    return None


def _dynamic_identity_line_indices(
    screen: Screen,
    lines: list[str],
    *,
    surface: str | None,
    supplement_fields: dict[int, str],
) -> set[int]:
    protected: set[int] = set()

    supplement_name = _supplement_name_index(lines, supplement_fields)
    if supplement_name is not None:
        protected.add(supplement_name)

    callbacks = [button.callback_data for row in screen.rows for button in row]
    if surface == "supplement" and any(data.startswith("rc:") for data in callbacks):
        first_non_empty = next((index for index, line in enumerate(lines) if line), None)
        if first_non_empty is not None:
            protected.add(first_non_empty)

    if surface in {"today", "plan", "history"}:
        protected.update(index for index, line in enumerate(lines) if line.startswith("• "))

    if surface == "supplements":
        protected.update(
            index
            for index, line in enumerate(lines)
            if line.partition(". ")[0].isdigit() and ". " in line
        )

    if surface == "composition":
        if any(data.startswith("k122c:") for data in callbacks):
            protected.update(index for index, line in enumerate(lines) if line.startswith("• "))
        if lines and lines[0].startswith("Состав — "):
            protected.add(0)
        if (
            lines
            and "k122cancel" in callbacks
            and not any(data.startswith("k122ok:") for data in callbacks)
            and " — " in lines[0]
        ):
            protected.add(0)

    if surface == "totals":
        protected.update(index for index, line in enumerate(lines) if line.startswith("  • "))

    if surface == "why" and lines and lines[0].startswith("Why this time? — "):
        protected.add(0)

    protected.update(
        index for index, line in enumerate(lines) if line.startswith(_DYNAMIC_IDENTITY_PREFIXES)
    )
    return protected


def _localize_structured_shell_line(
    line: str,
    *,
    surface: str | None,
    supplement_field: str | None,
) -> str:
    heading = _SURFACE_HEADINGS.get(surface or "")
    if heading is not None and line == heading[0]:
        return heading[1]

    if surface == "profile":
        for source, target in _PROFILE_FIELD_PREFIXES.items():
            if line.startswith(source):
                value = line[len(source) :]
                if value == "Not set":
                    value = "Не настроен"
                return target + value

    if supplement_field == "status":
        return "Статус: подтверждённый ручной ввод"
    if supplement_field == "label_serving":
        return "Порция по этикетке: " + line.removeprefix("Label serving: ")
    if supplement_field == "plan":
        value = line.removeprefix("Your plan: ")
        if value == "Not set":
            return "Ваш план: Не настроен"
        for source, target in _ROUTINE_BUCKET_LABELS.items():
            prefix = f"{source} — "
            if value.startswith(prefix):
                return f"Ваш план: {target} — " + value[len(prefix) :]
        return "Ваш план: " + value

    if surface == "today":
        for source, target in _ROUTINE_BUCKET_LABELS.items():
            prefix = f"• {source} — "
            if line.startswith(prefix):
                return f"• {target} — " + line[len(prefix) :]

    if surface == "supplements":
        if line.startswith("My supplements — "):
            return "Мои добавки — " + line.removeprefix("My supplements — ")
        number, separator, tail = line.partition(". ")
        if separator and number.isdigit():
            identity, state_separator, state = tail.rpartition(" — ")
            if state_separator and state in {"plan set", "no plan yet"}:
                rendered_state = "план настроен" if state == "plan set" else "план не настроен"
                return f"{number}. {identity} — {rendered_state}"

    for source, target in _DYNAMIC_PREFIX_FIELDS:
        if line.startswith(source):
            return target + line[len(source) :]

    return line


def _localize_structured_status_line(line: str) -> str:
    if not line.startswith("• "):
        return line
    for source, target in _STRUCTURED_BRACKET_STATUSES.items():
        if line.endswith(source):
            return line[: -len(source)] + target
    for source, target in _STRUCTURED_HISTORY_STATUSES.items():
        suffix = f" — {source}"
        if line.endswith(suffix):
            return line[: -len(suffix)] + f" — {target}"
    return line


def localize_operational_screen(
    screen: Screen,
    *,
    surface: str | None = None,
) -> Screen:
    """Translate only KIR-116/KIR-120 operational copy.

    Scientific KIR-146 card prose is intentionally not passed through this translator.
    Dynamic product identity is protected by structural controller roles before generic copy
    localization is applied.
    """
    lines = screen.text.splitlines()
    resolved_surface = surface or _source_operational_surface(screen)
    supplement_fields = _supplement_structured_fields(lines)
    protected = _dynamic_identity_line_indices(
        screen,
        lines,
        surface=resolved_surface,
        supplement_fields=supplement_fields,
    )

    translated_lines: list[str] = []
    for line_index, line in enumerate(lines):
        localized_line = _localize_structured_shell_line(
            line,
            surface=resolved_surface,
            supplement_field=supplement_fields.get(line_index),
        )
        if line_index not in protected:
            localized_line = _LINE_REPLACEMENTS.get(localized_line, localized_line)
            for source, target in _PHRASE_REPLACEMENTS:
                localized_line = localized_line.replace(source, target)
        translated_lines.append(_localize_structured_status_line(localized_line))

    rows = tuple(
        tuple(Button(_button_label(button), button.callback_data) for button in row)
        for row in screen.rows
    )
    return Screen(text="\n".join(translated_lines), rows=rows)


def _button_label(button: Button) -> str:
    label = button.label
    data = button.callback_data
    if data.startswith("o:") and label.startswith("Open "):
        return "Открыть " + label.removeprefix("Open ")

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
        "Taken": "Принял(а)",
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


_TOP_LEVEL_CALLBACKS = frozenset({"a", "ls", "k120today", "k120p", "k120h", "k122tot"})


def project_v02_screen(screen: Screen, *, surface: str | None = None) -> Screen:
    """Project existing authoritative controller state into the accepted KIR-168 shell.

    This function changes presentation/navigation only. Callback payloads that perform
    domain writes remain owned by the existing controllers and stores.
    """

    projected = localize_operational_screen(screen, surface=surface)
    resolved_surface = surface or _infer_surface(projected)

    if resolved_surface == "start":
        return Screen(
            text=(
                "VitaminBot\n\n"
                "Помогу собрать ваши добавки в одном месте, подтвердить данные с этикетки "
                "и организовать ежедневный план.\n\n"
                "Если данных недостаточно или что-то неоднозначно, я покажу это прямо — "
                "без догадок."
            ),
            rows=(
                (Button("Добавить первую добавку", "a"),),
                (Button("Как это работает", "h"),),
            ),
        )

    if resolved_surface == "today":
        return _project_today(projected)
    if resolved_surface == "add":
        return _project_add(projected)
    if resolved_surface == "composition":
        return _project_composition(projected)
    if resolved_surface == "totals":
        return _project_totals(projected)
    if resolved_surface == "safety":
        return _project_safety(projected)
    if resolved_surface == "rules":
        return _project_rules(projected)
    if resolved_surface == "sources":
        return _project_sources(projected)
    if resolved_surface == "why":
        return _project_why(projected)
    if resolved_surface == "supplements":
        return _project_supplements(projected)
    if resolved_surface == "supplement":
        return _project_supplement(projected)
    if resolved_surface == "plan":
        return _project_plan(projected)
    if resolved_surface == "history":
        return _project_history(projected)
    if resolved_surface == "history_confirmation":
        return projected
    if resolved_surface == "profile":
        profile = _project_residual(projected)
        profile = Screen(
            text=profile.text.replace(
                "Only technical profile fields are collected here. "
                "Medical/applicability fields are not collected speculatively.",
                "Здесь хранятся только технические настройки. "
                "Данные применимости не собираются заранее: если конкретной функции "
                "понадобятся эти данные, она должна запросить их отдельно.",
            ),
            rows=profile.rows,
        )
        return _with_footer(profile, ((Button("Сегодня", "k120today"),),))
    if resolved_surface == "help":
        return projected
    return _project_residual(projected)


def project_v02_scientific_shell(screen: Screen) -> Screen:
    """Translate navigation around governed scientific text without rewriting claims."""

    rows = tuple(
        tuple(
            Button(_scientific_button_label(button.label), button.callback_data) for button in row
        )
        for row in screen.rows
    )
    callbacks = {button.callback_data for row in rows for button in row}
    if callbacks and all(data.startswith("k146c:") for data in callbacks):
        rows = _merge_rows(
            rows,
            (
                (Button("Итоги", "k122tot"),),
                (Button("Сегодня", "k120today"),),
            ),
        )
    return Screen(text=screen.text, rows=rows)


def _infer_surface(screen: Screen) -> str | None:
    callbacks = [button.callback_data for row in screen.rows for button in row]
    first = screen.text.splitlines()[0] if screen.text else ""

    if first.startswith("Сегодня"):
        return "today"
    if first.startswith("План"):
        return "plan"
    if first.startswith("История"):
        return "history"
    if first.startswith("Профиль"):
        return "profile"
    if first.startswith("Мои добавки") or first.startswith("Добавок пока нет"):
        return "supplements"
    if any(data.startswith(("p:", "en:", "es:", "rp:", "rc:")) for data in callbacks):
        return "supplement"
    return None


def _project_add(screen: Screen) -> Screen:
    text = screen.text
    replacements = (
        ("How it works", "Как это работает"),
        (
            "Product/label facts and your intake plan are stored as different things.",
            "Данные с упаковки и ваш план хранятся отдельно.",
        ),
        (
            "Manual confirmation means “this matches what I entered”, not “this is safe”.",
            "Ручное подтверждение означает «это совпадает с моим вводом», а не «это безопасно».",
        ),
        (
            "Technical profile fields are optional here and can be reviewed or corrected.",
            "Технические настройки можно проверить или изменить отдельно.",
        ),
        (
            "Safety/applicability questions are requested only when a governed feature needs them.",
            "Данные применимости запрашиваются только тогда, когда они нужны конкретной "
            "принятой функции.",
        ),
        (
            "Send the supplement name you want recorded.",
            "Отправьте название, которое нужно сохранить.",
        ),
        ("New serving unit:", "Новая единица продукта:"),
        (
            "How many of these units make one label serving? Enter a positive number.",
            "Сколько таких единиц составляет одну порцию по этикетке? Введите положительное число.",
        ),
    )
    rendered_lines: list[str] = []
    for line in text.splitlines():
        rendered_line = line
        for source, target in replacements:
            if rendered_line == source:
                rendered_line = target
                break
        rendered_lines.append(rendered_line)
    text = "\n".join(rendered_lines)
    rows = tuple(
        tuple(Button(_button_label(button), button.callback_data) for button in row)
        for row in screen.rows
    )
    return _project_residual(Screen(text=text, rows=rows))


def _project_composition(screen: Screen) -> Screen:
    rows: list[tuple[Button, ...]] = []
    for row in screen.rows:
        rendered: list[Button] = []
        for button in row:
            label = button.label
            if button.callback_data.startswith("k122ok:"):
                label = "Подтвердить состав"
            elif button.callback_data == "k122cancel":
                label = "Отмена"
            elif button.callback_data.startswith("o:"):
                label = "Назад к добавке"
            rendered.append(Button(label, button.callback_data))
        rows.append(tuple(rendered))

    callbacks = {button.callback_data for row in rows for button in row}
    if "k122tot" in callbacks and not any(data.startswith("o:") for data in callbacks):
        rows = list(
            _merge_rows(
                tuple(rows),
                (
                    (Button("Сегодня", "k120today"),),
                    (Button("Добавки", "ls"),),
                ),
            )
        )
    return Screen(text=screen.text, rows=tuple(rows))


def _project_totals(screen: Screen) -> Screen:
    rows: list[tuple[Button, ...]] = []
    for row in screen.rows:
        rendered: list[Button] = []
        for button in row:
            label = button.label
            if button.callback_data == "k122safe":
                label = "Проверка"
            elif button.callback_data == "k122rules":
                label = "Почему так распределено?"
            elif button.callback_data.startswith("k146c:"):
                label = button.label
            rendered.append(Button(label, button.callback_data))
        rows.append(tuple(rendered))
    return Screen(
        text=screen.text,
        rows=_merge_rows(
            tuple(rows),
            (
                (Button("Сегодня", "k120today"), Button("План", "k120p")),
                (Button("Добавки", "ls"),),
            ),
        ),
    )


def _project_safety(screen: Screen) -> Screen:
    rows = tuple(
        tuple(
            Button(
                "Почему? / Источники"
                if button.callback_data.startswith("k122src:")
                else button.label,
                button.callback_data,
            )
            for button in row
        )
        for row in screen.rows
    )
    return Screen(
        text=screen.text,
        rows=_merge_rows(
            rows,
            (
                (Button("Итоги", "k122tot"),),
                (Button("Сегодня", "k120today"),),
            ),
        ),
    )


def _project_rules(screen: Screen) -> Screen:
    rows = tuple(
        tuple(
            Button(
                "Источники правила"
                if button.callback_data.startswith("k122why:")
                else button.label,
                button.callback_data,
            )
            for button in row
        )
        for row in screen.rows
    )
    return Screen(
        text=screen.text,
        rows=_merge_rows(
            rows,
            (
                (Button("Сегодня", "k120today"), Button("План", "k120p")),
                (Button("Итоги", "k122tot"),),
            ),
        ),
    )


def _project_sources(screen: Screen) -> Screen:
    rows = tuple(
        tuple(
            Button(
                "Назад" if button.callback_data in {"k122rules", "k122safe"} else button.label,
                button.callback_data,
            )
            for button in row
        )
        for row in screen.rows
    )
    return Screen(text=screen.text, rows=rows)


def _project_why(screen: Screen) -> Screen:
    return Screen(
        text=screen.text,
        rows=tuple(
            tuple(
                Button(
                    "Назад к «Сегодня»" if button.callback_data == "k120today" else button.label,
                    button.callback_data,
                )
                for button in row
            )
            for row in screen.rows
        ),
    )


def _project_today(screen: Screen) -> Screen:
    rows = _without_callbacks(screen.rows, {"k120p", "k120h", "ls", "a", "k122tot"})
    footer = (
        (Button("+ Добавить добавку", "a"),),
        (Button("Итоги", "k122tot"), Button("План", "k120p")),
        (Button("Добавки", "ls"), Button("История", "k120h")),
    )
    return Screen(text=screen.text, rows=_merge_rows(rows, footer))


def _project_supplements(screen: Screen) -> Screen:
    text = screen.text
    if text.startswith("No supplements yet.") or text.startswith("Добавок пока нет"):
        text = (
            "Добавок пока нет\n\n"
            "Добавьте первую добавку, чтобы подтвердить данные с этикетки "
            "и при необходимости настроить план."
        )
    else:
        text = screen.text
    rows = tuple(
        tuple(
            Button(
                (
                    "Открыть " + button.label.removeprefix("Open ")
                    if button.label.startswith("Open ")
                    else _button_label(button)
                ),
                button.callback_data,
            )
            for button in row
        )
        for row in screen.rows
    )
    rows = _without_callbacks(rows, {"a", "k120today", "k120p", "k120h"})
    footer = (
        (Button("Добавить добавку", "a"),),
        (Button("Сегодня", "k120today"), Button("План", "k120p")),
        (Button("История", "k120h"),),
    )
    return Screen(text=text, rows=_merge_rows(rows, footer))


def _project_supplement(screen: Screen) -> Screen:
    rows = screen.rows
    callbacks = [button for row in rows for button in row]
    destructive = next(
        (button for button in callbacks if button.callback_data.startswith("rc:")),
        None,
    )
    if destructive is not None:
        parts = destructive.callback_data.split(":")
        name = screen.text.splitlines()[0]
        if name.startswith("Remove ") and name.endswith("?"):
            name = name[len("Remove ") : -1]
        text = (
            f"Удалить {name}?\n\n"
            "Будет удалена эта отслеживаемая ручная запись, её сохранённый план "
            "и связанная история приёма. Служебные строки, созданные только для этой "
            "ручной записи, удаляются в той же транзакции.\n\n"
            "Другие отслеживаемые добавки не изменятся."
        )
        cancel = next(
            (button for button in callbacks if button.callback_data.startswith("o:")),
            None,
        )
        return Screen(
            text=text,
            rows=(
                (Button(f"Удалить {name}", destructive.callback_data),),
                (
                    Button(
                        "Отмена",
                        cancel.callback_data if cancel is not None else "ls",
                    ),
                ),
            ),
        )

    plan = next((b for b in callbacks if b.callback_data.startswith("p:")), None)
    edit_name = next((b for b in callbacks if b.callback_data.startswith("en:")), None)
    edit_serving = next((b for b in callbacks if b.callback_data.startswith("es:")), None)
    remove = next((b for b in callbacks if b.callback_data.startswith("rp:")), None)

    if plan is None:
        return _project_residual(screen)

    parts = plan.callback_data.split(":")
    composition_callback = f"k122c:{parts[1]}:{parts[2]}" if len(parts) == 3 else "k122comp"
    new_rows: list[tuple[Button, ...]] = [
        (Button("Состав", composition_callback),),
        (Button("Добавить / изменить план", plan.callback_data),),
        (Button("Итоги", "k122tot"),),
    ]
    if edit_name is not None and edit_serving is not None:
        new_rows.append(
            (
                Button("Изменить название", edit_name.callback_data),
                Button("Изменить порцию", edit_serving.callback_data),
            )
        )
    if remove is not None:
        new_rows.append((Button("Удалить добавку…", remove.callback_data),))
    new_rows.append((Button("Назад к добавкам", "ls"),))
    return Screen(text=screen.text, rows=tuple(new_rows))


def _project_plan(screen: Screen) -> Screen:
    rendered: list[str] = []
    for line in screen.text.splitlines():
        if line.startswith("• "):
            row, separator, schedule = line[2:].rpartition(" — ")
            rendered_schedule = _ROUTINE_BUCKET_LABELS.get(schedule, schedule)
            if separator:
                rendered.append(f"Ваша настройка: {row} — {rendered_schedule}")
            else:
                rendered.append("Ваша настройка: " + line[2:])
        else:
            rendered.append(line)
    rows = _without_callbacks(
        screen.rows,
        {"k120today", "k120h", "k122rules", "ls"},
    )
    footer = (
        (Button("Почему так распределено?", "k122rules"),),
        (Button("Сегодня", "k120today"), Button("История", "k120h")),
        (Button("Добавки", "ls"),),
    )
    return _project_residual(Screen(text="\n".join(rendered), rows=_merge_rows(rows, footer)))


def _project_history(screen: Screen) -> Screen:
    rows: list[tuple[Button, ...]] = []
    for row in screen.rows:
        rendered: list[Button] = []
        for button in row:
            data = button.callback_data
            if data.startswith("k120c:"):
                data = "k120q:" + data.removeprefix("k120c:")
                rendered.append(Button("Исправить запись", data))
            elif data != "k120today":
                rendered.append(Button(_button_label(button), data))
        if rendered:
            rows.append(tuple(rendered))
    rows.append((Button("Сегодня", "k120today"),))
    return Screen(text=screen.text, rows=tuple(rows))


def _project_residual(screen: Screen) -> Screen:
    text = screen.text
    replacements = (
        (
            "No supplements yet.\n\nAdd one manually to get started.",
            "Добавок пока нет.\n\nДобавьте первую добавку.",
        ),
        (
            "The manual draft is no longer available.",
            "Черновик ручного ввода больше недоступен. Начните добавление заново.",
        ),
        (
            "This input state is not supported.",
            "Этот шаг ввода больше недоступен. Откройте текущее состояние снова.",
        ),
        (
            "That action payload is invalid. Please reopen the current view.",
            "Этот экран уже изменился. Действие не применено. Откройте текущее состояние снова.",
        ),
        (
            "That action is not available in this MVP slice.",
            "Это действие сейчас недоступно. Откройте текущее состояние снова.",
        ),
        (
            "Unsupported Today/Plan action.",
            "Это действие больше недоступно. Откройте текущее состояние через "
            "«Сегодня» или «План».",
        ),
        (
            "No Plan field is waiting for text input.",
            "Сейчас ни одно поле плана не ждёт текстового ввода.",
        ),
        (
            "This Plan edit is out of date. Open the current Plan and try again.",
            "Этот экран плана уже изменился. Действие не применено. "
            "Откройте текущий «План» и повторите.",
        ),
        (
            "Pending input cancelled. Confirmed records were not changed.",
            "Ввод отменён. Подтверждённые записи не изменены.",
        ),
        (
            "I’m not waiting for free-form input right now. Use /add, /supplements, or /profile.",
            "Сейчас я не жду текстового ввода. Откройте «Добавить», «Добавки» или «Профиль».",
        ),
        ("Please send a non-empty supplement name.", "Введите непустое название добавки."),
        (
            "The supplement name is too long for this MVP entry field.",
            "Название слишком длинное. Сократите его и повторите.",
        ),
        (
            "The supplement name contains unsupported control characters.",
            "Название содержит неподдерживаемые служебные символы. Исправьте ввод.",
        ),
        (
            "Enter a positive decimal number, for example 1, 1.5, or 2,5.",
            "Введите положительное число, например 1, 1.5 или 2,5.",
        ),
        ("Enter a valid positive decimal number.", "Введите корректное положительное число."),
        ("Quantity must be greater than zero.", "Количество должно быть больше нуля."),
        ("Timezone value is too long.", "Значение часового пояса слишком длинное."),
        (
            "I don’t recognize that IANA timezone. Example: Europe/Helsinki.",
            "Не удалось распознать часовой пояс. Пример: Europe/Helsinki.",
        ),
        (
            "Use a locale such as en, fi, en-GB, or pt-BR.",
            "Укажите код языка, например ru, en, fi или en-GB.",
        ),
        (
            "Routine preference updated. The planned product-unit amount was not changed.",
            "Настройка времени обновлена. Количество единиц продукта в плане не изменилось.",
        ),
        (
            "Exact local time saved. The planned product-unit amount was not changed.",
            "Точное местное время сохранено. Количество единиц продукта в плане не изменилось.",
        ),
        (
            "Send a local time as HH:MM, for example 08:30.",
            "Введите местное время в формате ЧЧ:ММ, например 08:30.",
        ),
        (
            "Send a local time as HH:MM without seconds or timezone.",
            "Введите местное время как ЧЧ:ММ — без секунд и часового пояса.",
        ),
        (
            "Supplement removed. The tracked record, its saved plan, and linked "
            "intake history were removed. Manual support rows created only for "
            "this tracked record were also deleted.",
            "Добавка удалена. Удалены эта отслеживаемая ручная запись, её сохранённый "
            "план и связанная история приёма. Служебные строки, созданные только "
            "для этой записи, также удалены.",
        ),
        ("Timezone updated.", "Часовой пояс обновлён."),
        ("Locale updated.", "Язык интерфейса обновлён."),
        ("Name updated.", "Название обновлено."),
        ("Serving updated.", "Порция обновлена."),
    )
    rendered_lines: list[str] = []
    for line in text.splitlines():
        rendered_line = line
        for source, target in replacements:
            if rendered_line == source:
                rendered_line = target
                break
        rendered_lines.append(rendered_line)
    return Screen(text="\n".join(rendered_lines), rows=screen.rows)


def _without_callbacks(
    rows: tuple[tuple[Button, ...], ...],
    callback_ids: set[str],
) -> tuple[tuple[Button, ...], ...]:
    kept: list[tuple[Button, ...]] = []
    for row in rows:
        filtered = tuple(button for button in row if button.callback_data not in callback_ids)
        if filtered:
            kept.append(filtered)
    return tuple(kept)


def _merge_rows(
    rows: tuple[tuple[Button, ...], ...],
    extra: tuple[tuple[Button, ...], ...],
) -> tuple[tuple[Button, ...], ...]:
    seen = {button.callback_data for row in rows for button in row}
    merged = list(rows)
    for row in extra:
        filtered = tuple(button for button in row if button.callback_data not in seen)
        if filtered:
            merged.append(filtered)
            seen.update(button.callback_data for button in filtered)
    return tuple(merged)


def _with_footer(screen: Screen, footer: tuple[tuple[Button, ...], ...]) -> Screen:
    return Screen(text=screen.text, rows=_merge_rows(screen.rows, footer))


def _scientific_button_label(label: str) -> str:
    return {
        "Available cards": "Доступные карточки",
        "Reference values": "Справочные значения",
        "Sources": "Источники",
        "Why / Sources": "Почему? / Источники",
        "Back": "Назад",
        "Why?": "Почему?",
    }.get(label, label)
