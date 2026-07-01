"""Effects emitted by the pure console update function."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


EffectKind = Literal[
    "open_menu",
    "dispatch_action",
    "start_request",
    "exit",
]


@dataclass(frozen=True, slots=True)
class ConsoleEffect:
    kind: EffectKind
    value: str = ""
    args: tuple[str, ...] = ()
    raw_tail: str = ""


def open_menu() -> ConsoleEffect:
    return ConsoleEffect("open_menu")


def dispatch_action(name: str, args: tuple[str, ...] = (), *, raw_tail: str = "") -> ConsoleEffect:
    return ConsoleEffect("dispatch_action", name, args, raw_tail)


def start_request(request: str) -> ConsoleEffect:
    return ConsoleEffect("start_request", request)


def exit_console() -> ConsoleEffect:
    return ConsoleEffect("exit")
