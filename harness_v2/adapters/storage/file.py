"""File-backed storage adapters for v2 run state and artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from pathlib import Path
from typing import Any

from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.errors import DomainValidationError, ErrorRecord
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.domain.tasks import TaskStatus, TaskSummary
from harness_v2.backend.ports.artifact_store import (
    ArtifactManifest,
    ArtifactMetadata,
    ArtifactNotFoundError,
    ArtifactStoreError,
)
from harness_v2.backend.ports.state_store import StateNotFoundError, StateStoreCorruptionError

SCHEMA_VERSION = 1
_ACTIVE_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_FOR_USER}
_TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


def _require_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not run_id.strip() or "/" in run_id or run_id.strip() in {".", ".."}:
        raise ValueError("run_id must be a single nonempty path segment")
    return run_id.strip()


def _require_artifact_id(artifact_id: str) -> str:
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ValueError("artifact_id is required")
    normalized = artifact_id.strip()
    parts = normalized.split("/")
    if normalized.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("artifact_id must be a relative path without empty, current, or parent segments")
    return normalized


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise ArtifactStoreError(f"unsafe artifact path contains a symlink: {path}")


def _require_safe_directory(path: Path) -> None:
    _reject_symlink(path)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise ArtifactNotFoundError(str(path)) from exc
    if not stat.S_ISDIR(mode):
        raise ArtifactStoreError(f"artifact path is not a directory: {path}")


def _ensure_safe_directory_tree(base: Path, parts: tuple[str, ...]) -> Path:
    if base.exists() or base.is_symlink():
        _require_safe_directory(base)
    else:
        base.mkdir(parents=True, exist_ok=True)
        _require_safe_directory(base)

    current = base
    for part in parts:
        current = current / part
        if current.exists() or current.is_symlink():
            _require_safe_directory(current)
        else:
            current.mkdir()
            _require_safe_directory(current)
    return current


def _safe_existing_artifact_root(base: Path, run_id: str) -> Path | None:
    current = base
    for part in ("runs", _require_run_id(run_id), "artifacts"):
        if current.exists() or current.is_symlink():
            _require_safe_directory(current)
        else:
            return None
        current = current / part
    if current.exists() or current.is_symlink():
        _require_safe_directory(current)
        return current
    return None


def _ensure_safe_artifact_parent(base: Path, run_id: str, artifact_id: str) -> Path:
    artifact_parts = tuple(artifact_id.split("/"))
    parent_parts = ("runs", _require_run_id(run_id), "artifacts", *artifact_parts[:-1])
    return _ensure_safe_directory_tree(base, parent_parts)


def _require_safe_existing_artifact(root: Path, artifact_id: str) -> Path:
    parts = artifact_id.split("/")
    current = root
    for part in parts[:-1]:
        current = current / part
        _require_safe_directory(current)

    path = current / parts[-1]
    _reject_symlink(path)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise ArtifactNotFoundError(artifact_id) from exc
    if not stat.S_ISREG(mode):
        raise ArtifactNotFoundError(artifact_id)
    return path


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _run_to_mapping(run: RunRecord) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "run_id": run.run_id,
            "request": run.request,
            "status": run.status.value,
            "strategy": run.strategy.value,
            "current_phase": run.current_phase.value if run.current_phase else None,
            "completed_phases": [phase.value for phase in run.completed_phases],
            "pending_decision": _decision_to_mapping(run.pending_decision),
            "tasks": [_task_to_mapping(task) for task in run.tasks],
            "errors": [_error_to_mapping(error) for error in run.errors],
        },
    }


def _decision_to_mapping(decision: PendingDecision | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "decision_id": decision.decision_id,
        "origin_phase": decision.origin_phase.value,
        "prompt": decision.prompt,
        "created_at": decision.created_at,
        "options": list(decision.options),
    }


def _task_to_mapping(task: TaskSummary) -> dict[str, Any]:
    return {"task_id": task.task_id, "title": task.title, "status": task.status.value}


def _error_to_mapping(error: ErrorRecord) -> dict[str, Any]:
    return {
        "code": error.code,
        "message": error.message,
        "phase": error.phase,
        "timestamp": error.timestamp,
    }


def _run_from_mapping(payload: dict[str, Any]) -> RunRecord:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise StateStoreCorruptionError("unsupported state schema version")
    data = payload.get("run")
    if not isinstance(data, dict):
        raise StateStoreCorruptionError("state payload missing run object")
    try:
        pending = data.get("pending_decision")
        return RunRecord(
            run_id=data["run_id"],
            request=data["request"],
            status=RunStatus(data["status"]),
            strategy=RunStrategy(data["strategy"]),
            current_phase=PhaseName(data["current_phase"]) if data.get("current_phase") is not None else None,
            completed_phases=tuple(PhaseName(phase) for phase in data.get("completed_phases", ())),
            pending_decision=_decision_from_mapping(pending),
            tasks=tuple(_task_from_mapping(task) for task in data.get("tasks", ())),
            errors=tuple(_error_from_mapping(error) for error in data.get("errors", ())),
            events=(),
        )
    except (KeyError, TypeError, ValueError, DomainValidationError) as exc:
        raise StateStoreCorruptionError("state payload is malformed or domain-invalid") from exc


def _decision_from_mapping(data: object) -> PendingDecision | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise StateStoreCorruptionError("pending decision must be an object")
    return PendingDecision(
        decision_id=data["decision_id"],
        origin_phase=PhaseName(data["origin_phase"]),
        prompt=data["prompt"],
        created_at=data["created_at"],
        options=tuple(data.get("options", ())),
    )


def _task_from_mapping(data: object) -> TaskSummary:
    if not isinstance(data, dict):
        raise StateStoreCorruptionError("task summary must be an object")
    return TaskSummary(task_id=data["task_id"], title=data["title"], status=TaskStatus(data["status"]))


def _error_from_mapping(data: object) -> ErrorRecord:
    if not isinstance(data, dict):
        raise StateStoreCorruptionError("error record must be an object")
    return ErrorRecord(
        code=data["code"],
        message=data["message"],
        phase=data.get("phase"),
        timestamp=data["timestamp"],
    )


class FileStateStore:
    """File-backed state store using one JSON state file per run."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def save(self, run: RunRecord) -> None:
        path = self._state_path(run.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_run_to_mapping(run), sort_keys=True, indent=2) + "\n"
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            _fsync_directory(path.parent)
        finally:
            temp_path.unlink(missing_ok=True)

    def get(self, run_id: str) -> RunRecord:
        path = self._state_path(run_id)
        if not path.is_file():
            raise StateNotFoundError(run_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateStoreCorruptionError(f"state file is malformed JSON: {run_id}") from exc
        if not isinstance(payload, dict):
            raise StateStoreCorruptionError("state payload must be an object")
        return _run_from_mapping(payload)

    def list_all(self) -> tuple[RunRecord, ...]:
        runs_dir = self._root / "runs"
        if not runs_dir.exists():
            return ()
        runs = [self.get(path.parent.name) for path in sorted(runs_dir.glob("*/state.json"))]
        return tuple(sorted(runs, key=lambda run: run.run_id))

    def list_active(self) -> tuple[RunRecord, ...]:
        return tuple(run for run in self.list_all() if run.status in _ACTIVE_STATUSES)

    def list_completed(self) -> tuple[RunRecord, ...]:
        return tuple(run for run in self.list_all() if run.status in _TERMINAL_STATUSES)

    def _state_path(self, run_id: str) -> Path:
        return self._root / "runs" / _require_run_id(run_id) / "state.json"


class FileArtifactStore:
    """File-backed artifact store using raw artifact bytes."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def write(self, run_id: str, artifact_id: str, content: bytes) -> ArtifactMetadata:
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        normalized = _require_artifact_id(artifact_id)
        parent = _ensure_safe_artifact_parent(self._root, run_id, normalized)
        path = parent / normalized.split("/")[-1]
        _reject_symlink(path)

        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags, 0o666)
        except OSError as exc:
            if path.is_symlink():
                raise ArtifactStoreError(f"unsafe artifact path contains a symlink: {run_id}:{normalized}") from exc
            raise
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(parent)
        return self._metadata(run_id, normalized)

    def read(self, run_id: str, artifact_id: str) -> bytes:
        normalized = _require_artifact_id(artifact_id)
        root = _safe_existing_artifact_root(self._root, run_id)
        if root is None:
            raise ArtifactNotFoundError(f"{run_id}:{normalized}")
        path = _require_safe_existing_artifact(root, normalized)
        return path.read_bytes()

    def checksum(self, run_id: str, artifact_id: str) -> str:
        return self._metadata(run_id, artifact_id).checksum

    def list(self, run_id: str) -> tuple[ArtifactMetadata, ...]:
        root = _safe_existing_artifact_root(self._root, run_id)
        if root is None:
            return ()
        artifact_ids = []
        for path in root.rglob("*"):
            _reject_symlink(path)
            if path.is_file():
                artifact_ids.append(str(path.relative_to(root)))
        artifact_ids.sort()
        return tuple(self._metadata(run_id, artifact_id) for artifact_id in artifact_ids)

    def manifest(self, run_id: str) -> ArtifactManifest:
        return ArtifactManifest(run_id=run_id, artifacts=self.list(run_id))

    def _metadata(self, run_id: str, artifact_id: str) -> ArtifactMetadata:
        content = self.read(run_id, artifact_id)
        return ArtifactMetadata(
            artifact_id=_require_artifact_id(artifact_id),
            checksum=hashlib.sha256(content).hexdigest(),
            size=len(content),
        )

    def _artifact_root(self, run_id: str) -> Path:
        return self._root / "runs" / _require_run_id(run_id) / "artifacts"

    def _artifact_path(self, run_id: str, artifact_id: str) -> Path:
        return self._artifact_root(run_id) / _require_artifact_id(artifact_id)
