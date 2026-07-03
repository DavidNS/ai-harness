"""Outbound port definitions for AI Harness v2."""

from harness_v2.backend.ports.artifact_store import (
    ArtifactMetadata,
    ArtifactNotFoundError,
    ArtifactManifest,
    ArtifactStoreError,
    ArtifactStorePort,
)
from harness_v2.backend.ports.ci import (
    CIPort,
    CI_MODES,
    CI_TARGETS,
    CiInstallRequest,
    CiInstallResult,
    CiSignalRequest,
)
from harness_v2.backend.ports.clock import ClockPort
from harness_v2.backend.ports.git import (
    BRANCH_MODES,
    GitPort,
    GitRunRequest,
    GitRunResult,
)
from harness_v2.backend.ports.id_generator import IdGeneratorPort
from harness_v2.backend.ports.knowledge_patch_store import (
    KnowledgePatchNotFoundError,
    KnowledgePatchStoreError,
    KnowledgePatchStorePort,
)
from harness_v2.backend.ports.model_provider import (
    CapabilityProjection,
    CapabilityProjectionError,
    McpToolCapability,
    ModelProviderError,
    ModelProviderPort,
    ModelProviderRequest,
    OutputSchema,
    ModelProviderResult,
    ModelSelection,
    PathCapability,
    TimeoutPolicy,
    TruncationPolicy,
)
from harness_v2.backend.ports.state_store import (
    StateNotFoundError,
    StateStoreCorruptionError,
    StateStoreError,
    StateStorePort,
)

__all__ = [
    "ArtifactMetadata",
    "ArtifactNotFoundError",
    "ArtifactManifest",
    "ArtifactStoreError",
    "ArtifactStorePort",
    "BRANCH_MODES",
    "CIPort",
    "CI_MODES",
    "CI_TARGETS",
    "CiInstallRequest",
    "CiInstallResult",
    "CiSignalRequest",
    "CapabilityProjection",
    "CapabilityProjectionError",
    "ClockPort",
    "IdGeneratorPort",
    "GitRunResult",
    "GitRunRequest",
    "GitPort",
    "KnowledgePatchNotFoundError",
    "KnowledgePatchStoreError",
    "KnowledgePatchStorePort",
    "McpToolCapability",
    "ModelProviderError",
    "ModelProviderPort",
    "ModelProviderRequest",
    "ModelProviderResult",
    "OutputSchema",
    "ModelSelection",
    "PathCapability",
    "StateNotFoundError",
    "StateStoreCorruptionError",
    "StateStoreError",
    "StateStorePort",
    "TimeoutPolicy",
    "TruncationPolicy",
]
