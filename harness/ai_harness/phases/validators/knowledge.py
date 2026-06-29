"""Knowledge source phase validators."""

from __future__ import annotations

from ...knowledge_source import (
    KnowledgeSourceError,
    parse_knowledge_review,
    parse_learning_proposal,
)
from ..errors import PhaseValidationError


def validate_learning(candidate: str) -> str:
    if not isinstance(candidate, str) or not candidate.strip():
        raise PhaseValidationError("phase output must be nonempty JSON")
    try:
        parse_learning_proposal(candidate)
    except KnowledgeSourceError as exc:
        raise PhaseValidationError(str(exc)) from exc
    return candidate


def validate_knowledge_review(candidate: str) -> str:
    if not isinstance(candidate, str) or not candidate.strip():
        raise PhaseValidationError("phase output must be nonempty JSON")
    try:
        parse_knowledge_review(candidate)
    except KnowledgeSourceError as exc:
        raise PhaseValidationError(str(exc)) from exc
    return candidate
