"""User intents for the console model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubmitLine:
    line: str


@dataclass(frozen=True, slots=True)
class SelectAction:
    value: str


@dataclass(frozen=True, slots=True)
class MoveSelection:
    delta: int


@dataclass(frozen=True, slots=True)
class SetStatus:
    code: int


@dataclass(frozen=True, slots=True)
class ShowError:
    message: str


@dataclass(frozen=True, slots=True)
class ExitRequested:
    pass


ConsoleMessage = SubmitLine | SelectAction | MoveSelection | SetStatus | ShowError | ExitRequested

