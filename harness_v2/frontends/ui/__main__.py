"""Interactive terminal UI for AI Harness v2 daemon-backed runs."""

from __future__ import annotations

import argparse
import shlex
from collections.abc import Sequence

from harness_v2.hosts.daemon.client import DaemonClient
from harness_v2.frontends.ui.controller import UiController
from harness_v2.frontends.ui.renderer import render
from harness_v2.frontends.ui.state import UiState, with_error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AI Harness v2 terminal UI")
    parser.add_argument("--daemon-url", default="http://127.0.0.1:8765")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    controller = UiController(DaemonClient(args.daemon_url))
    state = controller.refresh(UiState())
    print(render(state), end="")
    while True:
        try:
            raw = input("ui> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not raw:
            continue
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            state = with_error(state, str(exc))
            print(render(state), end="")
            continue
        if parts[0] in {"quit", "exit"}:
            return 0
        state = _dispatch(controller, state, parts)
        print(render(state), end="")


def _dispatch(controller: UiController, state: UiState, parts: list[str]) -> UiState:
    command = parts[0]
    if command in {"refresh", "list"}:
        return controller.refresh(state)
    if command == "select" and len(parts) == 2:
        return controller.select(state, parts[1])
    if command == "start" and len(parts) >= 3:
        return controller.start(state, " ".join(parts[2:]), root_bundle=parts[1])
    if command == "resume" and len(parts) == 1:
        return controller.resume(state)
    if command == "cancel" and len(parts) == 1:
        return controller.cancel(state)
    if command == "retry" and len(parts) == 2:
        return controller.retry(state, parts[1])
    if command == "decision" and len(parts) >= 2:
        return controller.submit_decision(state, " ".join(parts[1:]))
    if command == "watch":
        timeout = float(parts[1]) if len(parts) == 2 else 1.0
        return controller.refresh(controller.poll_events(state, timeout=timeout))
    return with_error(
        state,
        "commands: refresh, list, select <run_id>, start <root_bundle> <request>, "
        "resume, cancel, retry <phase>, decision <response>, watch [timeout], quit",
    )


if __name__ == "__main__":
    raise SystemExit(main())
