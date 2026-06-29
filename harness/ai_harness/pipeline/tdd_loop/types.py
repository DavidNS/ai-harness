"""Public data types for the TDD loop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from ...errors import ValidationError
from ...models import Task, TaskStatus

Command = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaskPlan:
    """Controller inputs for one task; commands are argument vectors, never shells."""

    id: str
    focused_tests: tuple[Command, ...]
    broader_tests: tuple[Command, ...] = ()
    allowed_paths: tuple[str, ...] = (".",)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValidationError("task plan ID is required")
        if not self.focused_tests:
            raise ValidationError("a focused test command is required")
        for command in self.focused_tests + self.broader_tests:
            if not command or any(not isinstance(argument, str) or not argument for argument in command):
                raise ValidationError("test commands must be nonempty argument vectors")
        if not self.allowed_paths or any(not isinstance(path, str) or not path for path in self.allowed_paths):
            raise ValidationError("allowed paths must be nonempty strings")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "TaskPlan":
        def commands(name: str) -> tuple[Command, ...]:
            raw = value.get(name, ())
            if not isinstance(raw, (list, tuple)):
                raise ValidationError(f"{name} must be a list of commands")
            return tuple(tuple(command) if isinstance(command, (list, tuple)) else () for command in raw)

        raw_paths = value.get("touched_paths", (".",))
        if not isinstance(raw_paths, (list, tuple)):
            raise ValidationError("touched_paths must be a list")
        return cls(str(value.get("id", "")), commands("focused_tests"), commands("broader_tests"),
                   tuple(raw_paths))


@dataclass(frozen=True, slots=True)
class ImplementationOutcome:
    changed_paths: tuple[str, ...]
    summary: str = ""
    exit_code: int | None = 0
    stderr: str = ""
    repository_diff: str = ""

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True, slots=True)
class CommandEvidence:
    argv: Command
    stdout: str
    stderr: str
    exit_code: int | None
    duration_seconds: float
    timed_out: bool = False
    missing: bool = False

    @property
    def passed(self) -> bool:
        return not self.timed_out and not self.missing and self.exit_code == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "argv": list(self.argv), "stdout": self.stdout, "stderr": self.stderr,
            "exit_code": self.exit_code, "duration_seconds": self.duration_seconds,
            "timed_out": self.timed_out, "missing": self.missing, "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class LoopResult:
    task_id: str
    status: TaskStatus
    attempts: int
    failure: str | None = None


ImplementWorker = Callable[[Task, int, tuple[str, ...]], ImplementationOutcome]
ReviewWorker = Callable[[Task, ImplementationOutcome, tuple[CommandEvidence, ...]], str]
CommandRunner = Callable[[Command, Path, float], CommandEvidence]
