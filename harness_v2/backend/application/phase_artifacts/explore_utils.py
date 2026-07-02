"""Shared Explore artifact mapping helpers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError

_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2, "critical": 3}
_WORK_SHAPES = {
    "direct_change",
    "change_with_extraction",
    "change_with_test_gap_closure",
    "security_sensitive_change",
    "performance_baseline_then_change",
    "migration_sensitive_change",
    "investigation_needed",
    "documentation_only",
}
_OBSERVATION_LIMIT = 12
_SIGNAL_LIMIT = 8
_HANDOFF_LIMIT = 8

def _validate_unique_evidence_ids(value: object, field: str) -> None:
    seen: set[str] = set()
    for item in _object_list(value, field):
        evidence_id = _text(item.get("id"))
        if evidence_id in seen:
            raise BundleValidationError(f"{field} ids must be unique")
        seen.add(evidence_id)

def _artifact_strings(value: object) -> tuple[str, ...]:
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())

def _evidence_ids(value: dict[str, Any]) -> set[str]:
    return {str(item["id"]) for item in _object_list(value.get("evidence"), "evidence")}

def _validate_refs(refs: tuple[str, ...], evidence_ids: set[str]) -> None:
    missing = [ref for ref in refs if ref not in evidence_ids]
    if missing:
        raise BundleValidationError("unknown evidence refs: " + ", ".join(missing))

def _safe_artifact_json(artifacts: Any | None, run_id: str, artifact_id: str) -> dict[str, object]:
    if artifacts is None:
        return {}
    try:
        value = artifacts.read_json(run_id, artifact_id)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}

def _safe_artifact_list(
    artifacts: Any | None,
    run_id: str,
    artifact_id: str,
    *,
    keys: Sequence[str],
) -> list[Mapping[str, object]]:
    value = _safe_artifact_json(artifacts, run_id, artifact_id)
    for key in keys:
        items = value.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
    return []

def _path(value: object) -> str:
    text = _text(value)
    if not text or Path(text).is_absolute():
        return ""
    return text

def _source_path(value: Mapping[str, object]) -> str:
    return _path(value.get("path")) or _path(value.get("raw_path"))

def _path_parts(path: str) -> tuple[str, ...]:
    return tuple(part for part in Path(path).parts if part not in {".", ""})

def _same_area(path: str, candidate: str) -> bool:
    parts = _path_parts(path)
    candidate_parts = _path_parts(candidate)
    if not parts or not candidate_parts:
        return False
    if path == candidate:
        return True
    return len(parts) >= 2 and len(candidate_parts) >= 2 and parts[:2] == candidate_parts[:2]

def _is_relevant_or_adjacent(path: str, relevant_paths: set[str]) -> bool:
    return bool(path and relevant_paths and any(_same_area(path, candidate) for candidate in relevant_paths))

def _signal_summary(signal: Mapping[str, object]) -> dict[str, object]:
    item: dict[str, object] = {
        "tool": _text(signal.get("tool")) or "unknown",
        "category": _text(signal.get("category")) or "unknown",
        "severity": _severity(signal.get("severity")),
        "summary": _text(signal.get("summary")) or _text(signal.get("evidence")) or "CI signal was reported.",
    }
    path = _source_path(signal)
    if path:
        item["path"] = path
    evidence = _text(signal.get("evidence"))
    if evidence and len(evidence) <= 240:
        item["evidence"] = evidence
    return item

def _count_by(signals: Sequence[Mapping[str, object]], key: str) -> dict[str, int]:
    counter = Counter(_text(signal.get(key)) or "unknown" for signal in signals)
    return dict(sorted(counter.items()))

def _severity(value: object) -> str:
    text = _text(value).casefold()
    return text if text in _SEVERITY_ORDER else "info"

def _severity_rank(value: object) -> int:
    return _SEVERITY_ORDER.get(_severity(value), 0)

def _signal_key(signal: Mapping[str, object]) -> tuple[int, str, str, str]:
    return (_severity_rank(signal.get("severity")), _text(signal.get("tool")), _source_path(signal), _text(signal.get("summary")))

def _evidence_kind(signal: Mapping[str, object]) -> str:
    category = _text(signal.get("category")).casefold()
    tool = _text(signal.get("tool")).casefold()
    if category == "security" or tool == "semgrep":
        return "security"
    if category in {"tests", "test"} or tool in {"pytest", "unittest"}:
        return "test"
    if category in {"lint", "typing", "budget", "architecture"} or tool in {"ruff", "mypy", "check_architecture"}:
        return "structure"
    return "ci"

def _candidate_paths(*groups: Sequence[Mapping[str, object]]) -> set[str]:
    paths: set[str] = set()
    for group in groups:
        for item in group:
            path = _path(item.get("path"))
            if path:
                paths.add(path)
            for source in _list(item.get("sources")):
                if isinstance(source, Mapping):
                    source_path = _path(source.get("path"))
                    if source_path:
                        paths.add(source_path)
    return paths

def _source_paths(evidence: Sequence[Mapping[str, object]]) -> dict[str, list[str]]:
    paths_by_evidence: dict[str, list[str]] = {}
    for item in evidence:
        evidence_id = _text(item.get("id"))
        if not evidence_id:
            continue
        paths: list[str] = []
        for source in _mapping_list(item.get("sources", [])):
            path = _path(source.get("path"))
            if path and path not in paths:
                paths.append(path)
        paths_by_evidence[evidence_id] = paths
    return paths_by_evidence

def _first_unambiguous_path(evidence_refs: Sequence[str], paths_by_evidence: Mapping[str, list[str]]) -> str:
    paths: list[str] = []
    for evidence_ref in evidence_refs:
        for path in paths_by_evidence.get(evidence_ref, []):
            if path not in paths:
                paths.append(path)
    return paths[0] if len(paths) == 1 else ""

def _valid_evidence_refs(value: object, evidence_ids: set[str]) -> list[str]:
    refs: list[str] = []
    for evidence_ref in _string_items(value):
        if evidence_ref in evidence_ids and evidence_ref not in refs:
            refs.append(evidence_ref)
    return refs

def _surface_kind(observation: Mapping[str, object]) -> str:
    kind = _text(observation.get("kind")).casefold()
    path = _text(observation.get("path")).casefold()
    if kind == "test" or "/test" in path or path.startswith("tests/"):
        return "test_surface"
    if kind in {"analysis_doc", "documentation", "prompt", "worker"} or path.endswith(".md"):
        return "documentation_surface"
    if kind == "source" or path.endswith((".py", ".js", ".ts", ".tsx", ".jsx")):
        return "implementation_surface"
    return "repository_surface"

def _surface_reason(observation: Mapping[str, object]) -> str:
    matches = _string_items(observation.get("matches"))
    if matches:
        return matches[0]
    terms = _string_items(observation.get("matched_terms"))
    if terms:
        return "Matched request/evidence terms: " + ", ".join(terms[:6])
    return "Repository observation selected this path."

def _risk_kind(text: str) -> str | None:
    lowered = text.casefold()
    if any(term in lowered for term in ("secret", "token", "auth", "permission", "path", "shell", "subprocess", "security")):
        return "security"
    if any(term in lowered for term in ("slow", "cache", "timeout", "loop", "scan", "performance", "latency")):
        return "performance"
    if any(term in lowered for term in ("migration", "schema", "database", "backfill")):
        return "migration"
    if any(term in lowered for term in ("test", "coverage", "regression", "flaky")):
        return "regression"
    if any(term in lowered for term in ("architecture", "budget", "large", "coupling", "over_by")):
        return "coupling"
    return None

def _shape_from_risks(risks: Sequence[Mapping[str, object]]) -> list[str]:
    kinds = {_text(item.get("kind")) for item in risks}
    shapes: list[str] = []
    if "security" in kinds:
        shapes.append("security_sensitive_change")
    if "performance" in kinds:
        shapes.append("performance_baseline_then_change")
    if "migration" in kinds:
        shapes.append("migration_sensitive_change")
    if "regression" in kinds:
        shapes.append("change_with_test_gap_closure")
    if "coupling" in kinds:
        shapes.append("change_with_extraction")
    return shapes

def _confidence(value: object, *, default: str = "medium") -> str:
    text = _text(value).casefold()
    return text if text in {"low", "medium", "high", "critical"} else default

def _append_unique(items: list[dict[str, object]], item: dict[str, object]) -> None:
    key = (item.get("kind"), item.get("path"), item.get("text"), item.get("shape"))
    for existing in items:
        if (existing.get("kind"), existing.get("path"), existing.get("text"), existing.get("shape")) == key:
            return
    items.append(item)

def _drop_empty_optional_strings(item: dict[str, object], fields: Sequence[str]) -> None:
    for field in fields:
        if field in item and not _text(item.get(field)):
            del item[field]

def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleValidationError(f"{field} must be an object")
    return value

def _object_list(value: object, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise BundleValidationError(f"{field} must be a list of objects")
    return value

def _mapping_list(value: object) -> list[Mapping[str, object]]:
    return [item for item in _list(value) if isinstance(item, Mapping)]

def _string_items(value: object) -> list[str]:
    return [_text(item) for item in _list(value) if _text(item)]

def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []

def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def candidate_paths(*groups: Sequence[Mapping[str, object]]) -> set[str]:
    return _candidate_paths(*groups)


def evidence_ids(value: dict[str, Any]) -> set[str]:
    return _evidence_ids(value)


def object_list(value: object, field: str) -> list[dict[str, Any]]:
    return _object_list(value, field)
