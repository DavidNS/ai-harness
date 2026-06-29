"""Backend process boundary and run discovery for the AI Harness launcher."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from .bootstrap import OPEN_STATUSES, RUNNER


def _command(args: list[str]) -> list[str]:
    return [sys.executable, "-B", str(RUNNER), *args]


def _repository_from_backend_args(args: list[str]) -> Path | None:
    try:
        index = args.index("--cwd")
        return Path(args[index + 1]).resolve()
    except (ValueError, IndexError, OSError):
        return None


def _run(args: list[str], *, request: str | None = None, verbose: bool = False, dry_run: bool = False) -> int:
    command = _command(args)
    if verbose or dry_run:
        print(shlex.join(command), file=sys.stderr)
    if dry_run:
        return 0
    try:
        completed = subprocess.run(command, input=request, text=True, check=False)
    except KeyboardInterrupt:
        print("\nBackend run interrupted.", file=sys.stderr)
        repository = _repository_from_backend_args(args)
        if repository is not None:
            _print_recovery_actions(repository)
        return 130
    return completed.returncode


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _candidate_live_dirs(repository: Path) -> list[Path]:
    artifacts = repository / ".ai-harness" / "artifacts"
    candidates: list[Path] = []
    registry = _read_json(artifacts / "live-runs.json")
    for entry in registry.get("runs", []) if registry else []:
        if not isinstance(entry, dict) or entry.get("status") not in OPEN_STATUSES:
            continue
        current = entry.get("current_dir")
        if isinstance(current, str) and current:
            path = Path(current)
            candidates.append(path if path.is_absolute() else artifacts / path)
    active = _read_json(artifacts / "active.json")
    if active and isinstance(active.get("current"), str):
        candidates.append(artifacts / str(active["current"]))
    if artifacts.exists():
        candidates.extend(sorted(artifacts.glob("current-*")))
        legacy = artifacts / "current"
        if legacy.exists() or legacy.is_symlink():
            candidates.append(legacy)
    seen: set[Path] = set()
    result: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def _unfinished_runs(repository: Path) -> list[tuple[Path, dict[str, Any]]]:
    runs: list[tuple[Path, dict[str, Any]]] = []
    for current in _candidate_live_dirs(repository):
        state = _read_json(current / "state.json")
        if not state or state.get("status") not in OPEN_STATUSES:
            continue
        if not isinstance(state.get("run_id"), str):
            continue
        runs.append((current, state))
    return sorted(runs, key=lambda item: (str(item[1].get("started_at", "")), str(item[1].get("run_id", ""))))


def _find_run(repository: Path, run_id: str | None) -> tuple[Path, dict[str, Any]] | None:
    runs = _unfinished_runs(repository)
    if run_id:
        for item in runs:
            if item[1].get("run_id") == run_id:
                return item
        return None
    if len(runs) == 1:
        return runs[0]
    if not runs:
        return None
    ids = ", ".join(str(state.get("run_id")) for _, state in runs)
    raise ValueError(f"multiple unfinished runs require a run ID: {ids}")


def _decision_request(current: Path, state: dict[str, Any]) -> dict[str, Any] | None:
    pending = state.get("pending_decision")
    if not isinstance(pending, dict):
        return None
    request_artifact = pending.get("request_artifact")
    if not isinstance(request_artifact, str) or not request_artifact:
        return None
    raw = Path(request_artifact)
    if raw.is_absolute() or ".." in raw.parts:
        return None
    return _read_json(current.joinpath(*raw.parts))


def _run_phase(state: dict[str, Any]) -> str:
    value = state.get("current_phase")
    return str(value) if value else "unknown"


def _run_line(index: int | None, state: dict[str, Any]) -> str:
    prefix = f" {index}. " if index is not None else "- "
    return f"{prefix}{state.get('run_id')} [{state.get('status', 'unknown')}] phase={_run_phase(state)}"


def _print_unfinished_runs(repository: Path, runs: list[tuple[Path, dict[str, Any]]] | None = None, *, heading: str = "Unfinished runs") -> None:
    selected = _unfinished_runs(repository) if runs is None else runs
    if not selected:
        print("No unfinished runs found.", file=sys.stderr)
        return
    print(f"{heading}:", file=sys.stderr)
    for index, (_, state) in enumerate(selected, 1):
        print(_run_line(index, state), file=sys.stderr)


def _print_recovery_actions(repository: Path) -> None:
    runs = _unfinished_runs(repository)
    if not runs:
        print("No resumable run was found.", file=sys.stderr)
        return
    _print_unfinished_runs(repository, runs, heading="Current recovery options")
    if len(runs) == 1:
        run_id = str(runs[0][1].get("run_id"))
        print(f"Use `resume {run_id}` or `archive {run_id}` from the console.", file=sys.stderr)
    else:
        print("Use `resume <RUN_ID>` or `archive <RUN_ID>` from the console.", file=sys.stderr)
