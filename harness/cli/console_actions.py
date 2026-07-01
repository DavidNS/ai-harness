"""Backward-compatible imports for the pure action registry."""

from __future__ import annotations

from .actions import CONSOLE_ACTIONS, ConsoleAction, action_names, actions_by_name, top_level_action_names, visible_actions
from .console.action_specs import action_specs

__all__ = [
    "CONSOLE_ACTIONS",
    "ConsoleAction",
    "action_names",
    "actions_by_name",
    "top_level_action_names",
    "visible_actions",
    "action_specs",
]
