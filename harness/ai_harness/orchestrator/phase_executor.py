"""PhaseExecutor — central dispatch table for orchestration phases.

Previously the handlers dict was inlined in phase execution.
A named class keeps the full set of supported phases explicit while
Orchestrator delegates to a composed phase execution collaborator.
"""
from __future__ import annotations

from typing import Callable

from ..errors import ValidationError


class PhaseExecutor:
    """Maps phase-name strings to their handler callables and executes them.

    Cheap to instantiate — the work is in the handlers themselves.
    Unknown phases fail closed so graph/dispatcher drift cannot mark work complete.
    """

    def __init__(self, handlers: dict[str, Callable[[], None]]) -> None:
        self._handlers = handlers

    def execute(self, phase: str) -> None:
        try:
            handler = self._handlers[phase]
        except KeyError as exc:
            raise ValidationError(f"unknown phase dispatcher target: {phase}") from exc
        handler()

    def known_phases(self) -> frozenset[str]:
        return frozenset(self._handlers)
