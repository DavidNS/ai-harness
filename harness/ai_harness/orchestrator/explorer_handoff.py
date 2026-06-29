"""Build structured Explorer handoff artifacts for downstream SDD phases."""

from __future__ import annotations

import re
from collections.abc import Mapping

from ..canonical import checksum
from ..control_outputs import ExplorerBundle

_TITLE_LIMIT = 120


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _object_list(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def sanitize_manifest_title(title: object, *, content: object = None, fallback: str = "Explorer artifact") -> str:
    text = _text(title)
    if not text and isinstance(content, str):
        first_line = content.replace("\r\n", "\n").splitlines()[0].strip() if content else ""
        text = first_line.lstrip("# ").strip()
    text = re.sub(r"\s+", " ", text or fallback).strip()
    if len(text) <= _TITLE_LIMIT:
        return text
    return text[: _TITLE_LIMIT - 1].rstrip(" .,;:") + "..."


def _selected_direction(discovery: Mapping[str, object], decision: Mapping[str, object]) -> Mapping[str, object]:
    selected = _text(decision.get("selected_direction"))
    for direction in _object_list(discovery.get("candidate_directions")):
        if _text(direction.get("id")) == selected:
            return direction
    return {}


def _unknowns(discovery: Mapping[str, object], decision: Mapping[str, object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for claim in _object_list(discovery.get("claims")):
        if claim.get("status") == "unresolved":
            result.append({
                "id": f"U{len(result) + 1}",
                "claim_id": _text(claim.get("id")),
                "text": _text(claim.get("unresolved_reason")) or _text(claim.get("evidence")),
            })
    for item in _strings(decision.get("counterevidence")):
        result.append({"id": f"U{len(result) + 1}", "text": item})
    return result


def _risks(discovery: Mapping[str, object]) -> list[dict[str, object]]:
    risks: list[dict[str, object]] = []
    for finding in _object_list(discovery.get("critic_findings")):
        severity = _text(finding.get("severity")) or "warning"
        if severity not in {"blocker", "warning"}:
            continue
        risks.append({
            "id": f"R{len(risks) + 1}",
            "direction_id": _text(finding.get("direction_id")),
            "severity": severity,
            "text": _text(finding.get("finding")),
            "recommendation": _text(finding.get("recommendation")),
        })
    return risks


def _candidate_work_shapes(discovery: Mapping[str, object], decision: Mapping[str, object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    selected = _text(decision.get("selected_direction"))
    for direction in _object_list(discovery.get("candidate_directions")):
        result.append({
            "id": f"W{len(result) + 1}",
            "direction_id": _text(direction.get("id")),
            "selected": _text(direction.get("id")) == selected,
            "title": sanitize_manifest_title(direction.get("title")),
            "mechanism": _text(direction.get("mechanism")),
            "behavioral_delta": _text(direction.get("behavioral_delta")),
            "evidence": _strings(direction.get("evidence")),
        })
    return result


def _verification_surfaces(decision: Mapping[str, object], evidence_trace: list[object]) -> list[dict[str, object]]:
    surfaces: list[dict[str, object]] = []
    minimum = _text(decision.get("minimum_verification"))
    if minimum:
        surfaces.append({"id": "V1", "kind": "minimum_verification", "text": minimum})
    for item in _object_list(evidence_trace):
        path = _text(item.get("path"))
        if not path.startswith("tests/"):
            continue
        surfaces.append({
            "id": f"V{len(surfaces) + 1}",
            "kind": "existing_test_surface",
            "path": path,
            "text": _text(item.get("excerpt")),
            "evidence_trace_id": _text(item.get("id")),
        })
    return surfaces


def build_explorer_handoff(
    *,
    bundle: ExplorerBundle,
    records: list[dict[str, object]],
    discovery: Mapping[str, object],
    decision: Mapping[str, object],
    pre_distilled_content: Mapping[str, str] | None,
) -> dict[str, object]:
    content_by_entry = {
        entry.entry_id: (
            pre_distilled_content[entry.entry_id]
            if pre_distilled_content is not None and entry.entry_id in pre_distilled_content
            else entry.content
        )
        for entry in bundle.entries
    }
    entries: list[dict[str, object]] = []
    for record in records:
        entry_id = _text(record.get("entry_id"))
        content = content_by_entry.get(entry_id)
        item = dict(record)
        if isinstance(content, str) and content:
            item["content"] = content
            item["checksum"] = checksum(content)
            item["bytes"] = len(content.encode("utf-8"))
            item["title"] = sanitize_manifest_title(item.get("title"), content=content)
        else:
            item["title"] = sanitize_manifest_title(item.get("title"))
        entries.append(item)
    evidence_trace = list(discovery.get("evidence_trace", [])) if isinstance(discovery.get("evidence_trace"), list) else []
    selected_direction = _selected_direction(discovery, decision)
    return {
        "schema_version": 1,
        "kind": "explorer_handoff",
        "primary_entry": bundle.primary_entry,
        "selected_direction": dict(selected_direction) if selected_direction else {},
        "decision": {
            "outcome": decision.get("outcome"),
            "selected_direction": decision.get("selected_direction"),
            "rationale": decision.get("rationale"),
            "value_hypothesis": decision.get("value_hypothesis"),
            "behavioral_delta": decision.get("behavioral_delta"),
            "rejected_alternatives": decision.get("rejected_alternatives", []),
            "falsifying_conditions": decision.get("falsifying_conditions", []),
            "minimum_verification": decision.get("minimum_verification"),
        },
        "entries": entries,
        "evidence_trace": evidence_trace,
        "duplicate_search": discovery.get("duplicate_search", {}),
        "unknowns": _unknowns(discovery, decision),
        "risks": _risks(discovery),
        "candidate_work_shapes": _candidate_work_shapes(discovery, decision),
        "verification_surfaces": _verification_surfaces(decision, evidence_trace),
    }
