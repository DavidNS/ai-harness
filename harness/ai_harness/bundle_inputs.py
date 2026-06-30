"""Import artifacts from completed runs for independent bundle execution."""

from __future__ import annotations

import json
import shutil
from pathlib import Path, PurePath

from .errors import ArtifactError
from .stores.artifact import ArtifactStore
from .stores.state import StateStore

_SKIP_IMPORTS = {"state.json", "result.json"}


def _source_root(repository: Path, source: str) -> Path:
    value = source.strip()
    if not value:
        raise ArtifactError("--from-run requires a run id or artifact directory")
    candidate = Path(value).expanduser()
    if candidate.exists():
        root = candidate.resolve()
    else:
        root = (repository.resolve() / ".ai-harness" / "artifacts" / "runs" / value).resolve()
    runs_root = (repository.resolve() / ".ai-harness" / "artifacts" / "runs").resolve()
    if not root.is_dir() or not root.is_relative_to(runs_root):
        raise ArtifactError("source run must be a completed run under .ai-harness/artifacts/runs")
    return root


def import_source_run_artifacts(repository: Path, artifacts: ArtifactStore, state: StateStore, source: str) -> None:
    root = _source_root(repository, source)
    imported: list[dict[str, object]] = []
    for source_file in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = source_file.relative_to(root).as_posix()
        raw = PurePath(relative)
        if relative in _SKIP_IMPORTS or raw.is_absolute() or ".." in raw.parts:
            continue
        target = artifacts.current.joinpath(*raw.parts)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target, follow_symlinks=True)
        state.record_artifact(relative, state.load().current_phase)
        imported.append({
            "source_artifact": relative,
            "imported_as": relative,
            "checksum": artifacts.checksum(relative),
        })
    payload = {
        "schema_version": 1,
        "source_run_id": root.name,
        "source_path": str(root),
        "imported_artifacts": imported,
    }
    artifacts.write_json("inputs/source-run.json", payload)
    state.record_artifact("inputs/source-run.json", state.load().current_phase)


def compatible_runs(repository: Path, required_artifact: str) -> list[dict[str, object]]:
    runs_root = repository.resolve() / ".ai-harness" / "artifacts" / "runs"
    if not runs_root.is_dir():
        return []
    result: list[dict[str, object]] = []
    for run in sorted(runs_root.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True):
        if not run.is_dir():
            continue
        artifact = run / required_artifact
        if artifact.is_file():
            result.append({"run_id": run.name, "path": str(run), "required_artifact": required_artifact})
    return result
