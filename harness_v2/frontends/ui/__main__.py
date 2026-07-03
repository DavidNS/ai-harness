"""MVU runtime for the AI Harness v2 terminal UI.

The loop is thin: read input into a ``Msg``, fold it with the pure ``update`` to
get ``(state, effect)``, run the effect through ``perform`` (the only I/O), then
render. All menu content, navigation and drill-down live in the pure layer
(``screens``/``update``); this file only does terminal I/O.
"""

from __future__ import annotations

import argparse
import termios
from collections.abc import Sequence

from harness_v2.hosts.daemon.client import DaemonClient
from harness_v2.frontends.ui import messages as m
from harness_v2.frontends.ui.controller import UiController
from harness_v2.frontends.ui.dispatch import COMMAND_HELP, CommandError, parse_command
from harness_v2.frontends.ui.effects import perform
from harness_v2.frontends.ui.renderer import render, render_screen
from harness_v2.frontends.ui.state import (
    HOME,
    UiState,
    current_screen,
    push_screen,
    with_error,
    with_notice,
)
from harness_v2.frontends.ui.screens import make_screen
from harness_v2.frontends.ui.terminal import KeyReader, PromptRenderer, RawTerminal, TerminalIO
from harness_v2.frontends.ui.update import update


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AI Harness v2 terminal UI")
    parser.add_argument("--daemon-url", default="http://127.0.0.1:8765")
    parser.add_argument("--no-menu", action="store_true", help="ignored; kept for compatibility")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    controller = UiController(DaemonClient(args.daemon_url))
    state = controller.refresh(UiState())
    print(render(state), end="")
    while True:
        try:
            screen = current_screen(state)
            if screen.kind == "prompt":
                state = _prompt_step(controller, state)
            elif screen.kind == "input":
                state = _input_step(controller, state)
            else:
                state = _menu_step(controller, state)
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        except SystemExit as exc:
            return int(exc.code)
        print(render(state), end="")


# --- prompt (home) -------------------------------------------------------------


def _prompt_step(controller: UiController, state: UiState) -> UiState:
    while True:
        raw = input("ui> ")
        if raw.strip():
            return _handle_line(controller, state, raw)


def _handle_line(controller: UiController, state: UiState, raw: str) -> UiState:
    if raw.startswith("/"):
        try:
            msg = parse_command(raw)
        except CommandError as exc:
            return with_error(state, str(exc))
        if msg is None:
            return with_notice(state, COMMAND_HELP)
        return _run(controller, state, msg)
    if _decision_available(state):
        return _run(controller, state, m.Invoke("decision", (raw,)))
    return with_notice(state, COMMAND_HELP)


# --- input (text capture) ------------------------------------------------------


def _input_step(controller: UiController, state: UiState) -> UiState:
    title = render_screen(state).splitlines()[0]
    line = input(title if title.endswith(("> ", ": ")) else f"{title}\n> ")
    return _run(controller, state, m.SubmitLine(line))


# --- menu (arrow-key or numbered) ----------------------------------------------


def _menu_step(controller: UiController, state: UiState) -> UiState:
    terminal = TerminalIO()
    if terminal.interactive:
        try:
            return _menu_step_keys(controller, state, terminal)
        except (termios.error, OSError):
            pass
    return _menu_step_line(controller, state)


def _menu_step_keys(controller: UiController, state: UiState, terminal: TerminalIO) -> UiState:
    renderer = PromptRenderer(terminal)
    reader = KeyReader()
    with RawTerminal():
        while True:
            key = reader.read_key()
            if not key:
                raise EOFError
            if key == "/":
                break
            new_state, effect = update(state, m.Key(key))
            if not isinstance(effect, m.Nothing):
                return perform(effect, controller, new_state)
            if new_state.nav != state.nav:
                # selection moved or a screen was pushed/popped with no effect
                if _same_screen_moved(state, new_state):
                    _redraw_screen(renderer, state, new_state)
                    state = new_state
                    continue
                return new_state
    # dropped out of raw mode to take a one-shot command
    return _one_shot_command(controller, state)


def _same_screen_moved(old: UiState, new: UiState) -> bool:
    return (
        len(old.nav) == len(new.nav)
        and current_screen(old).screen_id == current_screen(new).screen_id
    )


def _menu_step_line(controller: UiController, state: UiState) -> UiState:
    line = input("menu> ").strip()
    if line.startswith("/"):
        return _handle_line(controller, state, line)
    if line in {"b", "back"}:
        return _run(controller, state, m.Back())
    if line.isdigit():
        return _run(controller, state, m.Key(line))
    return with_notice(state, "enter an item number, 'b' for back, or /command")


def _one_shot_command(controller: UiController, state: UiState) -> UiState:
    raw = input("ui> /")
    if not raw.strip():
        return state
    return _handle_line(controller, state, "/" + raw)


# --- helpers -------------------------------------------------------------------


def _run(controller: UiController, state: UiState, msg: m.Msg) -> UiState:
    new_state, effect = update(state, msg)
    return perform(effect, controller, new_state)


def _redraw_screen(renderer: PromptRenderer, old: UiState, new: UiState) -> None:
    rows = sum(renderer.rows_for(line) for line in render_screen(old).splitlines())
    renderer.clear_previous(rows)
    for line in render_screen(new).splitlines():
        renderer.clear_line(line)


def _decision_available(state: UiState) -> bool:
    run = state.selected_run
    return run is not None and run.pending_decision is not None


if __name__ == "__main__":
    raise SystemExit(main())
