"""Pure console UI state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ConsoleScreen = Literal["prompt", "menu", "exiting"]


@dataclass(frozen=True, slots=True)
class ConsoleChoice:
    key: str
    label: str
    value: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConsoleActionSpec:
    name: str
    label: str
    key: str
    shortcuts: tuple[str, ...] = ()
    menu_visible: bool = True


@dataclass(frozen=True, slots=True)
class ConsoleModel:
    screen: ConsoleScreen = "prompt"
    prompt: str = "aihui> "
    actions: tuple[ConsoleActionSpec, ...] = ()
    selected_index: int = 0
    last_status: int = 0
    message: str | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def visible_actions(self) -> tuple[ConsoleActionSpec, ...]:
        return tuple(action for action in self.actions if action.menu_visible)

