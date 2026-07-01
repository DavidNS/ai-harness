"""Run domain objects for the v2 walking skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    request: str
    status: RunStatus
    current_phase: str | None = None
    completed_phases: tuple[str, ...] = ()
    events: tuple[Any, ...] = ()

    def with_events(self, events: tuple[Any, ...]) -> "RunRecord":
        return RunRecord(
            run_id=self.run_id,
            request=self.request,
            status=self.status,
            current_phase=self.current_phase,
            completed_phases=self.completed_phases,
            events=events,
        )

