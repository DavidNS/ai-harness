"""Pure command/action registry shared by CLI and UI frontends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ConsoleContext = Literal["console"]


@dataclass(frozen=True, slots=True)
class ConsoleAction:
    name: str
    label: str
    key: str
    aliases: tuple[str, ...] = ()
    contexts: tuple[ConsoleContext, ...] = ("console",)
    menu_visible: bool = True
    top_level: bool = False


CONSOLE_ACTIONS: tuple[ConsoleAction, ...] = (
    ConsoleAction("status", "Show status", "s", top_level=True),
    ConsoleAction("runs", "Show live runs", "r", top_level=True),
    ConsoleAction("resume", "Resume run", "u", top_level=True),
    ConsoleAction("archive", "Archive run", "a", top_level=True),
    ConsoleAction("start", "Start request", "n", ("new",)),
    ConsoleAction("sdd", "Start full SDD", "f", top_level=True),
    ConsoleAction("explore", "Run explore bundle", "e", top_level=True),
    ConsoleAction("proposal", "Run proposal bundle", "o", top_level=True),
    ConsoleAction("spec", "Run spec bundle", "w", top_level=True),
    ConsoleAction("design", "Run design bundle", "d", top_level=True),
    ConsoleAction("tasks", "Run tasks bundle", "t", top_level=True),
    ConsoleAction("tdd", "Run TDD bundle", "l", top_level=True),
    ConsoleAction("artifacts", "List run artifacts", "v", menu_visible=False, top_level=True),
    ConsoleAction("model", "Select model", "m"),
    ConsoleAction("ci-mode", "Select GitHub CI mode", "g", ("ci", "github-ci")),
    ConsoleAction("jobs", "Show background jobs", "j"),
    ConsoleAction("attach", "Attach job output", "b"),
    ConsoleAction("cancel", "Cancel job", "k"),
    ConsoleAction("install-ci", "Install CI", "c", top_level=True),
    ConsoleAction("install-packages", "Install packages", "p", ("packages",), top_level=True),
    ConsoleAction("exit", "Exit launcher", "x", ("quit",)),
)


def action_names(action: ConsoleAction) -> tuple[str, ...]:
    return (action.name, *action.aliases)


def actions_by_name(actions: tuple[ConsoleAction, ...] = CONSOLE_ACTIONS) -> dict[str, ConsoleAction]:
    return {value.casefold(): action for action in actions for value in action_names(action)}


def visible_actions(
    actions: tuple[ConsoleAction, ...] = CONSOLE_ACTIONS,
    *,
    context: ConsoleContext = "console",
) -> list[ConsoleAction]:
    return [action for action in actions if action.menu_visible and context in action.contexts]


def top_level_action_names(actions: tuple[ConsoleAction, ...] = CONSOLE_ACTIONS) -> set[str]:
    return {action.name for action in actions if action.top_level}
