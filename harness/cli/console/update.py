"""Pure Model-View-Update transitions for the console."""

from __future__ import annotations

import shlex
from dataclasses import replace

from .effects import ConsoleEffect, dispatch_action, exit_console, open_menu, start_request
from .messages import ConsoleMessage, ExitRequested, MoveSelection, SelectAction, SetStatus, ShowError, SubmitLine
from .model import ConsoleActionSpec, ConsoleModel


def update(model: ConsoleModel, message: ConsoleMessage) -> tuple[ConsoleModel, tuple[ConsoleEffect, ...]]:
    if isinstance(message, SubmitLine):
        return _submit_line(model, message.line)
    if isinstance(message, SelectAction):
        return _select_action(model, message.value)
    if isinstance(message, MoveSelection):
        visible = model.visible_actions
        if not visible:
            return model, ()
        return replace(model, selected_index=(model.selected_index + message.delta) % len(visible)), ()
    if isinstance(message, SetStatus):
        return replace(model, last_status=message.code, screen="prompt", message=None), ()
    if isinstance(message, ShowError):
        return replace(model, screen="prompt", errors=(*model.errors, message.message)), ()
    if isinstance(message, ExitRequested):
        return replace(model, screen="exiting"), (exit_console(),)
    return model, ()


def _submit_line(model: ConsoleModel, line: str) -> tuple[ConsoleModel, tuple[ConsoleEffect, ...]]:
    raw = line.strip()
    if not raw:
        return replace(model, screen="menu", selected_index=0, message=None), (open_menu(),)
    if raw.casefold() in {"exit", "quit"}:
        return replace(model, screen="exiting"), (exit_console(),)
    parts = _split_command(raw)
    if parts:
        action = _find_action(model.actions, parts[0], include_keys=False)
        if action is not None:
            raw_tail = _raw_tail(raw, parts[0])
            return replace(model, screen="prompt", message=None), (dispatch_action(action.name, tuple(parts[1:]), raw_tail=raw_tail),)
    return replace(model, screen="prompt", message=None), (start_request(raw),)


def _select_action(model: ConsoleModel, value: str) -> tuple[ConsoleModel, tuple[ConsoleEffect, ...]]:
    action = _find_action(model.actions, value, include_keys=True)
    if action is None:
        return replace(model, screen="prompt", errors=(*model.errors, f"Unknown console action: {value}")), ()
    if action.name in {"exit", "quit"}:
        return replace(model, screen="exiting"), (exit_console(),)
    return replace(model, screen="prompt", message=None), (dispatch_action(action.name),)


def _split_command(raw: str) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(raw))
    except ValueError:
        return ()


def _raw_tail(raw: str, command: str) -> str:
    remainder = raw[len(command):]
    return remainder.lstrip()


def _find_action(actions: tuple[ConsoleActionSpec, ...], value: str, *, include_keys: bool) -> ConsoleActionSpec | None:
    selected = value.strip().casefold()
    if not selected:
        return None
    for action in actions:
        names = (action.name, *action.shortcuts)
        if include_keys:
            names = (action.name, action.key, *action.shortcuts)
        if selected in {name.casefold() for name in names}:
            return action
    return None

