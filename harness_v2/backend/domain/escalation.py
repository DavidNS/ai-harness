"""Escalation domain objects for v2 lifecycle recovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from harness_v2.backend.domain.errors import DomainValidationError, require_text
from harness_v2.backend.domain.lifecycle import PhaseName


class EscalationCategory(StrEnum):
    USER_CLARIFICATION = "USER_CLARIFICATION"
    EXPLORATION_GAP = "EXPLORATION_GAP"
    REQUIREMENTS_GAP = "REQUIREMENTS_GAP"
    DESIGN_GAP = "DESIGN_GAP"
    TASK_PLAN_GAP = "TASK_PLAN_GAP"
    IMPLEMENTATION_BLOCKED = "IMPLEMENTATION_BLOCKED"
    VALIDATION_BLOCKED = "VALIDATION_BLOCKED"
    CONTRACT_INVALID = "CONTRACT_INVALID"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


def _text_tuple(values: tuple[str, ...] | list[str], field: str) -> tuple[str, ...]:
    normalized = tuple(require_text(value, field) for value in values)
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError(f"{field} must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class EscalationIssue:
    issue_id: str
    origin_phase: PhaseName
    category: EscalationCategory
    reason: str
    evidence_artifact_ids: tuple[str, ...] = ()
    decision_id: str | None = None
    response: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "issue_id", require_text(self.issue_id, "escalation issue ID"))
        object.__setattr__(self, "origin_phase", PhaseName(self.origin_phase))
        object.__setattr__(self, "category", EscalationCategory(self.category))
        object.__setattr__(self, "reason", require_text(self.reason, "escalation reason"))
        object.__setattr__(self, "evidence_artifact_ids", _text_tuple(self.evidence_artifact_ids, "evidence artifact ID"))
        if self.decision_id is not None:
            object.__setattr__(self, "decision_id", require_text(self.decision_id, "decision ID"))
        if self.response is not None:
            object.__setattr__(self, "response", require_text(self.response, "decision response"))
