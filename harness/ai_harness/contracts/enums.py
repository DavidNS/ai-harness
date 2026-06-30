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
    EXPLORE_BUNDLE = "EXPLORE_BUNDLE"
    PROPOSAL_BUNDLE = "PROPOSAL_BUNDLE"
    SPEC_BUNDLE = "SPEC_BUNDLE"
    DESIGN_BUNDLE = "DESIGN_BUNDLE"
    TASKS_BUNDLE = "TASKS_BUNDLE"
    TDD_BUNDLE = "TDD_BUNDLE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
