"""Artifact persistence ports for v2 backend runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ArtifactStoreError(RuntimeError):
    """Base error for artifact store failures."""


class ArtifactNotFoundError(ArtifactStoreError):
    """Raised when a requested artifact does not exist."""


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    artifact_id: str
    checksum: str
    size: int


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    """Metadata-only artifact inventory; does not copy artifact bytes."""

    run_id: str
    artifacts: tuple[ArtifactMetadata, ...]


class ArtifactStorePort(Protocol):
    """Run artifact persistence boundary."""

    def write(self, run_id: str, artifact_id: str, content: bytes) -> ArtifactMetadata: ...

    def read(self, run_id: str, artifact_id: str) -> bytes: ...

    def checksum(self, run_id: str, artifact_id: str) -> str: ...

    def list(self, run_id: str) -> tuple[ArtifactMetadata, ...]: ...

    def manifest(self, run_id: str) -> ArtifactManifest: ...
