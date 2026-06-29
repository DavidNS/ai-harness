"""Numeric limits and thresholds used across the orchestrator.

Previously scattered across explorer_flow.py, analysis_quality.py,
phase_execution.py, and explorer_scope.py with duplicated values.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LearningLimits:
    """Byte limits that govern the learning / knowledge-synthesis pipeline."""
    artifact: int = 12_000
    context: int = 60_000
    # Maximum bytes of a rejected proposal excerpt kept for repair prompts.
    # Formerly LEARNING_REJECTED_LIMIT (explorer_flow.py + analysis_quality.py)
    # and PHASE_REPAIR_REJECTED_LIMIT (phase_execution.py) — all were 4_000.
    rejected: int = 4_000


@dataclass(frozen=True)
class RepositorySnapshotLimits:
    """Limits on the repository snapshot passed to learning workers."""
    max_files: int = 16
    max_bytes: int = 24_000
    max_file_bytes: int = 80_000


@dataclass(frozen=True)
class RepositoryObservationLimits:
    """Limits on repository observations passed to explorer workers."""
    suffixes: frozenset[str] = frozenset({".md", ".py", ".json", ".toml", ".yaml", ".yml"})


@dataclass(frozen=True)
class ExplorerScopeLimits:
    """Limits on the explorer scope resolver."""
    max_artifacts: int = 25
    artifact_bytes: int = 50_000
    total_bytes: int = 250_000


# Singleton instances — import these rather than instantiating per-call.
LEARNING = LearningLimits()
REPOSITORY_SNAPSHOT = RepositorySnapshotLimits()
REPOSITORY_OBSERVATION = RepositoryObservationLimits()
ANALYSIS_SCOPE = ExplorerScopeLimits()
