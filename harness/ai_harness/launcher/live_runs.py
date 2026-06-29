"""Live run discovery helpers for the launcher backend."""

from __future__ import annotations

from pathlib import Path

from ..models import RunState, RunStatus
from ..stores.artifact import ArtifactStore, discover_live_artifacts
from ..stores.state import StateStore


def live_states(repository: Path) -> list[tuple[ArtifactStore, RunState]]:
    states: list[tuple[ArtifactStore, RunState]] = []
    for artifacts in discover_live_artifacts(repository):
        if not artifacts.exists("state.json"):
            continue
        try:
            state = StateStore(repository, artifacts).load()
        except Exception:
            continue
        states.append((artifacts, state))
    return sorted(states, key=lambda item: (item[1].started_at, item[1].run_id))


def is_unfinished(state: RunState) -> bool:
    return state.status in {RunStatus.ACTIVE, RunStatus.WAITING_FOR_USER}


def unfinished_runs(repository: Path) -> list[tuple[ArtifactStore, RunState]]:
    return [(artifacts, state) for artifacts, state in live_states(repository) if is_unfinished(state)]


def unfinished_run(repository: Path) -> tuple[ArtifactStore, RunState | None]:
    unfinished = unfinished_runs(repository)
    if len(unfinished) > 1:
        run_ids = ", ".join(state.run_id for _, state in unfinished)
        raise ValueError(f"multiple unfinished runs require --show-runs, --resume, or --archive: {run_ids}")
    if unfinished:
        return unfinished[0]
    return ArtifactStore(repository, create=False), None


def find_unfinished_run(repository: Path, run_id: str) -> tuple[ArtifactStore, RunState | None]:
    for artifacts, state in unfinished_runs(repository):
        if state.run_id == run_id:
            return artifacts, state
    return ArtifactStore(repository, create=False), None
