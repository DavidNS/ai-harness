"""Worker prompt resource port for v2 application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from harness_v2.backend.ports.model_provider import CapabilityProjection


class WorkerResourceError(RuntimeError):
    """Base error for worker prompt resource failures."""


class WorkerResourceNotFoundError(WorkerResourceError):
    """Raised when a worker resource file cannot be found."""


class WorkerResourceValidationError(WorkerResourceError, ValueError):
    """Raised when worker prompt resources are malformed."""


def require_task_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerResourceValidationError("task_id is required")
    normalized = value.strip()
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        raise WorkerResourceValidationError("task_id must be a single safe path segment")
    return normalized


def require_markdown(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerResourceValidationError(f"{field} must be nonempty markdown")
    return value.strip() + "\n"


@dataclass(frozen=True, slots=True)
class WorkerResourceSpec:
    task_id: str
    playbook_markdown: str
    prompt_markdown: str
    capabilities: CapabilityProjection

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", require_task_id(self.task_id))
        object.__setattr__(self, "playbook_markdown", require_markdown(self.playbook_markdown, "playbook_markdown"))
        object.__setattr__(self, "prompt_markdown", require_markdown(self.prompt_markdown, "prompt_markdown"))
        if not isinstance(self.capabilities, CapabilityProjection):
            raise TypeError("capabilities must be CapabilityProjection")


class WorkerResourcePort(Protocol):
    """Loads prompt material and capabilities for one worker task."""

    def get(self, task_id: str) -> WorkerResourceSpec: ...
