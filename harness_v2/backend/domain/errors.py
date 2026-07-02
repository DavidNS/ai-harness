"""Domain errors for v2 lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass


class DomainValidationError(ValueError):
    """Raised when domain state violates an invariant."""


class InvalidTransitionError(DomainValidationError):
    """Raised when a lifecycle transition is not allowed."""


def require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field} is required")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    code: str
    message: str
    bundle: str | None = None
    phase: str | None = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", require_text(self.code, "error code"))
        object.__setattr__(self, "message", require_text(self.message, "error message"))
        if self.bundle is not None:
            object.__setattr__(self, "bundle", require_text(self.bundle, "error bundle"))
        if self.phase is not None:
            object.__setattr__(self, "phase", require_text(self.phase, "error phase"))
        object.__setattr__(self, "timestamp", require_text(self.timestamp, "error timestamp"))
