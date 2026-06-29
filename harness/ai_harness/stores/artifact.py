"""Contained, atomic human-readable artifact storage."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path, PurePath
from typing import Any, Iterable, Mapping

from ..errors import ArtifactError
from .live_registry import TERMINAL_STATUSES, LiveRunRegistry


class ArtifactStore:
    def __init__(self, target_repository: Path, *, current_dir: Path | None = None, create: bool = True) -> None:
        self.target_repository = Path(target_repository).resolve()
        self.runtime_root = self.target_repository / ".ai-harness"
        self.artifacts_root = self.runtime_root / "artifacts"
        self.current = current_dir.resolve() if current_dir is not None else self.artifacts_root / "current"
        self.runs = self.artifacts_root / "runs"
        if create:
            self.current.mkdir(parents=True, exist_ok=True)
            self.runs.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_run(cls, target_repository: Path, run_id: str) -> "ArtifactStore":
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            raise ArtifactError("invalid live run ID")
        live = Path(target_repository).resolve() / ".ai-harness" / "artifacts" / f"current-{run_id}"
        store = cls(target_repository, current_dir=live)
        store._publish_current_compatibility_link()
        store.activate(run_id)
        return store

    @classmethod
    def from_live_dir(cls, target_repository: Path, live_dir: Path, *, create: bool = False) -> "ArtifactStore":
        root = Path(target_repository).resolve() / ".ai-harness" / "artifacts"
        resolved = Path(live_dir).resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ArtifactError("live artifact directory escapes artifacts root")
        if resolved.name != "current" and not resolved.name.startswith("current-"):
            raise ArtifactError("live artifact directory must be current or current-<run_id>")
        return cls(target_repository, current_dir=resolved, create=create)

    def _publish_current_compatibility_link(self) -> None:
        legacy = self.artifacts_root / "current"
        if legacy == self.current:
            return
        if legacy.is_symlink():
            legacy.unlink()
        elif legacy.exists():
            return
        legacy.parent.mkdir(parents=True, exist_ok=True)
        try:
            legacy.symlink_to(self.current.name, target_is_directory=True)
        except OSError:
            legacy.mkdir(parents=True, exist_ok=True)

    def activate(self, run_id: str) -> None:
        payload = {
            "schema_version": 1,
            "run_id": run_id,
            "current": self.current.name,
        }
        self._atomic_write(
            self.artifacts_root / "active.json",
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        LiveRunRegistry(self.target_repository).record(run_id, self.current, "active", pid=os.getpid())

    def clear_live(self, run_id: str | None = None, status: str = "completed") -> None:
        if run_id is not None:
            LiveRunRegistry(self.target_repository).close(run_id, status, current_dir=self.current)
            active = self.artifacts_root / "active.json"
            if active.is_file():
                try:
                    value = json.loads(active.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    value = {}
                if isinstance(value, dict) and value.get("run_id") == run_id:
                    active.unlink(missing_ok=True)
        legacy = self.artifacts_root / "current"
        if legacy.is_symlink() and legacy.resolve() == self.current.resolve():
            legacy.unlink()
        if self.current.exists():
            shutil.rmtree(self.current)

    def phase_temp_dir(self, run_id: str, phase: str, job_id: str) -> Path:
        temp = self.runtime_root / "tmp" / run_id / phase.lower() / job_id
        temp.mkdir(parents=True, exist_ok=True)
        return temp

    def cleanup_run_temp(self, run_id: str) -> None:
        shutil.rmtree(self.runtime_root / "tmp" / run_id, ignore_errors=True)

    def _path(self, name: str) -> Path:
        raw = PurePath(name)
        if not name or raw.is_absolute() or ".." in raw.parts:
            raise ArtifactError("artifact path must be relative and contained")
        candidate = self.current.joinpath(*raw.parts)
        resolved_parent = candidate.parent.resolve()
        if not resolved_parent.is_relative_to(self.current.resolve()):
            raise ArtifactError("artifact path escapes current artifacts")
        if candidate.exists() and not candidate.resolve().is_relative_to(self.current.resolve()):
            raise ArtifactError("artifact symlink escapes current artifacts")
        return candidate

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    def write(self, name: str, content: str) -> str:
        if not isinstance(content, str):
            raise ArtifactError("artifact content must be text")
        path = self._path(name)
        self._atomic_write(path, content)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def read(self, name: str) -> str:
        path = self._path(name)
        if not path.is_file():
            raise ArtifactError(f"artifact does not exist: {name}")
        return path.read_text(encoding="utf-8")

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()

    def write_json(self, name: str, data: Any) -> str:
        content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        return self.write(name, content)

    def read_json(self, name: str) -> Any:
        try:
            return json.loads(self.read(name))
        except json.JSONDecodeError as exc:
            raise ArtifactError(f"invalid JSON artifact: {name}") from exc

    def list(self) -> list[str]:
        return sorted(str(path.relative_to(self.current)) for path in self.current.rglob("*") if path.is_file())

    def checksum(self, name: str) -> str:
        return hashlib.sha256(self.read(name).encode("utf-8")).hexdigest()

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.exists() and not path.is_symlink():
            return
        if path.is_file() or path.is_symlink():
            path.unlink()
        parent = path.parent
        while parent != self.current and parent.exists() and parent.is_relative_to(self.current) and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent

    def snapshot_run(
        self,
        run_id: str,
        overrides: Mapping[str, str] | None = None,
        *,
        artifact_names: Iterable[str] | None = None,
    ) -> Path:
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            raise ArtifactError("invalid snapshot run ID")
        destination = self.runs / run_id
        if destination.exists():
            raise ArtifactError(f"snapshot already exists: {run_id}")
        temporary = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=self.runs))
        try:
            if artifact_names is None:
                for source in self.current.iterdir():
                    target = temporary / source.name
                    if source.is_dir():
                        shutil.copytree(source, target, symlinks=False)
                    elif source.is_file():
                        shutil.copy2(source, target, follow_symlinks=True)
            else:
                for name in dict.fromkeys(artifact_names):
                    source = self._path(name)
                    if not source.is_file():
                        raise ArtifactError(f"recorded artifact missing during snapshot: {name}")
                    target = temporary.joinpath(*PurePath(name).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target, follow_symlinks=True)
            for name, content in (overrides or {}).items():
                raw = PurePath(name)
                target = temporary.joinpath(*raw.parts)
                if (not name or raw.is_absolute() or ".." in raw.parts
                        or not target.parent.resolve().is_relative_to(temporary.resolve())):
                    raise ArtifactError("snapshot override path must be relative and contained")
                if not isinstance(content, str):
                    raise ArtifactError("snapshot override content must be text")
                self._atomic_write(target, content)
            os.rename(temporary, destination)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return destination


def discover_live_artifacts(target_repository: Path) -> list[ArtifactStore]:
    artifacts_root = Path(target_repository).resolve() / ".ai-harness" / "artifacts"
    candidates: list[Path] = []
    registry = LiveRunRegistry(target_repository)
    candidates.extend(registry.current_path(entry) for entry in registry.entries())
    active = artifacts_root / "active.json"
    if active.is_file():
        try:
            value = json.loads(active.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if isinstance(value, dict) and isinstance(value.get("current"), str):
            candidates.append(artifacts_root / value["current"])
    candidates.extend(sorted(artifacts_root.glob("current-*")))
    legacy = artifacts_root / "current"
    if legacy.exists() or legacy.is_symlink():
        candidates.append(legacy)

    stores: list[ArtifactStore] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        stores.append(ArtifactStore.from_live_dir(target_repository, resolved))
    return stores


def cleanup_terminal_live_artifacts(target_repository: Path) -> list[str]:
    diagnostics: list[str] = []
    for artifacts in discover_live_artifacts(target_repository):
        run_id = None
        status = None
        state_path = artifacts.current / "state.json"
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                diagnostics.append(f"invalid state artifact in {artifacts.current}")
                continue
            if isinstance(state, dict):
                run_id = state.get("run_id")
                status = state.get("status")
        if isinstance(run_id, str) and isinstance(status, str) and status in TERMINAL_STATUSES:
            artifacts.clear_live(run_id, status)
        elif not state_path.is_file():
            diagnostics.append(f"unclassified live artifact directory: {artifacts.current}")
    return diagnostics
