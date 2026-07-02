"""Shared TDD phase helpers."""

from __future__ import annotations

from harness_v2.backend.domain.tasks import TaskSummary


def _task_mapping(task: TaskSummary) -> dict[str, object]:
    return {"task_id": task.task_id, "title": task.title, "status": task.status.value, "attempts": task.attempts, "last_failure": task.last_failure}
