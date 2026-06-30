"""Canonical EXPLORE evidence helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..stores.artifact import ArtifactStore


_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2, "critical": 3}


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _safe_artifact_json(artifacts: ArtifactStore, name: str) -> dict[str, object]:
    if not artifacts.exists(name):
        return {}
    try:
        value = artifacts.read_json(name)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _severity(value: object) -> str:
    text = _text(value).casefold()
    return text if text in _SEVERITY_ORDER else "info"


def _evidence_kind(signal: Mapping[str, object]) -> str:
    category = _text(signal.get("category")).casefold()
    tool = _text(signal.get("tool")).casefold()
    if category in {"security"} or tool == "semgrep":
        return "security"
    if category in {"tests", "test"} or tool in {"pytest", "unittest"}:
        return "test"
    if category in {"lint", "typing", "budget", "architecture"} or tool in {"ruff", "mypy", "check_architecture"}:
        return "structure"
    return "ci"


def _source_for_signal(signal: Mapping[str, object]) -> dict[str, object]:
    source: dict[str, object] = {"type": "ci"}
    path = _text(signal.get("path"))
    if path and not Path(path).is_absolute():
        source["path"] = path
    artifact = _text(signal.get("artifact")) or "ci-signals.json"
    source["artifact"] = artifact
    description = _text(signal.get("agent_hint")) or _text(signal.get("evidence")) or _text(signal.get("summary"))
    if description:
        source["description"] = description
    return source


def ci_evidence_from_artifacts(artifacts: ArtifactStore) -> list[dict[str, object]]:
    """Return canonical evidence items derived from normalized CI artifacts."""
    signals = _safe_artifact_json(artifacts, "ci-signals.json")
    evidence: list[dict[str, object]] = []
    status = _text(signals.get("status"))
    reason = _text(signals.get("reason"))
    if status and status not in {"ready", "partial"}:
        evidence.append({
            "id": "CI1",
            "kind": "ci",
            "claim": reason or f"CI evidence is {status}.",
            "status": "blocked",
            "confidence": "high",
            "severity": "warning",
            "sources": [{"type": "artifact", "artifact": "ci-signals.json", "description": "Normalized CI signals artifact."}],
        })
        return evidence
    raw_signals = [item for item in _list(signals.get("signals")) if isinstance(item, Mapping)]
    for index, signal in enumerate(raw_signals[:20], start=1):
        summary = _text(signal.get("summary")) or _text(signal.get("evidence")) or "CI signal was reported."
        evidence.append({
            "id": f"CI{index}",
            "kind": _evidence_kind(signal),
            "claim": summary,
            "status": "supported",
            "confidence": _text(signal.get("confidence")) or "high",
            "severity": _severity(signal.get("severity")),
            "sources": [_source_for_signal(signal)],
        })
    return evidence


def merge_evidence(*groups: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Merge evidence groups and assign stable unique IDs when needed."""
    merged: list[dict[str, object]] = []
    used: set[str] = set()
    next_index = 1
    for group in groups:
        for raw in group:
            item = dict(raw)
            evidence_id = _text(item.get("id"))
            if not evidence_id or evidence_id in used:
                while f"E{next_index}" in used:
                    next_index += 1
                evidence_id = f"E{next_index}"
                item["id"] = evidence_id
            used.add(evidence_id)
            merged.append(item)
    return merged


def evidence_from_digest(value: Mapping[str, object]) -> list[dict[str, object]]:
    return [dict(item) for item in _list(value.get("evidence")) if isinstance(item, Mapping)]


def context_pack(
    *,
    request: str,
    profile: Mapping[str, object],
    knowledge: Sequence[str],
    related_improvements: Sequence[Mapping[str, object]],
    repository_observations: Sequence[Mapping[str, object]],
    artifacts: ArtifactStore,
    explorer_scope: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "explore_context_pack",
        "request": request,
        "profile": dict(profile),
        "knowledge": list(knowledge),
        "related_improvements": [dict(item) for item in related_improvements],
        "repository_observations": [dict(item) for item in repository_observations],
        "git": _safe_artifact_json(artifacts, "git-run.json"),
        "ci_status": _safe_artifact_json(artifacts, "ci-status.json"),
        "ci_signals": _safe_artifact_json(artifacts, "ci-signals.json"),
        "explorer_scope": dict(explorer_scope),
    }
