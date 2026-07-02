"""Explore CI signal mappers."""

from __future__ import annotations

from collections.abc import Mapping

from harness_v2.backend.application.phase_artifacts.explore_utils import (
    _count_by,
    _evidence_kind,
    _is_relevant_or_adjacent,
    _list,
    _mapping_list,
    _path,
    _safe_artifact_json,
    _severity,
    _signal_key,
    _signal_summary,
    _source_path,
    _text,
)

def ci_digest_from_artifacts(
    artifacts: Any | None,
    run_id: str,
    *,
    relevant_paths: set[str] | None = None,
) -> dict[str, object]:
    relevant_paths = relevant_paths or set()
    status = _safe_artifact_json(artifacts, run_id, "ci-status.json")
    signals_payload = _safe_artifact_json(artifacts, run_id, "ci-signals.json")
    raw_signals = [item for item in _list(signals_payload.get("signals")) if isinstance(item, Mapping)]
    providers = signals_payload.get("providers")
    provider_summary = {
        name: dict(provider.get("summary", {}))
        for name, provider in providers.items()
        if isinstance(name, str) and isinstance(provider, Mapping)
    } if isinstance(providers, Mapping) else {}
    health = _text(signals_payload.get("status")) or "unavailable"
    blocking = [signal for signal in raw_signals if _severity(signal.get("severity")) in {"error", "critical"}]
    relevant = [signal for signal in raw_signals if _is_relevant_or_adjacent(_source_path(signal), relevant_paths)]
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
        "ci_status": {"providers": status.get("providers", []), "warnings": status.get("warnings", [])},
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

def ci_evidence_from_artifacts(
    artifacts: Any | None,
    run_id: str,
    *,
    relevant_paths: set[str] | None = None,
) -> list[dict[str, object]]:
    digest = ci_digest_from_artifacts(artifacts, run_id, relevant_paths=relevant_paths)
    evidence: list[dict[str, object]] = []
    health = _text(digest.get("health")) or "unavailable"
    signal_count = digest.get("signal_count", 0)
    if health != "unavailable" or signal_count:
        evidence.append({
            "id": "CI1",
            "kind": "ci",
            "claim": f"CI digest status is {health} with {signal_count} normalized signal(s).",
            "status": "supported" if health in {"ready", "partial"} else "blocked",
            "confidence": "high",
            "severity": "warning" if digest.get("blocking_findings") else "info",
            "sources": [{"type": "artifact", "artifact": "ci-signals.json", "description": "Compacted CI digest from normalized CI signals."}],
        })
    for index, finding in enumerate(_mapping_list(digest.get("blocking_findings"))[:6], start=2):
        source = {"type": "ci", "artifact": "ci-signals.json", "description": f"{_text(finding.get('tool')) or 'CI'} {_text(finding.get('category')) or 'finding'} from compact CI digest."}
        path = _path(finding.get("path"))
        if path:
            source["path"] = path
        evidence.append({
            "id": f"CI{index}",
            "kind": _evidence_kind(finding),
            "claim": _text(finding.get("summary")) or "Blocking CI finding was reported.",
            "status": "supported",
            "confidence": "high",
            "severity": _severity(finding.get("severity")),
            "sources": [source],
        })
    return evidence
