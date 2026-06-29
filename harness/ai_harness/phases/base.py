"""Compatibility exports for phase contracts."""

from __future__ import annotations

from ..explorer_contracts import (
    validate_explorer_artifact,
    validate_explorer_decision,
    validate_explorer_discovery,
    validate_explorer_intake,
    validate_explorer_review,
)
from .errors import PhaseRepairExhaustedError, PhaseValidationError
from .registry import PHASE_DEFINITIONS, get_phase
from .types import PhaseDefinition, Validator
from .validators.explore import (
    validate_explore_ci_barrier,
    validate_explore_clarification_gate,
    validate_explore_evidence_collection,
    validate_explore_evidence_normalization,
    validate_explore_evidence_plan,
    validate_explore_outcome_bundle,
    validate_explore_request_understanding,
    validate_explore_review as validate_sdd_explore_review,
    validate_explore_triage,
)
from .validators.explorer import (
    validate_compact_improvement,
    validate_explorer,
    validate_explorer_distill,
)
from .validators.knowledge import validate_knowledge_review, validate_learning
from .validators.review import validate_review
from .validators.tasks import validate_tasks

__all__ = [
    "PHASE_DEFINITIONS",
    "PhaseDefinition",
    "PhaseRepairExhaustedError",
    "PhaseValidationError",
    "Validator",
    "get_phase",
    "validate_explore_ci_barrier",
    "validate_explore_clarification_gate",
    "validate_explore_evidence_collection",
    "validate_explore_evidence_normalization",
    "validate_explore_evidence_plan",
    "validate_explore_outcome_bundle",
    "validate_explore_request_understanding",
    "validate_explore_triage",
    "validate_sdd_explore_review",
    "validate_compact_improvement",
    "validate_explorer",
    "validate_explorer_artifact",
    "validate_explorer_decision",
    "validate_explorer_discovery",
    "validate_explorer_intake",
    "validate_explorer_review",
    "validate_explorer_distill",
    "validate_knowledge_review",
    "validate_learning",
    "validate_review",
    "validate_tasks",
]
