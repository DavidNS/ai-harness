"""FailureRecorder — capture an unexpected run-level exception into persisted state.

Single responsibility: on unhandled exception, mark the current phase failed in
the state store and snapshot the failed-state artifact tree. Previously
_record_failure + _snapshot_run on the Orchestrator.
"""
from __future__ import annotations

import json

from ..models import ErrorRecord, RunStatus
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore


class FailureRecorder:
    """Record a run-level failure into state and create a snapshot artifact."""

    def __init__(self, state: StateStore, artifacts: ArtifactStore) -> None:
        self._state = state
        self._artifacts = artifacts

    def record(self, exc: Exception) -> None:
        try:
            state = self._state.load()
        except Exception:
            return
        if state.status is not RunStatus.ACTIVE:
            return
        message = " ".join(str(exc).split())[:500] or type(exc).__name__
        if state.current_phase not in {"COMPLETED", "FAILED"}:
            try:
                self._state.mark_phase_failed(
                    state.current_phase,
                    ErrorRecord(type(exc).__name__.lower(), message, state.current_phase),
                )
            except Exception:
                pass
        try:
            failed = self._state.load()
            failed_json = json.dumps(failed.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            self._snapshot_run(
                f"{state.run_id}-failed",
                {"state.json": failed_json},
                failed.artifacts.keys(),
            )
        except Exception:
            pass

    def _snapshot_run(self, run_id: str, overrides: dict[str, str], artifact_names) -> None:
        try:
            self._artifacts.snapshot_run(run_id, overrides, artifact_names=artifact_names)
        except TypeError as exc:
            if "artifact_names" not in str(exc):
                raise
            self._artifacts.snapshot_run(run_id, overrides)
