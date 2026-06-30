"""Launcher rendering for unfinished and live runs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..models import RunState, RunStatus
from ..output import render_archive_command, render_pending_decision, render_resume_command
from ..run_display import read_json_if_present, run_branch, run_datetime, run_display_label
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


def _state_from_dir(path: Path) -> dict[str, object] | None:
    state = read_json_if_present(path / "state.json")
    return state if isinstance(state, dict) else None


def _next_bundle_from_artifacts(path: Path) -> str | None:
    for artifact, bundle in (
        ("published/tasks-handoff.json", "TDD_BUNDLE"),
        ("published/design-handoff.json", "TASKS_BUNDLE"),
        ("published/spec-handoff.json", "DESIGN_BUNDLE"),
        ("published/proposal-handoff.json", "SPEC_BUNDLE"),
        ("published/explore-handoff.json", "PROPOSAL_BUNDLE"),
    ):
        if (path / artifact).is_file():
            return bundle
    return None


def _fallback_state(run_id: str, status: str, *, created_at: str = "", updated_at: str = "") -> dict[str, object]:
    timestamps = {"started_at": created_at, "updated_at": updated_at, "finished_at": None}
    return {"run_id": run_id, "status": status, "current_phase": "unknown", "user_input": "", "timestamps": timestamps}


def render_show_runs(repository: Path) -> str:
    context = command_context(repository)
    registry = LiveRunRegistry(repository)
    records: dict[str, dict[str, object]] = {}
    for entry in registry.entries():
        artifact_dir = registry.current_path(entry)
        state = _state_from_dir(artifact_dir) or _fallback_state(entry.run_id, entry.status, created_at=entry.created_at, updated_at=entry.updated_at)
        records[entry.run_id] = {"artifact_dir": artifact_dir, "target": entry.target_repository, "state": state}
    for artifacts, state in live_states(repository):
        records[state.run_id] = {
            "artifact_dir": artifacts.current,
            "target": str(repository),
            "state": state.to_dict(),
            "selected_model": state.selected_model,
        }
    runs_root = repository / ".ai-harness" / "artifacts" / "runs"
    if runs_root.is_dir():
        for snapshot in sorted(item for item in runs_root.iterdir() if item.is_dir()):
            state = _state_from_dir(snapshot)
            if not isinstance(state, dict):
                continue
            run_id = str(state.get("run_id") or snapshot.name)
            records[run_id] = {"artifact_dir": snapshot, "target": str(repository), "state": state, "snapshot": True}
    if not records:
        return f"No runs found for {repository}.\n"

    def sort_key(item: tuple[str, dict[str, object]]) -> tuple[datetime, str]:
        run_id, record = item
        artifact_dir = Path(str(record["artifact_dir"]))
        state = record.get("state") if isinstance(record.get("state"), dict) else {}
        moment = run_datetime(artifact_dir, state) or datetime.min.replace(tzinfo=timezone.utc)
        return moment, run_id

    lines = ["Runs", f"Repository: {repository}", ""]
    for run_id, record in sorted(records.items(), key=sort_key, reverse=True):
        artifact_dir = Path(str(record["artifact_dir"]))
        state = record.get("state") if isinstance(record.get("state"), dict) else _fallback_state(run_id, "unknown")
        status = str(state.get("status") or "unknown")
        selected_model = str(record.get("selected_model") or state.get("selected_model") or "").strip() or None
        branch = run_branch(artifact_dir)
        phase = str(state.get("current_phase") or "unknown")
        lines.extend([
            run_display_label(artifact_dir, state),
            f"  id: {run_id}",
            f"  phase: {phase}",
        ])
        if branch:
            lines.append(f"  branch: {branch}")
        lines.extend([
            f"  artifacts: {artifact_dir}",
            f"  target: {record.get('target', repository)}",
        ])
        if status in {"active", "waiting_for_user"}:
            lines.extend([
                f"  resume: {render_resume_command(context, run_id, model=selected_model)}",
                f"  archive: {render_archive_command(context, run_id)}",
            ])
        elif status == "completed":
            next_bundle = _next_bundle_from_artifacts(artifact_dir)
            action = f"continue with {next_bundle}" if next_bundle else "terminal run"
            lines.append(f"  action: {action}")
        else:
            lines.append("  action: terminal run")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
