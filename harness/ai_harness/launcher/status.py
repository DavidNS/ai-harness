"""Launcher status rendering."""

from __future__ import annotations

import json
from pathlib import Path

from ..output import render_archive_command, render_resume_command
from ..stores.artifact import discover_live_artifacts
from ..stores.live_registry import LiveRunRegistry
from .context import command_context


def read_json_if_present(path: Path) -> object | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def state_from_artifact_dir(path: Path) -> dict[str, object] | None:
    value = read_json_if_present(path / "state.json")
    return value if isinstance(value, dict) else None


def latest_job_evidence(path: Path) -> dict[str, object] | None:
    jobs_dir = path / "jobs"
    if not jobs_dir.is_dir():
        return None
    job_dirs = sorted(item for item in jobs_dir.iterdir() if item.is_dir() and item.name.startswith("J"))
    if not job_dirs:
        return None
    job = job_dirs[-1]
    evidence: dict[str, object] = {
        "job_id": job.name,
        "request": str(job / "request.json"),
    }
    if (job / "result.json").is_file():
        evidence["result"] = str(job / "result.json")
    request = read_json_if_present(job / "request.json")
    if isinstance(request, dict) and request.get("temp_dir"):
        evidence["temp_dir"] = str(request["temp_dir"])
    if (job / "debug-before.json").is_file():
        evidence["debug_before"] = str(job / "debug-before.json")
    if (job / "debug-after.json").is_file():
        evidence["debug_after"] = str(job / "debug-after.json")
    return evidence


def status_records(repository: Path) -> dict[str, dict[str, object]]:
    registry = LiveRunRegistry(repository)
    records: dict[str, dict[str, object]] = {}
    for entry in registry.entries():
        current = registry.current_path(entry)
        records[entry.run_id] = {
            "run_id": entry.run_id,
            "status": entry.status,
            "artifact_dir": str(current),
            "target": entry.target_repository,
            "registry": True,
            "state": state_from_artifact_dir(current),
        }
    for artifacts in discover_live_artifacts(repository):
        state = state_from_artifact_dir(artifacts.current)
        if not isinstance(state, dict):
            continue
        run_id = str(state.get("run_id", ""))
        if not run_id:
            continue
        record = records.setdefault(run_id, {"run_id": run_id})
        record.update({
            "status": str(state.get("status", record.get("status", "unknown"))),
            "artifact_dir": str(artifacts.current),
            "target": str(repository),
            "state": state,
        })
    runs_root = repository / ".ai-harness" / "artifacts" / "runs"
    if runs_root.is_dir():
        for snapshot in sorted(item for item in runs_root.iterdir() if item.is_dir()):
            state = state_from_artifact_dir(snapshot)
            if not isinstance(state, dict):
                continue
            run_id = str(state.get("run_id", snapshot.name))
            record = records.setdefault(run_id, {"run_id": run_id})
            record.update({
                "status": str(state.get("status", record.get("status", "unknown"))),
                "artifact_dir": str(snapshot),
                "target": str(repository),
                "state": state,
                "archived_snapshot": True,
            })
    return records


def render_status(repository: Path) -> str:
    context = command_context(repository)
    records = status_records(repository)
    if not records:
        return f"## Harness Status\nRepository: {repository}\nStatus: no run\n"
    lines = ["## Harness Status", f"Repository: {repository}", ""]
    for run_id in sorted(records):
        record = records[run_id]
        state = record.get("state")
        pending = state.get("pending_decision") if isinstance(state, dict) else None
        selected_provider = state.get("selected_provider") if isinstance(state, dict) else None
        selected_model = state.get("selected_model") if isinstance(state, dict) else None
        strategy = state.get("strategy") if isinstance(state, dict) else None
        current_phase = state.get("current_phase") if isinstance(state, dict) else None
        artifact_dir = Path(str(record["artifact_dir"]))
        evidence = latest_job_evidence(artifact_dir)
        lines.extend([
            f"Run ID: {run_id}",
            f"Status: {record.get('status', 'unknown')}",
            f"Strategy: {strategy or 'unknown'}",
            f"Current phase: {current_phase or 'unknown'}",
            f"Pending decision ID: {pending.get('id') if isinstance(pending, dict) else 'none'}",
            f"Selected provider: {selected_provider or 'unknown'}",
            f"Selected model: {selected_model or 'provider default'}",
            f"Artifact dir: {artifact_dir}",
        ])
        if evidence is None:
            lines.append("Latest job: none")
        else:
            lines.extend([
                f"Latest job: {evidence['job_id']}",
                f"Job request: {evidence['request']}",
                f"Job result: {evidence.get('result', 'pending')}",
                f"Job temp dir: {evidence.get('temp_dir', 'unknown')}",
            ])
            if evidence.get("debug_before"):
                lines.append(f"Job debug before: {evidence['debug_before']}")
            if evidence.get("debug_after"):
                lines.append(f"Job debug after: {evidence['debug_after']}")
        if record.get("status") in {"active", "waiting_for_user"}:
            lines.extend([
                f"Resume: {render_resume_command(context, run_id, model=selected_model or None)}",
                f"Archive: {render_archive_command(context, run_id)}",
            ])
        else:
            lines.extend([
                "Resume: unavailable (run is terminal)",
                "Archive: unavailable (run is terminal)",
            ])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
