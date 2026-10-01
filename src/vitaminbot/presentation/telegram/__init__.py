"""Telegram presentation renderers."""

from vitaminbot.presentation.telegram.account import render_account_deletion
from vitaminbot.presentation.telegram.add import render_quick_add
from vitaminbot.presentation.telegram.adherence import render_adherence
from vitaminbot.presentation.telegram.composition import render_composition
from vitaminbot.presentation.telegram.history import render_history, render_history_action_result
from vitaminbot.presentation.telegram.inventory import render_inventory_edit
from vitaminbot.presentation.telegram.plan import render_plan, render_plan_action_result
from vitaminbot.presentation.telegram.safety import render_safety, render_safety_sources
from vitaminbot.presentation.telegram.supplement import render_supplement_detail
from vitaminbot.presentation.telegram.today import render_today, render_today_action_result
from vitaminbot.presentation.telegram.totals import render_regimen_totals

__all__ = [
    "render_account_deletion",
    "render_adherence",
    "render_composition",
    "render_history",
    "render_history_action_result",
    "render_inventory_edit",
    "render_plan",
    "render_plan_action_result",
    "render_quick_add",
    "render_safety",
    "render_safety_sources",
    "render_supplement_detail",
    "render_regimen_totals",
    "render_today",
    "render_today_action_result",
]
