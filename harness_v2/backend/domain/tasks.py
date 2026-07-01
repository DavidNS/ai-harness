"""Task summary domain objects for v2 runs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from harness_v2.backend.domain.errors import require_text


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class TaskSummary:
    task_id: str
    title: str
    status: TaskStatus = TaskStatus.PENDING

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", require_text(self.task_id, "task ID"))
        object.__setattr__(self, "title", require_text(self.title, "task title"))
        object.__setattr__(self, "status", TaskStatus(self.status))
