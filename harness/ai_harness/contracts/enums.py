"""StrEnum contracts for artifact kinds, bundle actions, and phase names.

Members compare equal to their string values, so call-sites can be migrated
incrementally — replacing a literal "improvement" with ArtifactKind.IMPROVEMENT
is a no-op at runtime.
"""
from __future__ import annotations

from enum import StrEnum


class ArtifactKind(StrEnum):
    """Artifact kinds produced by the explorer pipeline."""
    IMPROVEMENT = "improvement"
    LIMITATION = "limitation"
    BULLSHIT = "bullshit"
    EXISTING_FUNCTIONALITY = "existing-functionality"
    DOCUMENTATION = "documentation"


class BundleAction(StrEnum):
    """Actions an ExplorerBundleEntry can carry."""
    CREATE = "create"
    UPDATE = "update"
    NO_OP = "no-op"
    DOCUMENTATION_TASK = "documentation_task"
    LIMITATION = "limitation"
    EXISTING_FUNCTIONALITY = "existing_functionality"


class PhaseName(StrEnum):
    """Every phase string used across all strategy graphs.

    Values equal the strings in GRAPHS tuples, so replacing a literal
    ``"EXPLORE"`` with ``PhaseName.EXPLORE`` is a runtime no-op.
    """
    # Shared lifecycle phases (all graphs)
    INITIALIZING = "INITIALIZING"
    LOADING_KNOWLEDGE = "LOADING_KNOWLEDGE"
    DETECTING_INTENT = "DETECTING_INTENT"
    ROUTING = "ROUTING"
    SELECTING_STRATEGY = "SELECTING_STRATEGY"
    FINALIZING = "FINALIZING"
    SNAPSHOTTING = "SNAPSHOTTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    # Full-SDD graph phases
    EXPLORE = "EXPLORE"
    PURPOSE = "PURPOSE"
    SPEC = "SPEC"
    DESIGN = "DESIGN"
    TASKS = "TASKS"
    TDD_LOOP = "TDD_LOOP"
    LEARNING = "LEARNING"
    # Simple-implementation graph phases
    SIMPLE_TASK = "SIMPLE_TASK"
    # Non-code graph phases
    NON_CODE_STUB = "NON_CODE_STUB"
    # Explorer graph phases
    EXPLORER = "EXPLORER"
    EXPLORER_INTAKE = "EXPLORER_INTAKE"
    EXPLORER_DISCOVERY = "EXPLORER_DISCOVERY"
    EXPLORER_DECISION = "EXPLORER_DECISION"
    EXPLORER_ARTIFACT = "EXPLORER_ARTIFACT"
    EXPLORER_REVIEW = "EXPLORER_REVIEW"
