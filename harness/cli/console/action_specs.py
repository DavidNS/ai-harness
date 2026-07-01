"""Console-specific projection of the pure action registry."""

from __future__ import annotations

from ..actions import CONSOLE_ACTIONS, ConsoleAction
from .model import ConsoleActionSpec


def action_specs(actions: tuple[ConsoleAction, ...] = CONSOLE_ACTIONS) -> tuple[ConsoleActionSpec, ...]:
    return tuple(
        ConsoleActionSpec(
            name=action.name,
            label=action.label,
            key=action.key,
            shortcuts=action.aliases,
            menu_visible=action.menu_visible,
        )
        for action in actions
    )
