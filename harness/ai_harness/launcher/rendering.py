"""Launcher rendering for unfinished and live runs."""

from __future__ import annotations

from pathlib import Path

from ..models import RunState, RunStatus
from ..output import render_archive_command, render_pending_decision, render_resume_command
from ..stores.artifact import ArtifactStore
from ..stores.live_registry import LiveRunRegistry
from .context import command_context
from .live_runs import live_states


def render_unfinished_run(artifacts: ArtifactStore, state: RunState, repository: Path) -> str:
    context = command_context(repository)
    if state.status is RunStatus.WAITING_FOR_USER:
        assert state.pending_decision is not None
        request = artifacts.read_json(state.pending_decision.request_artifact)
        return render_pending_decision(
            state.run_id,
            state.pending_decision.id,
            request,
            context,
            model=state.selected_model or None,
        )
    return (
        f"error: unfinished run {state.run_id} is active at {state.current_phase}\n"
        "Resume:\n"
        f"{render_resume_command(context, state.run_id, model=state.selected_model or None)}\n"
        "Archive:\n"
        f"{render_archive_command(context, state.run_id)}\n"
    )


def render_show_runs(repository: Path) -> str:
    context = command_context(repository)
    registry = LiveRunRegistry(repository)
    records: dict[str, dict[str, str]] = {}
    for entry in registry.entries():
        records[entry.run_id] = {
            "run_id": entry.run_id,
            "status": entry.status,
            "current": str(registry.current_path(entry)),
            "target": entry.target_repository,
        }
    for artifacts, state in live_states(repository):
        records[state.run_id] = {
            "run_id": state.run_id,
            "status": state.status.value,
            "current": str(artifacts.current),
            "target": str(repository),
            "selected_model": state.selected_model,
        }
    if not records:
        return f"No live runs found for {repository}.\n"
    lines = ["## Live Runs", f"Repository: {repository}", ""]
    for run_id in sorted(records):
        record = records[run_id]
        selected_model = str(record.get("selected_model") or "").strip() or None
        lines.extend([
            f"Run ID: {record['run_id']}",
            f"Status: {record['status']}",
            f"Current: {record['current']}",
            f"Target: {record['target']}",
            f"Resume: {render_resume_command(context, run_id, model=selected_model)}",
            f"Archive: {render_archive_command(context, run_id)}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"
