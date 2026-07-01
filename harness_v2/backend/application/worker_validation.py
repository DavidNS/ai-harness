"""Worker output validation boundary for phase orchestration."""

from __future__ import annotations

from dataclasses import dataclass


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _error_tuple(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = tuple(_require_text(value, "validation error") for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError("validation errors must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class WorkerOutputValidationResult:
    """Semantic validation result produced after raw provider output is captured."""

    valid: bool
    schema_name: str
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.valid, bool):
            raise TypeError("valid must be bool")
        object.__setattr__(self, "schema_name", _require_text(self.schema_name, "schema_name"))
        object.__setattr__(self, "errors", _error_tuple(self.errors))
        if self.valid and self.errors:
            raise ValueError("valid worker output cannot have validation errors")
        if not self.valid and not self.errors:
            raise ValueError("invalid worker output requires at least one validation error")


def require_valid_worker_output(result: WorkerOutputValidationResult) -> None:
    """Fail closed before phase advancement when worker output has not validated."""

    if not isinstance(result, WorkerOutputValidationResult):
        raise TypeError("result must be WorkerOutputValidationResult")
    if not result.valid:
        raise ValueError("worker output is invalid: " + "; ".join(result.errors))
