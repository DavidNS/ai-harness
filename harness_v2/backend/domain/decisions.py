"""User decision domain objects for v2 runs."""

from __future__ import annotations

from dataclasses import dataclass

from harness_v2.backend.domain.errors import DomainValidationError, require_text
from harness_v2.backend.domain.lifecycle import PhaseName


def _normalize_options(options: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = tuple(require_text(option, "decision option") for option in options)
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError("decision options must be unique")
    return normalized


@dataclass(frozen=True, slots=True)
class PendingDecision:
    decision_id: str
    origin_phase: PhaseName
    prompt: str
    created_at: str
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", require_text(self.decision_id, "decision ID"))
        object.__setattr__(self, "origin_phase", PhaseName(self.origin_phase))
        object.__setattr__(self, "prompt", require_text(self.prompt, "decision prompt"))
        object.__setattr__(self, "options", _normalize_options(self.options))
        object.__setattr__(self, "created_at", require_text(self.created_at, "decision timestamp"))


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    decision_id: str
    origin_phase: PhaseName
    prompt: str
    response: str
    created_at: str
    answered_at: str
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", require_text(self.decision_id, "decision ID"))
        object.__setattr__(self, "origin_phase", PhaseName(self.origin_phase))
        object.__setattr__(self, "prompt", require_text(self.prompt, "decision prompt"))
        object.__setattr__(self, "response", require_text(self.response, "decision response"))
        object.__setattr__(self, "created_at", require_text(self.created_at, "decision timestamp"))
        object.__setattr__(self, "answered_at", require_text(self.answered_at, "decision answer timestamp"))
        object.__setattr__(self, "options", _normalize_options(self.options))
