"""Harness exception hierarchy."""

from __future__ import annotations


class HarnessError(Exception):
    """Base exception for controlled harness failures."""


class ProviderPhaseError(HarnessError):
    """A bounded provider invocation failed while producing a phase artifact."""

    def __init__(
        self,
        phase: str,
        reason: str,
        *,
        stdout: str = "",
        stderr: str = "",
        truncated: bool = False,
    ) -> None:
        super().__init__(f"phase {phase} provider {reason}")
        self.phase = phase
        self.reason = reason
        self.stdout = stdout
        self.stderr = stderr
        self.truncated = truncated

    @property
    def diagnostic(self) -> str:
        parts = []
        if self.stderr:
            parts.append(self.stderr)
        if self.stdout:
            parts.append(self.stdout)
        if not parts:
            parts.append(str(self))
        if self.truncated:
            parts.append("[provider output truncated]")
        return "\n".join(parts)


class ConfigurationError(HarnessError):
    pass


class ValidationError(HarnessError):
    pass


class TransitionError(ValidationError):
    pass


class ArtifactError(HarnessError):
    pass


class StateError(HarnessError):
    pass


class LockError(HarnessError):
    pass


class KnowledgeError(HarnessError):
    pass
