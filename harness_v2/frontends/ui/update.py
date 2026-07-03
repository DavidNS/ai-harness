"""Pure MVU update for the v2 UI: (state, msg) -> (state, effect).

No I/O here. The returned ``Effect`` is the only thing the runtime hands to the
controller. Navigation, selection and drill-down are all decided here as pure
transitions over the model.
"""

from __future__ import annotations

from harness_v2.frontends.ui import messages as m
from harness_v2.frontends.ui.screens import build_items, make_screen
from harness_v2.frontends.ui.state import (
    UiState,
    current_screen,
    home_screen,
    move_selection,
    pop_screen,
    push_screen,
    with_notice,
)

# Commands that finish an action: after them the UI returns to home.
_TERMINAL = {"start", "resume", "cancel", "retry-step", "retry-bundle", "decision"}


def update(state: UiState, msg: m.Msg) -> tuple[UiState, m.Effect]:
    if isinstance(msg, m.Key):
        return _on_key(state, msg.key)
    if isinstance(msg, m.SubmitLine):
        return _on_submit(state, msg.text)
    if isinstance(msg, m.Navigate):
        return push_screen(state, make_screen(msg.screen_id, msg.context)), m.Nothing()
    if isinstance(msg, m.Invoke):
        return _on_invoke(state, msg.command, msg.args)
    if isinstance(msg, m.Back):
        return pop_screen(state), m.Nothing()
    if isinstance(msg, m.Home):
        return home_screen(state), m.Nothing()
    if isinstance(msg, m.Quit):
        raise SystemExit(0)
    return state, m.Nothing()


def _on_key(state: UiState, key: str) -> tuple[UiState, m.Effect]:
    items = build_items(current_screen(state), state)
    if not items:
        if key == "escape":
            return update(state, m.Back())
        return state, m.Nothing()
    if key == "up":
        return move_selection(state, (current_screen(state).selected - 1) % len(items)), m.Nothing()
    if key == "down":
        return move_selection(state, (current_screen(state).selected + 1) % len(items)), m.Nothing()
    if key == "escape":
        return update(state, m.Back())
    if key in {"\r", "\n"}:
        selected = min(current_screen(state).selected, len(items) - 1)
        return update(state, items[selected].msg)
    if key.isdigit() and key != "0" and int(key) <= len(items):
        return update(state, items[int(key) - 1].msg)
    return state, m.Nothing()


def _on_submit(state: UiState, text: str) -> tuple[UiState, m.Effect]:
    screen = current_screen(state)
    if not text.strip():
        return with_notice(pop_screen(state), "cancelled"), m.Nothing()
    if screen.screen_id == "start-request" and screen.context:
        return _on_invoke(state, "start", (screen.context[0], text))
    if screen.screen_id == "decision-input":
        return _on_invoke(state, "decision", (text,))
    return state, m.Nothing()


def _on_invoke(state: UiState, command: str, args: tuple[str, ...]) -> tuple[UiState, m.Effect]:
    effect = _effect_for(command, args)
    if effect is None:
        return state, m.Nothing()
    if command == "select":
        return push_screen(state, make_screen("actions")), effect
    if command in _TERMINAL:
        return home_screen(state), effect
    return state, effect


def _effect_for(command: str, args: tuple[str, ...]) -> m.Effect | None:
    if command == "select" and len(args) == 1:
        return m.Select(args[0])
    if command == "start" and len(args) == 2:
        return m.Start(args[0], args[1])
    if command == "resume":
        return m.Resume()
    if command == "cancel":
        return m.Cancel()
    if command == "retry-step" and len(args) == 1:
        return m.RetryStep(args[0])
    if command == "retry-bundle" and len(args) == 1:
        return m.RetryBundle(args[0])
    if command == "decision" and len(args) == 1:
        return m.Decision(args[0])
    if command == "refresh":
        return m.Refresh()
    if command == "watch":
        return m.Watch(float(args[0]) if args else 1.0)
    return None
