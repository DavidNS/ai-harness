"""Semantic rendering for the console model."""

from __future__ import annotations

from .model import ConsoleActionSpec, ConsoleChoice, ConsoleModel


def menu_title_lines(_model: ConsoleModel) -> list[str]:
    return ["Console actions"]


def menu_items(model: ConsoleModel) -> list[ConsoleChoice]:
    return [
        ConsoleChoice(action.key, action.label, action.name, (action.name, *action.shortcuts))
        for action in model.visible_actions
    ]


def help_lines(model: ConsoleModel) -> list[str]:
    lines = [
        "Controls:",
        "  Press Enter on an empty line to open the action menu",
        "  Type an action name to run it",
        "  Type any other text to start a harness run",
        "  Type exit or press Ctrl-D to leave the console",
    ]
    for action in model.visible_actions:
        aliases = ", ".join(action.shortcuts)
        suffix = f" ({aliases})" if aliases else ""
        lines.append(f"  {action.name}: {action.label}{suffix}")
    return lines


def render_lines(model: ConsoleModel) -> list[str]:
    lines: list[str] = []
    if model.message:
        lines.append(model.message)
    lines.extend(model.errors)
    if model.screen == "menu":
        lines.extend(menu_title_lines(model))
        for index, action in enumerate(model.visible_actions, 1):
            marker = ">" if index - 1 == model.selected_index else " "
            lines.append(f"{marker} {index}. {action.label}")
        lines.append("Use Up/Down, Enter, number keys, or Ctrl-C.")
        return lines
    if model.screen == "exiting":
        lines.append("Exiting console.")
        return lines
    lines.append(model.prompt)
    return lines


def action_names(actions: tuple[ConsoleActionSpec, ...]) -> set[str]:
    return {action.name for action in actions}
