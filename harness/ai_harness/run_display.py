"""Human-readable run display helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .run_identity import display_timestamp, parse_timestamp, run_id_datetime


def read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def first_text_line(value: object) -> str:
    if not isinstance(value, str):
        return ""
    for line in value.splitlines():
        text = " ".join(line.strip().split())
        if text:
            return text
    return ""


def markdown_section_first_line(text: str, heading: str) -> str:
    marker = f"## {heading}"
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().casefold() != marker.casefold():
            continue
        for candidate in lines[index + 1:]:
            stripped = candidate.strip()
            if stripped.startswith("## "):
                return ""
            if stripped:
                return stripped.lstrip("# ").strip()
    return ""


def run_title(root: Path | None, state: dict[str, Any]) -> str:
    if root is not None:
        title = read_json_if_present(root / "run-title.json")
        if title:
            value = first_text_line(title.get("title"))
            if value:
                return value[:120]
        for artifact in ("published/explore-handoff.json", "published/explorer-handoff.json"):
            handoff = read_json_if_present(root / artifact)
            if handoff:
                entries = handoff.get("entries")
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict):
                            value = first_text_line(entry.get("title"))
                            if value:
                                return value[:120]
                value = first_text_line(handoff.get("title"))
                if value:
                    return value[:120]
        outcome = read_json_if_present(root / "explore" / "outcome_bundle.json")
        if outcome:
            entries = outcome.get("entries")
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict):
                        value = first_text_line(entry.get("title"))
                        if value:
                            return value[:120]
        purpose = root / "purpose.md"
        if purpose.is_file():
            try:
                value = markdown_section_first_line(purpose.read_text(encoding="utf-8"), "Problem")
            except OSError:
                value = ""
            if value:
                return value[:120]
        tasks = read_json_if_present(root / "tasks.json")
        raw_tasks = tasks.get("tasks") if tasks else None
        if isinstance(raw_tasks, list):
            for task in raw_tasks:
                if isinstance(task, dict):
                    value = first_text_line(task.get("title"))
                    if value:
                        return value[:120]
    return (first_text_line(state.get("user_input")) or "Untitled harness run")[:120]


def run_branch(root: Path | None) -> str:
    if root is None:
        return ""
    git = read_json_if_present(root / "git-run.json")
    if not git:
        return ""
    branch = git.get("created_branch") or git.get("current_branch")
    return str(branch).strip() if isinstance(branch, str) else ""


def _state_timestamp(state: dict[str, Any], name: str) -> datetime | None:
    timestamps = state.get("timestamps")
    if isinstance(timestamps, dict):
        parsed = parse_timestamp(timestamps.get(name))
        if parsed is not None:
            return parsed
    return parse_timestamp(state.get(name))


def run_datetime(root: Path | None, state: dict[str, Any]) -> datetime | None:
    run_id = state.get("run_id")
    if isinstance(run_id, str):
        parsed = run_id_datetime(run_id)
        if parsed is not None:
            return parsed
    for name in ("started_at", "finished_at", "updated_at"):
        parsed = _state_timestamp(state, name)
        if parsed is not None:
            return parsed
    if root is not None:
        try:
            return datetime.fromtimestamp(root.stat().st_mtime).astimezone()
        except OSError:
            return None
    return None


def run_display_label(root: Path | None, state: dict[str, Any]) -> str:
    status = str(state.get("status") or "unknown")
    return f"[{display_timestamp(run_datetime(root, state))}][{status}]: {run_title(root, state)}"
