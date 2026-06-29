"""Launcher recovery operations."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import RunState, RunStatus, utc_now
from ..stores.artifact import ArtifactStore
from ..stores.runtime import RunLock
from ..stores.state import StateStore
from .live_runs import find_unfinished_run, unfinished_runs


def archive_run(repository: Path, expected_run_id: str) -> Path:
    with RunLock(repository):
        artifacts, state = find_unfinished_run(repository, expected_run_id)
        if state is None:
            if unfinished_runs(repository):
                raise ValueError("archive run ID does not match persisted state")
            raise ValueError("there is no unfinished run to archive")
        state = StateStore(repository, artifacts).validate_resume(expected_run_id)
        artifacts.write_json(
            "archive.json",
            {
                "run_id": state.run_id,
                "phase": state.current_phase,
                "archived_at": utc_now(),
            },
        )
        state_json = json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        snapshot = artifacts.snapshot_run(
            state.run_id,
            {"state.json": state_json},
            artifact_names=(*state.artifacts.keys(), "archive.json"),
        )
        artifacts.clear_live(state.run_id, "archived")
        return snapshot


def direct_decision_answer(
    artifacts: ArtifactStore,
    state: RunState,
    answer: str | None,
    selected_option: str | None,
) -> str:
    if state.status is not RunStatus.WAITING_FOR_USER or state.pending_decision is None:
        raise ValueError("direct answers can only resume a waiting run")
    text = (answer or selected_option or "").strip()
    if not text:
        raise ValueError("--answer or --selected-option must be nonempty")
    request = artifacts.read_json(state.pending_decision.request_artifact)
    options = request.get("options", []) if isinstance(request, dict) else []
    option_ids = {item.get("id") for item in options if isinstance(item, dict)}
    selected = selected_option.strip() if selected_option else None
    if selected is None and text in option_ids:
        selected = text
    payload = {
        "schema_version": 1,
        "kind": "decision_answer",
        "decision_id": state.pending_decision.id,
        "answer": text,
        "selected_option": selected,
    }
    return json.dumps(payload, ensure_ascii=False)
