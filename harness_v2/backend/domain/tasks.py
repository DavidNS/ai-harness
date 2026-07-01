"""Task summary domain objects for v2 runs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from harness_v2.backend.domain.errors import DomainValidationError, require_text


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
    attempts: int = 0
    last_failure: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", require_text(self.task_id, "task ID"))
        object.__setattr__(self, "title", require_text(self.title, "task title"))
        object.__setattr__(self, "status", TaskStatus(self.status))
        if isinstance(self.attempts, bool) or self.attempts < 0:
            raise DomainValidationError("task attempts must be a non-negative integer")
        if self.last_failure is not None:
            object.__setattr__(self, "last_failure", require_text(self.last_failure, "task last failure"))

    def replace(self, **changes: object) -> "TaskSummary":
        data = {
            "task_id": self.task_id,
            "title": self.title,
            "status": self.status,
            "attempts": self.attempts,
            "last_failure": self.last_failure,
        }
        data.update(changes)
        return TaskSummary(**data)
