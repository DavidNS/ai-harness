"""Terminal driver for the console MVU core."""

from __future__ import annotations

import sys
from collections.abc import Callable

from ..ui_primitives import _MenuItem
from .backend_port import ConsoleBackendPort
from .effects import ConsoleEffect
from .messages import SelectAction, SetStatus, SubmitLine
from .model import ConsoleModel
from .update import update
from .view import menu_items, menu_title_lines


LineReader = Callable[[], str | None]
MenuPrompt = Callable[..., _MenuItem]
LauncherExit = type[BaseException]


class ConsoleTerminalDriver:
    def __init__(
        self,
        model: ConsoleModel,
        backend: ConsoleBackendPort,
        *,
        line_reader: LineReader,
        menu_prompt: MenuPrompt,
        launcher_exit: LauncherExit,
    ) -> None:
        self.model = model
        self.backend = backend
        self.line_reader = line_reader
        self.menu_prompt = menu_prompt
        self.launcher_exit = launcher_exit

    def run_once(self, line: str) -> int:
        self.model, effects = update(self.model, SubmitLine(line))
        return self._run_effects(effects)

    def loop(self, startup: Callable[[], int | None] | None = None) -> int:
        print("AI Code Harness console. Press Enter for actions or type a request.", file=sys.stderr)
        last_status = 0
        if startup is not None:
            recovered = startup()
            if recovered is not None:
                last_status = recovered
        while True:
            line = self.line_reader()
            if line is None:
                print(file=sys.stderr)
                return last_status
            try:
                last_status = self.run_once(line)
                self.model, _ = update(self.model, SetStatus(last_status))
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                last_status = 1
            except self.launcher_exit:
                return 0

    def _run_effects(self, effects: tuple[ConsoleEffect, ...]) -> int:
        status = self.model.last_status
        for effect in effects:
            if effect.kind == "exit":
                raise self.launcher_exit
            if effect.kind == "open_menu":
                choices = [_MenuItem(item.key, item.label, item.value, item.aliases) for item in menu_items(self.model)]
                selected = self.menu_prompt(menu_title_lines(self.model), choices, help_kind="console").value
                self.model, followup = update(self.model, SelectAction(selected))
                status = self._run_effects(followup)
                continue
            if effect.kind == "dispatch_action":
                status = self.backend.dispatch_action(effect.value, effect.args, effect.raw_tail)
                continue
            if effect.kind == "start_request":
                status = self.backend.start_request(effect.value)
        return status

