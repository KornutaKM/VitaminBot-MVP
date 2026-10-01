from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from vitaminbot.application.views.add import QuickAddStep, QuickAddView
from vitaminbot.persistence.kir116 import (
    BotSession,
    InvalidTransition,
    KIR116Store,
    ManualDraft,
    ProfileRecord,
    RecordNotFound,
    StaleAction,
    SupplementRecord,
)

_NAME_MAX_LENGTH = 120
_DECIMAL_PATTERN = re.compile(r"^\d{1,12}(?:[.,]\d{1,6})?$")
_LOCALE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8}){0,2}$")

UNIT_CODES = {
    "c": "capsule",
    "t": "tablet",
    "sg": "softgel",
    "sc": "scoop",
    "d": "drop",
}
BUCKET_CODES = {
    "m": "morning",
    "d": "day",
    "e": "evening",
}


@dataclass(frozen=True, slots=True)
class Button:
    label: str
    callback_data: str


@dataclass(frozen=True, slots=True)
class Screen:
    text: str
    rows: tuple[tuple[Button, ...], ...] = ()


class KIR116Controller:
    """Transport-independent state machine for onboarding/manual entry."""

    def __init__(self, store: KIR116Store) -> None:
        self._store = store

    def start(self, telegram_user_id: int) -> Screen:
        self._store.ensure_user(telegram_user_id)
        return Screen(
            text=(
                "Welcome to VitaminBot\n\n"
                "Add the supplements you use, confirm what you entered, and organize "
                "your routine. I’ll keep uncertain information explicit and won’t "
                "generate medical dose recommendations during onboarding.\n\n"
                "Manual entry is available in this MVP slice."
            ),
            rows=(
                (Button("Add first supplement", "a"),),
                (Button("How it works", "h"),),
            ),
        )

    def help(self, telegram_user_id: int) -> Screen:
        self._store.ensure_user(telegram_user_id)
        return Screen(
            text=(
                "VitaminBot MVP\n\n"
                "Available now:\n"
                "• /add — add a supplement manually\n"
                "• /supplements — list tracked supplements\n"
                "• /plan — recurring schedule preferences\n"
                "• /today — today’s generated occurrences\n"
                "• /history — Taken / Skip / correction history\n"
                "• /profile — review or correct technical profile fields\n"
                "• /cancel — cancel pending input\n\n"
                "Photo and barcode capture are hidden until those flows are actually shipped."
            ),
            rows=((Button("Add supplement", "a"),),),
        )

    def has_supplements(self, telegram_user_id: int) -> bool:
        user_id = self._store.ensure_user(telegram_user_id)
        return bool(self._store.list_supplements(user_id))

    def quick_add_pending(self, telegram_user_id: int) -> bool:
        user_id = self._store.ensure_user(telegram_user_id)
        session = self._store.get_session(user_id)
        return (
            session is not None
            and session.pending_text == "quick"
            and session.state in {"manual_name", "manual_unit", "plan_quantity", "plan_bucket"}
        )

    def quick_add_start(
        self,
        telegram_user_id: int,
        *,
        action_key: str,
    ) -> QuickAddView:
        user_id = self._store.ensure_user(telegram_user_id)
        try:
            draft = self._store.begin_quick(user_id, action_key)
        except (InvalidTransition, StaleAction, RecordNotFound):
            return QuickAddView(step=QuickAddStep.STALE)
        return QuickAddView(
            step=QuickAddStep.NAME,
            draft_id=draft.draft_id,
            revision=draft.revision,
        )

    def quick_add_text(
        self,
        telegram_user_id: int,
        value: str,
        *,
        action_key: str,
    ) -> QuickAddView:
        user_id = self._store.ensure_user(telegram_user_id)
        session = self._store.get_session(user_id)
        if session is None or session.pending_text != "quick":
            return QuickAddView(step=QuickAddStep.INVALID)

        try:
            if session.state == "manual_name":
                name = self._validate_name(value)
                draft = self._store.set_manual_name(user_id, action_key, name)
                return QuickAddView(
                    step=QuickAddStep.UNIT,
                    name=draft.product_name,
                    draft_id=draft.draft_id,
                    revision=draft.revision,
                )
            if session.state == "manual_unit":
                draft = self._store.get_draft(user_id)
                if draft is None:
                    return QuickAddView(step=QuickAddStep.STALE)
                return QuickAddView(
                    step=QuickAddStep.UNIT,
                    name=draft.product_name,
                    draft_id=draft.draft_id,
                    revision=draft.revision,
                )
            if session.state == "plan_quantity":
                quantity = self._parse_positive_decimal(value)
                next_session = self._store.set_plan_quantity(
                    user_id,
                    action_key,
                    quantity,
                )
                if next_session.target_instance_id is None:
                    return QuickAddView(step=QuickAddStep.INVALID)
                record = self._store.supplement(user_id, next_session.target_instance_id)
                return QuickAddView(
                    step=QuickAddStep.BUCKET,
                    name=record.name,
                    unit_label=record.unit_label,
                    quantity=next_session.pending_quantity,
                    supplement_instance_id=record.instance_id,
                    supplement_revision=record.revision,
                    revision=next_session.revision,
                )
            if session.state == "plan_bucket":
                if session.target_instance_id is None:
                    return QuickAddView(step=QuickAddStep.STALE)
                record = self._store.supplement(user_id, session.target_instance_id)
                return QuickAddView(
                    step=QuickAddStep.BUCKET,
                    name=record.name,
                    unit_label=record.unit_label,
                    quantity=session.pending_quantity,
                    supplement_instance_id=record.instance_id,
                    supplement_revision=record.revision,
                    revision=session.revision,
                )
        except ValueError:
            if session.state == "manual_name":
                draft = self._store.get_draft(user_id)
                return QuickAddView(
                    step=QuickAddStep.NAME,
                    draft_id=None if draft is None else draft.draft_id,
                    revision=None if draft is None else draft.revision,
                )
            if session.state == "plan_quantity" and session.target_instance_id is not None:
                record = self._store.supplement(user_id, session.target_instance_id)
                return QuickAddView(
                    step=QuickAddStep.QUANTITY,
                    name=record.name,
                    unit_label=record.unit_label,
                    supplement_instance_id=record.instance_id,
                    supplement_revision=record.revision,
                )
            return QuickAddView(step=QuickAddStep.INVALID)
        except (InvalidTransition, StaleAction, RecordNotFound):
            return QuickAddView(step=QuickAddStep.STALE)

        return QuickAddView(step=QuickAddStep.INVALID)

    def quick_add_callback(
        self,
        telegram_user_id: int,
        data: str,
        *,
        action_key: str,
    ) -> QuickAddView:
        user_id = self._store.ensure_user(telegram_user_id)
        parts = data.split(":")
        action = parts[0]
        try:
            if action == "qac":
                self._store.cancel_pending(user_id)
                return QuickAddView(step=QuickAddStep.CANCELLED)
            if action == "qau":
                if len(parts) != 4:
                    return QuickAddView(step=QuickAddStep.INVALID)
                draft_id = parts[1]
                expected_revision = int(parts[2])
                unit = UNIT_CODES.get(parts[3])
                if unit is None:
                    return QuickAddView(step=QuickAddStep.INVALID)
                record = self._store.confirm_quick_unit_and_begin_plan(
                    user_id,
                    action_key,
                    draft_id,
                    expected_revision,
                    unit,
                )
                return QuickAddView(
                    step=QuickAddStep.QUANTITY,
                    name=record.name,
                    unit_label=record.unit_label,
                    supplement_instance_id=record.instance_id,
                    supplement_revision=record.revision,
                )
            if action == "qaq":
                if len(parts) != 2:
                    return QuickAddView(step=QuickAddStep.INVALID)
                if parts[1] == "custom":
                    session = self._store.get_session(user_id)
                    if (
                        session is None
                        or session.pending_text != "quick"
                        or session.target_instance_id is None
                    ):
                        return QuickAddView(step=QuickAddStep.STALE)
                    record = self._store.supplement(user_id, session.target_instance_id)
                    return QuickAddView(
                        step=QuickAddStep.QUANTITY,
                        name=record.name,
                        unit_label=record.unit_label,
                        supplement_instance_id=record.instance_id,
                        supplement_revision=record.revision,
                    )
                quantity = self._parse_positive_decimal(parts[1])
                session = self._store.set_plan_quantity(user_id, action_key, quantity)
                if session.target_instance_id is None:
                    return QuickAddView(step=QuickAddStep.INVALID)
                record = self._store.supplement(user_id, session.target_instance_id)
                return QuickAddView(
                    step=QuickAddStep.BUCKET,
                    name=record.name,
                    unit_label=record.unit_label,
                    quantity=session.pending_quantity,
                    supplement_instance_id=record.instance_id,
                    supplement_revision=record.revision,
                    revision=session.revision,
                )
            if action == "qab":
                if len(parts) != 3:
                    return QuickAddView(step=QuickAddStep.INVALID)
                bucket = BUCKET_CODES.get(parts[1])
                if bucket is None:
                    return QuickAddView(step=QuickAddStep.INVALID)
                record = self._store.save_plan(
                    user_id,
                    action_key,
                    bucket,
                    int(parts[2]),
                )
                return QuickAddView(
                    step=QuickAddStep.COMPLETE,
                    name=record.name,
                    unit_label=record.unit_label,
                    quantity=record.plan_quantity,
                    bucket=record.plan_bucket,
                    supplement_instance_id=record.instance_id,
                    supplement_revision=record.revision,
                )
        except (IndexError, ValueError):
            return QuickAddView(step=QuickAddStep.INVALID)
        except (InvalidTransition, StaleAction, RecordNotFound):
            return QuickAddView(step=QuickAddStep.STALE)

        return QuickAddView(step=QuickAddStep.INVALID)

    def add(self, telegram_user_id: int) -> Screen:
        self._store.ensure_user(telegram_user_id)
        return Screen(
            text=(
                "Add a supplement\n\n"
                "Manual entry is available in this version. "
                "Photo and barcode options are not shown until their implementation is ready."
            ),
            rows=((Button("Enter manually", "m"),),),
        )

    def supplements(self, telegram_user_id: int) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        records = self._store.list_supplements(user_id)
        if not records:
            return Screen(
                text="No supplements yet.\n\nAdd one manually to get started.",
                rows=((Button("Add supplement", "a"),),),
            )

        lines = [f"My supplements — {len(records)}", ""]
        rows: list[tuple[Button, ...]] = []
        for index, record in enumerate(records, start=1):
            state = "plan set" if record.plan_quantity is not None else "no plan yet"
            lines.append(f"{index}. {record.name} — {state}")
            rows.append(
                (
                    Button(
                        f"Open {record.name[:32]}",
                        self._supplement_callback("o", record),
                    ),
                )
            )
        rows.append((Button("Add supplement", "a"),))
        return Screen(text="\n".join(lines), rows=tuple(rows))

    def profile(self, telegram_user_id: int) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        profile = self._store.profile(user_id)
        return self._profile_screen(profile)

    def cancel(self, telegram_user_id: int) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        self._store.cancel_pending(user_id)
        return Screen(
            text="Pending input cancelled. No confirmed supplement or plan was changed.",
            rows=((Button("My supplements", "ls"),),),
        )

    def text(
        self,
        telegram_user_id: int,
        text: str,
        *,
        action_key: str,
    ) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        session = self._store.get_session(user_id)
        if session is None:
            return Screen(
                text=(
                    "I’m not waiting for free-form input right now. "
                    "Use /add, /supplements, or /profile."
                )
            )

        try:
            if session.state == "manual_name":
                name = self._validate_name(text)
                draft = self._store.set_manual_name(user_id, action_key, name)
                return self._manual_unit_screen(draft)
            if session.state == "manual_unit":
                return self._manual_unit_screen_from_session(user_id, session)
            if session.state == "manual_serving_quantity":
                quantity = self._parse_positive_decimal(text)
                draft = self._store.set_manual_serving_quantity(
                    user_id,
                    action_key,
                    quantity,
                )
                return self._manual_review_screen(draft)
            if session.state == "manual_review":
                return self._manual_review_screen_from_user(user_id)
            if session.state == "plan_quantity":
                quantity = self._parse_positive_decimal(text)
                next_session = self._store.set_plan_quantity(
                    user_id,
                    action_key,
                    quantity,
                )
                return self._plan_bucket_screen(next_session)
            if session.state == "plan_bucket":
                return self._plan_bucket_screen(session)
            if session.state == "profile_timezone":
                timezone = self._validate_timezone(text)
                profile = self._store.save_profile_field(
                    user_id,
                    action_key,
                    "timezone",
                    timezone,
                )
                return self._profile_screen(profile, prefix="Timezone updated.\n\n")
            if session.state == "profile_locale":
                locale = self._validate_locale(text)
                profile = self._store.save_profile_field(
                    user_id,
                    action_key,
                    "locale",
                    locale,
                )
                return self._profile_screen(profile, prefix="Locale updated.\n\n")
            if session.state == "edit_name":
                name = self._validate_name(text)
                record = self._store.save_edit_name(user_id, action_key, name)
                return self._supplement_screen(record, prefix="Name updated.\n\n")
            if session.state == "edit_serving_unit":
                record = self._store.supplement(
                    user_id,
                    self._required_target(session),
                )
                return self._edit_serving_unit_screen(record, session)
            if session.state == "edit_serving_quantity":
                quantity = self._parse_positive_decimal(text)
                record = self._store.save_edit_serving_quantity(
                    user_id,
                    action_key,
                    quantity,
                )
                return self._supplement_screen(
                    record,
                    prefix="Serving updated.\n\n",
                )
        except ValueError as exc:
            return Screen(text=str(exc))
        except (InvalidTransition, StaleAction, RecordNotFound):
            return self._stale_screen(user_id)

        return Screen(text="This input state is not supported.")

    def callback(
        self,
        telegram_user_id: int,
        data: str,
        *,
        action_key: str,
    ) -> Screen:
        user_id = self._store.ensure_user(telegram_user_id)
        parts = data.split(":")
        action = parts[0]

        try:
            if action == "a":
                return self.add(telegram_user_id)
            if action == "h":
                return Screen(
                    text=(
                        "How it works\n\n"
                        "Product/label facts and your intake plan are stored as different things. "
                        "Manual confirmation means “this matches what I entered”, "
                        "not “this is safe”.\n\n"
                        "Technical profile fields are optional here and can be reviewed "
                        "or corrected. "
                        "Safety/applicability questions are requested only when a governed "
                        "feature needs them."
                    ),
                    rows=((Button("Add first supplement", "a"),),),
                )
            if action == "ls":
                return self.supplements(telegram_user_id)
            if action == "pf":
                return self.profile(telegram_user_id)
            if action == "m":
                draft = self._store.begin_manual(user_id, action_key)
                return self._screen_for_draft(user_id, draft)
            if action == "mu":
                draft_id, revision, unit_code = parts[1], int(parts[2]), parts[3]
                unit = UNIT_CODES.get(unit_code)
                if unit is None:
                    raise ValueError("Unsupported product-unit choice.")
                draft = self._store.set_manual_unit(
                    user_id,
                    action_key,
                    draft_id,
                    revision,
                    unit,
                )
                return Screen(
                    text=(
                        f"Serving — {draft.product_name}\n\n"
                        f"How many {unit} units make one label serving?\n"
                        "Enter a positive number. I won’t convert it into a nutrient dose."
                    )
                )
            if action == "me":
                draft = self._store.restart_manual_edit(
                    user_id,
                    action_key,
                    parts[1],
                    int(parts[2]),
                )
                return Screen(
                    text=(
                        "Edit manual entry\n\n"
                        f"Current name: {draft.product_name or 'not set'}\n"
                        "Send the supplement name you want recorded."
                    )
                )
            if action == "mc":
                record = self._store.confirm_manual(
                    user_id,
                    action_key,
                    parts[1],
                    int(parts[2]),
                )
                return self._supplement_screen(
                    record,
                    prefix=(
                        "Manual entry confirmed. This records what you entered; "
                        "it is not a safety or dose recommendation.\n\n"
                    ),
                )
            if action == "o":
                record = self._record_from_token(user_id, parts[1], int(parts[2]))
                return self._supplement_screen(record)
            if action == "p":
                instance_id = self._instance_id(parts[1])
                session = self._store.begin_plan(
                    user_id,
                    action_key,
                    instance_id,
                    int(parts[2]),
                )
                return Screen(
                    text=(
                        "Add to plan\n\n"
                        "How many product units do you plan to take in this routine event?\n"
                        "Enter a positive number. This is your plan, not a medical "
                        "dose recommendation."
                    )
                )
            if action == "pb":
                bucket = BUCKET_CODES.get(parts[1])
                if bucket is None:
                    raise ValueError("Unsupported routine bucket.")
                record = self._store.save_plan(
                    user_id,
                    action_key,
                    bucket,
                    int(parts[2]),
                )
                return self._supplement_screen(
                    record,
                    prefix=(
                        "Plan saved. Morning / Day / Evening are routine buckets, "
                        "not biological timing claims.\n\n"
                    ),
                )
            if action == "pt":
                self._store.begin_profile_edit(
                    user_id,
                    action_key,
                    "timezone",
                    int(parts[1]),
                )
                return Screen(
                    text=(
                        "Edit timezone\n\n"
                        "Send an IANA timezone such as Europe/Helsinki. "
                        "This technical field is used for local scheduling when "
                        "reminder features need it."
                    )
                )
            if action == "pl":
                self._store.begin_profile_edit(
                    user_id,
                    action_key,
                    "locale",
                    int(parts[1]),
                )
                return Screen(
                    text=(
                        "Edit locale\n\n"
                        "Send a locale such as en, fi, or en-GB. "
                        "This controls presentation only; it is not a medical applicability field."
                    )
                )
            if action == "en":
                record = self._record_from_token(user_id, parts[1], int(parts[2]))
                self._store.begin_edit_name(
                    user_id,
                    action_key,
                    record.instance_id,
                    record.revision,
                )
                return Screen(
                    text=(f"Edit name — {record.name}\n\nSend the new tracked supplement name.")
                )
            if action == "es":
                record = self._record_from_token(user_id, parts[1], int(parts[2]))
                session = self._store.begin_edit_serving(
                    user_id,
                    action_key,
                    record.instance_id,
                    record.revision,
                )
                return self._edit_serving_unit_screen(record, session)
            if action == "eu":
                unit = UNIT_CODES.get(parts[2])
                if unit is None:
                    raise ValueError("Unsupported product-unit choice.")
                session = self._store.set_edit_serving_unit(
                    user_id,
                    action_key,
                    unit,
                    int(parts[1]),
                )
                return Screen(
                    text=(
                        f"New serving unit: {unit}\n\n"
                        "How many of these units make one label serving? "
                        "Enter a positive number."
                    )
                )
            if action == "rp":
                record = self._record_from_token(user_id, parts[1], int(parts[2]))
                return self._remove_confirmation_screen(record)
            if action == "rc":
                instance_id = self._instance_id(parts[1])
                self._store.remove_supplement(
                    user_id,
                    action_key,
                    instance_id,
                    int(parts[2]),
                )
                return Screen(
                    text=(
                        "Supplement removed. The tracked record, its saved plan, and linked "
                        "intake history were removed. Manual support rows created only for "
                        "this tracked record were also deleted."
                    ),
                    rows=((Button("My supplements", "ls"),),),
                )
            if action == "x":
                self._store.cancel_pending(user_id)
                return Screen(
                    text="Pending input cancelled. Confirmed records were not changed.",
                    rows=((Button("My supplements", "ls"),),),
                )
        except (IndexError, ValueError):
            return Screen(text="That action payload is invalid. Please reopen the current view.")
        except (InvalidTransition, StaleAction, RecordNotFound):
            return self._stale_screen(user_id)

        return Screen(text="That action is not available in this MVP slice.")

    def _screen_for_draft(self, user_id: UUID, draft: ManualDraft) -> Screen:
        if draft.product_name is None:
            return Screen(
                text=(
                    "Enter manually\n\n"
                    "Send the supplement name exactly as you want this tracked record to appear."
                )
            )
        if draft.unit_label is None:
            return self._manual_unit_screen(draft)
        if draft.units_per_serving is None:
            return Screen(
                text=(
                    f"Serving — {draft.product_name}\n\n"
                    f"How many {draft.unit_label} units make one label serving? "
                    "Enter a positive number."
                )
            )
        return self._manual_review_screen(draft)

    def _manual_unit_screen_from_session(
        self,
        user_id: UUID,
        session: BotSession,
    ) -> Screen:
        draft = self._store.get_draft(user_id)
        if draft is None:
            return Screen(text="The manual draft is no longer available.")
        return self._manual_unit_screen(draft)

    def _manual_review_screen_from_user(self, user_id: UUID) -> Screen:
        draft = self._store.get_draft(user_id)
        if draft is None:
            return Screen(text="The manual draft is no longer available.")
        return self._manual_review_screen(draft)

    @staticmethod
    def _manual_unit_screen(draft: ManualDraft) -> Screen:
        rows = (
            (
                Button("Capsule", f"mu:{draft.draft_id}:{draft.revision}:c"),
                Button("Tablet", f"mu:{draft.draft_id}:{draft.revision}:t"),
            ),
            (
                Button("Softgel", f"mu:{draft.draft_id}:{draft.revision}:sg"),
                Button("Scoop", f"mu:{draft.draft_id}:{draft.revision}:sc"),
            ),
            (Button("Drop", f"mu:{draft.draft_id}:{draft.revision}:d"),),
            (Button("Cancel", "x"),),
        )
        return Screen(
            text=(
                f"Product unit — {draft.product_name}\n\n"
                "Choose the unit printed or used for this product. "
                "This identifies a product unit; it does not convert nutrient quantities."
            ),
            rows=rows,
        )

    @staticmethod
    def _manual_review_screen(draft: ManualDraft) -> Screen:
        assert draft.product_name is not None
        assert draft.unit_label is not None
        assert draft.units_per_serving is not None
        return Screen(
            text=(
                f"Review manual entry — {draft.product_name}\n\n"
                f"Product name: {draft.product_name}\n"
                f"Label serving: {KIR116Controller._display_decimal(draft.units_per_serving)} "
                f"{draft.unit_label}\n"
                "Source: You entered these facts manually.\n\n"
                "Confirming means this matches what you entered. "
                "It does not mean the supplement is safe or appropriate for you."
            ),
            rows=(
                (Button("Confirm entry", f"mc:{draft.draft_id}:{draft.revision}"),),
                (Button("Edit", f"me:{draft.draft_id}:{draft.revision}"), Button("Cancel", "x")),
            ),
        )

    @staticmethod
    def _plan_bucket_screen(session: BotSession) -> Screen:
        assert session.pending_quantity is not None
        return Screen(
            text=(
                "Choose a routine bucket\n\n"
                f"Planned quantity: {KIR116Controller._display_decimal(session.pending_quantity)} "
                "product units.\n\n"
                "Morning / Day / Evening are routine labels only. "
                "No biological timing claim is being made."
            ),
            rows=(
                (
                    Button("Morning", f"pb:m:{session.revision}"),
                    Button("Day", f"pb:d:{session.revision}"),
                ),
                (Button("Evening", f"pb:e:{session.revision}"),),
                (Button("Cancel", "x"),),
            ),
        )

    @staticmethod
    def _profile_screen(profile: ProfileRecord, *, prefix: str = "") -> Screen:
        timezone = profile.timezone or "Not set"
        locale = profile.locale or "Not set"
        return Screen(
            text=(
                f"{prefix}Profile\n\n"
                f"Timezone: {timezone}\n"
                f"Locale: {locale}\n\n"
                "Only technical profile fields are collected here. "
                "Medical/applicability fields are not collected speculatively."
            ),
            rows=(
                (Button("Edit timezone", f"pt:{profile.version}"),),
                (Button("Edit locale", f"pl:{profile.version}"),),
            ),
        )

    @staticmethod
    def _supplement_screen(
        record: SupplementRecord,
        *,
        prefix: str = "",
    ) -> Screen:
        plan = "Not set"
        if record.plan_quantity is not None and record.plan_bucket is not None:
            plan_unit_label = record.plan_unit_label or record.unit_label
            plan = (
                f"{record.plan_bucket.title()} — "
                f"{KIR116Controller._display_decimal(record.plan_quantity)} {plan_unit_label}"
            )
        plan_note = ""
        if (
            record.plan_quantity is not None
            and record.plan_unit_label is not None
            and record.plan_unit_label != record.unit_label
        ):
            plan_note = (
                "\nSaved plan note: this plan keeps the previous product-unit meaning "
                f"({record.plan_unit_label}). Review the plan if you want to change it.\n"
            )
        return Screen(
            text=(
                f"{prefix}{record.name}\n\n"
                "Status: Confirmed manual entry\n"
                + (
                    f"Tracked unit: 1 {record.unit_label}\n"
                    if record.serving_basis_type == "per_consumption_unit"
                    else (
                        "Label serving: "
                        f"{KIR116Controller._display_decimal(record.units_per_serving)} "
                        f"{record.unit_label}\n"
                    )
                )
                + f"Your plan: {plan}\n"
                f"{plan_note}\n"
                "Product facts and your plan are stored separately."
            ),
            rows=(
                (Button("Add / edit plan", KIR116Controller._supplement_callback("p", record)),),
                (
                    Button("Edit name", KIR116Controller._supplement_callback("en", record)),
                    Button("Edit serving", KIR116Controller._supplement_callback("es", record)),
                ),
                (
                    Button(
                        "Remove supplement…",
                        KIR116Controller._supplement_callback("rp", record),
                    ),
                ),
                (Button("Back to supplements", "ls"),),
            ),
        )

    @staticmethod
    def _remove_confirmation_screen(record: SupplementRecord) -> Screen:
        return Screen(
            text=(
                f"Remove {record.name}?\n\n"
                "This removes the tracked supplement, its saved plan, and linked intake history. "
                "Manual support rows created only for this tracked record are removed as part of "
                "the same database transaction.\n\n"
                "This action does not silently merge or modify any other tracked supplement."
            ),
            rows=(
                (Button("Remove supplement", KIR116Controller._supplement_callback("rc", record)),),
                (Button("Cancel", KIR116Controller._supplement_callback("o", record)),),
            ),
        )

    def _edit_serving_unit_screen(
        self,
        record: SupplementRecord,
        session: BotSession,
    ) -> Screen:
        return Screen(
            text=(
                f"Edit serving — {record.name}\n\n"
                f"Current serving: {self._display_decimal(record.units_per_serving)} "
                f"{record.unit_label}\n"
                "Choose the new product-unit label."
            ),
            rows=(
                (
                    Button("Capsule", f"eu:{session.revision}:c"),
                    Button("Tablet", f"eu:{session.revision}:t"),
                ),
                (
                    Button("Softgel", f"eu:{session.revision}:sg"),
                    Button("Scoop", f"eu:{session.revision}:sc"),
                ),
                (Button("Drop", f"eu:{session.revision}:d"),),
                (Button("Cancel", "x"),),
            ),
        )

    def _record_from_token(
        self,
        user_id: UUID,
        token: str,
        expected_revision: int,
    ) -> SupplementRecord:
        record = self._store.supplement(
            user_id,
            self._instance_id(token),
        )
        if record.revision != expected_revision:
            raise StaleAction("supplement callback is stale")
        return record

    @staticmethod
    def _supplement_callback(action: str, record: SupplementRecord) -> str:
        token = record.instance_id.removeprefix("instance:manual:")
        return f"{action}:{token}:{record.revision}"

    @staticmethod
    def _instance_id(token: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{16}", token):
            raise ValueError("invalid supplement reference")
        return f"instance:manual:{token}"

    @staticmethod
    def _required_target(session: BotSession) -> str:
        if session.target_instance_id is None:
            raise InvalidTransition("target supplement is missing")
        return session.target_instance_id

    def _stale_screen(self, user_id: UUID) -> Screen:
        records = self._store.list_supplements(user_id)
        if records:
            return Screen(
                text=(
                    "This action is out of date, so I didn’t apply it. "
                    "Open the current supplement state and try again."
                ),
                rows=((Button("My supplements", "ls"),),),
            )
        return Screen(
            text=(
                "This action is out of date, so I didn’t apply it. Start again from Add supplement."
            ),
            rows=((Button("Add supplement", "a"),),),
        )

    @staticmethod
    def _validate_name(value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Please send a non-empty supplement name.")
        if len(normalized) > _NAME_MAX_LENGTH:
            raise ValueError("The supplement name is too long for this MVP entry field.")
        if any(ord(char) < 32 for char in normalized):
            raise ValueError("The supplement name contains unsupported control characters.")
        return normalized

    @staticmethod
    def _parse_positive_decimal(value: str) -> Decimal:
        normalized = value.strip()
        if not _DECIMAL_PATTERN.fullmatch(normalized):
            raise ValueError("Enter a positive decimal number, for example 1, 1.5, or 2,5.")
        try:
            quantity = Decimal(normalized.replace(",", "."))
        except InvalidOperation as exc:
            raise ValueError("Enter a valid positive decimal number.") from exc
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        return quantity

    @staticmethod
    def _validate_timezone(value: str) -> str:
        normalized = value.strip()
        if len(normalized) > 64:
            raise ValueError("Timezone value is too long.")
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                "I don’t recognize that IANA timezone. Example: Europe/Helsinki."
            ) from exc
        return normalized

    @staticmethod
    def _validate_locale(value: str) -> str:
        normalized = value.strip()
        if not _LOCALE_PATTERN.fullmatch(normalized):
            raise ValueError("Use a locale such as en, fi, en-GB, or pt-BR.")
        return normalized.replace("_", "-")

    @staticmethod
    def _display_decimal(value: Decimal) -> str:
        rendered = format(value.normalize(), "f")
        return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
