"""Centralised contracts: enums, limits, and vocabulary lists.

All magic strings and scattered numeric limits should live here so that
'follow the repo rules' means something an agent (or linter) can check.
"""
from .enums import ArtifactKind, BundleAction
from .limits import (
    ExplorerScopeLimits,
    LearningLimits,
    RepositoryObservationLimits,
    RepositorySnapshotLimits,
)

__all__ = [
    "ArtifactKind",
    "BundleAction",
    "ExplorerScopeLimits",
    "LearningLimits",
    "RepositoryObservationLimits",
    "RepositorySnapshotLimits",
]
