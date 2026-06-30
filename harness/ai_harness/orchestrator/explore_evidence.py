"""Canonical EXPLORE evidence helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections import Counter
from pathlib import Path
from typing import Any

from ..stores.artifact import ArtifactStore


_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2, "critical": 3}


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _object_list(value: object) -> list[Mapping[str, object]]:
    return [item for item in _list(value) if isinstance(item, Mapping)]


def _safe_artifact_json(artifacts: ArtifactStore, name: str) -> dict[str, object]:
    if not artifacts.exists(name):
        return {}
    try:
        value = artifacts.read_json(name)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}



def _path(value: object) -> str:
    text = _text(value)
    if not text or Path(text).is_absolute():
        return ""
    return text


def _source_path(value: Mapping[str, object]) -> str:
    return _path(value.get("path")) or _path(value.get("raw_path"))


def _severity_rank(value: object) -> int:
    return _SEVERITY_ORDER.get(_severity(value), 0)


def _signal_key(signal: Mapping[str, object]) -> tuple[int, str, str, str]:
    return (
        _severity_rank(signal.get("severity")),
        _text(signal.get("tool")),
        _source_path(signal),
        _text(signal.get("summary")),
    )


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


def _path_parts(path: str) -> tuple[str, ...]:
    return tuple(part for part in Path(path).parts if part not in {".", ""})


def _same_area(path: str, candidate: str) -> bool:
    parts = _path_parts(path)
    candidate_parts = _path_parts(candidate)
    if not parts or not candidate_parts:
        return False
    if path == candidate:
        return True
    if len(parts) >= 2 and len(candidate_parts) >= 2 and parts[:2] == candidate_parts[:2]:
        return True
    return False


def _is_relevant_or_adjacent(path: str, relevant_paths: set[str]) -> bool:
    if not path or not relevant_paths:
        return False
    return any(_same_area(path, candidate) for candidate in relevant_paths)


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



_OBSERVATION_LIMIT = 12
_OBSERVATION_SYMBOL_LIMIT = 8
_OBSERVATION_MATCH_LIMIT = 3


def compact_repository_observations(
    observations: Sequence[Mapping[str, object]],
    *,
    limit: int = _OBSERVATION_LIMIT,
) -> list[dict[str, object]]:
    compacted: list[dict[str, object]] = []
    for observation in observations:
        kind = _text(observation.get("kind"))
        if kind in {"ci", "ci_signal"}:
            continue
        path = _path(observation.get("path"))
        if not path:
            continue
        item: dict[str, object] = {"kind": kind or "repository", "path": path}
        score = observation.get("score")
        if isinstance(score, int) and not isinstance(score, bool):
            item["score"] = score
        terms = [_text(term) for term in _list(observation.get("matched_terms")) if _text(term)]
        if terms:
            item["matched_terms"] = terms[:8]
        symbols = [_text(symbol) for symbol in _list(observation.get("symbols")) if _text(symbol)]
        if symbols:
            item["symbols"] = symbols[:_OBSERVATION_SYMBOL_LIMIT]
        matches = [_text(match) for match in _list(observation.get("matches")) if _text(match)]
        if matches:
            item["matches"] = matches[:_OBSERVATION_MATCH_LIMIT]
        compacted.append(item)
        if len(compacted) >= limit:
            break
    return compacted


def compact_context_pack(value: Mapping[str, object]) -> dict[str, object]:
    compact: dict[str, object] = {
        "schema_version": value.get("schema_version"),
        "kind": value.get("kind"),
        "request": value.get("request"),
        "profile": value.get("profile"),
        "ci_digest": value.get("ci_digest"),
        "git": value.get("git"),
        "explorer_scope": value.get("explorer_scope"),
    }
    knowledge = _list(value.get("knowledge"))[:3]
    if knowledge:
        compact["knowledge"] = knowledge
    related = [dict(item) for item in _object_list(value.get("related_improvements"))[:5]]
    if related:
        compact["related_improvements"] = related
    observations = compact_repository_observations(_object_list(value.get("repository_observations")))
    if observations:
        compact["repository_observations"] = observations
    return {key: item for key, item in compact.items() if item not in (None, [], {})}

def ci_digest_from_artifacts(
    artifacts: ArtifactStore,
    *,
    relevant_paths: set[str] | None = None,
) -> dict[str, object]:
    """Return compact CI context for prompts and PURPOSE/DESIGN handoff."""
    relevant_paths = relevant_paths or set()
    status = _safe_artifact_json(artifacts, "ci-status.json")
    signals_payload = _safe_artifact_json(artifacts, "ci-signals.json")
    raw_signals = [item for item in _list(signals_payload.get("signals")) if isinstance(item, Mapping)]
    provider_summary = {
        name: dict(provider.get("summary", {}))
        for name, provider in signals_payload.get("providers", {}).items()
        if isinstance(name, str) and isinstance(provider, Mapping)
    } if isinstance(signals_payload.get("providers"), Mapping) else {}
    health = _text(signals_payload.get("status")) or "unavailable"
    blocking = [signal for signal in raw_signals if _severity(signal.get("severity")) in {"error", "critical"}]
    relevant = [
        signal for signal in raw_signals
        if _is_relevant_or_adjacent(_source_path(signal), relevant_paths)
    ]
    structural = [
        signal for signal in relevant
        if _text(signal.get("category")) in {"budget", "coupling", "contract", "architecture"}
        or _text(signal.get("tool")) == "check_architecture"
    ]
    security = [
        signal for signal in relevant
        if _text(signal.get("category")) == "security" or _text(signal.get("tool")) == "semgrep"
    ]
    verification = [
        signal for signal in raw_signals
        if _text(signal.get("category")) in {"tests", "test"} or _text(signal.get("tool")) in {"pytest", "unittest"}
    ]
    highlighted = {id(signal) for signal in [*blocking, *relevant]}
    unrelated = [signal for signal in raw_signals if id(signal) not in highlighted]
    digest: dict[str, object] = {
        "schema_version": 1,
        "kind": "ci_digest",
        "health": health,
        "provider_summary": provider_summary,
        "ci_status": {
            "providers": status.get("providers", []),
            "warnings": status.get("warnings", []),
        },
        "signal_count": len(raw_signals),
        "relevant_paths": sorted(relevant_paths),
        "blocking_findings": [_signal_summary(signal) for signal in sorted(blocking, key=_signal_key, reverse=True)[:8]],
        "relevant_findings": [_signal_summary(signal) for signal in sorted(relevant, key=_signal_key, reverse=True)[:10]],
        "structural_refactor_hints": [_signal_summary(signal) for signal in sorted(structural, key=_signal_key, reverse=True)[:8]],
        "security_hints": [_signal_summary(signal) for signal in sorted(security, key=_signal_key, reverse=True)[:8]],
        "verification_hints": [_signal_summary(signal) for signal in sorted(verification, key=_signal_key, reverse=True)[:6]],
        "baseline_noise": {
            "signal_count": len(unrelated),
            "by_tool": _count_by(unrelated, "tool"),
            "by_category": _count_by(unrelated, "category"),
            "by_severity": _count_by(unrelated, "severity"),
            "examples": [_signal_summary(signal) for signal in sorted(unrelated, key=_signal_key, reverse=True)[:5]],
        },
    }
    reason = _text(signals_payload.get("reason"))
    if reason:
        digest["reason"] = reason
    return digest

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


def ci_evidence_from_artifacts(
    artifacts: ArtifactStore,
    *,
    relevant_paths: set[str] | None = None,
) -> list[dict[str, object]]:
    """Return compact canonical evidence derived from normalized CI artifacts."""
    digest = ci_digest_from_artifacts(artifacts, relevant_paths=relevant_paths)
    evidence: list[dict[str, object]] = []
    health = _text(digest.get("health")) or "unavailable"
    signal_count = digest.get("signal_count", 0)
    evidence.append({
        "id": "CI1",
        "kind": "ci",
        "claim": f"CI digest status is {health} with {signal_count} normalized signal(s).",
        "status": "supported" if health in {"ready", "partial"} else "blocked",
        "confidence": "high",
        "severity": "warning" if digest.get("blocking_findings") else "info",
        "sources": [{"type": "artifact", "artifact": "ci-signals.json", "description": "Compacted CI digest from normalized CI signals."}],
    })
    for index, finding in enumerate(digest.get("blocking_findings", [])[:6], start=2):
        if not isinstance(finding, Mapping):
            continue
        evidence.append({
            "id": f"CI{index}",
            "kind": _evidence_kind(finding),
            "claim": _text(finding.get("summary")) or "Blocking CI finding was reported.",
            "status": "supported",
            "confidence": "high",
            "severity": _severity(finding.get("severity")),
            "sources": [{
                "type": "ci",
                "artifact": "ci-signals.json",
                **({"path": _path(finding.get("path"))} if _path(finding.get("path")) else {}),
                "description": f"{_text(finding.get('tool')) or 'CI'} {_text(finding.get('category')) or 'finding'} from compact CI digest.",
            }],
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
        "repository_observations": compact_repository_observations(repository_observations),
        "git": _safe_artifact_json(artifacts, "git-run.json"),
        "ci_status": _safe_artifact_json(artifacts, "ci-status.json"),
        "ci_digest": ci_digest_from_artifacts(
            artifacts,
            relevant_paths=_candidate_paths(repository_observations, related_improvements),
        ),
        "explorer_scope": dict(explorer_scope),
    }
