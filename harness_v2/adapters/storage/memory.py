"""In-memory storage adapters for v2 tests and in-process hosts."""

from __future__ import annotations

import hashlib

from harness_v2.backend.domain.lifecycle import RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import (
    ArtifactMetadata,
    ArtifactNotFoundError,
    ArtifactManifest,
)
from harness_v2.backend.ports.state_store import StateNotFoundError

_ACTIVE_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_FOR_USER}
_TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


def _require_artifact_id(artifact_id: str) -> str:
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ValueError("artifact_id is required")
    normalized = artifact_id.strip()
    parts = normalized.split("/")
    if normalized.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("artifact_id must be a relative path without empty, current, or parent segments")
    return normalized


class InMemoryStateStore:
    """State store backed by a process-local dictionary."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def save(self, run: RunRecord) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> RunRecord:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise StateNotFoundError(run_id) from exc

    def list_all(self) -> tuple[RunRecord, ...]:
        return tuple(self._runs[run_id] for run_id in sorted(self._runs))

    def list_active(self) -> tuple[RunRecord, ...]:
        return tuple(run for run in self.list_all() if run.status in _ACTIVE_STATUSES)

    def list_completed(self) -> tuple[RunRecord, ...]:
        return tuple(run for run in self.list_all() if run.status in _TERMINAL_STATUSES)


class InMemoryArtifactStore:
    """Artifact store backed by process-local bytes."""

    def __init__(self) -> None:
        self._artifacts: dict[tuple[str, str], bytes] = {}

    def write(self, run_id: str, artifact_id: str, content: bytes) -> ArtifactMetadata:
        normalized = _require_artifact_id(artifact_id)
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        self._artifacts[(run_id, normalized)] = bytes(content)
        return self._metadata(run_id, normalized)

    def read(self, run_id: str, artifact_id: str) -> bytes:
        normalized = _require_artifact_id(artifact_id)
        try:
            return self._artifacts[(run_id, normalized)]
        except KeyError as exc:
            raise ArtifactNotFoundError(f"{run_id}:{normalized}") from exc

    def delete(self, run_id: str, artifact_id: str) -> bool:
        normalized = _require_artifact_id(artifact_id)
        return self._artifacts.pop((run_id, normalized), None) is not None

    def checksum(self, run_id: str, artifact_id: str) -> str:
        return self._metadata(run_id, _require_artifact_id(artifact_id)).checksum

    def list(self, run_id: str) -> tuple[ArtifactMetadata, ...]:
        artifact_ids = sorted(artifact_id for stored_run_id, artifact_id in self._artifacts if stored_run_id == run_id)
        return tuple(self._metadata(run_id, artifact_id) for artifact_id in artifact_ids)

    def manifest(self, run_id: str) -> ArtifactManifest:
        return ArtifactManifest(run_id=run_id, artifacts=self.list(run_id))

    def _metadata(self, run_id: str, artifact_id: str) -> ArtifactMetadata:
        content = self.read(run_id, artifact_id) if (run_id, artifact_id) not in self._artifacts else self._artifacts[(run_id, artifact_id)]
        return ArtifactMetadata(
            artifact_id=artifact_id,
            checksum=hashlib.sha256(content).hexdigest(),
            size=len(content),
        )
