"""Explore artifact mappers and normalizers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from harness_v2.backend.application.phase_artifacts.explore_utils import (
    _OBSERVATION_LIMIT,
    _drop_empty_optional_strings,
    _first_unambiguous_path,
    _list,
    _mapping_list,
    _object_list,
    _path,
    _source_paths,
    _string_items,
    _text,
    _valid_evidence_refs,
)

def compact_context_pack(value: Mapping[str, object]) -> dict[str, object]:
    compact: dict[str, object] = {
        "schema_version": value.get("schema_version"),
        "kind": value.get("kind"),
        "request": value.get("request"),
        "profile": value.get("profile") or value.get("request_profile"),
        "ci_digest": value.get("ci_digest"),
        "git": value.get("git"),
        "explorer_scope": value.get("explorer_scope"),
        "decision_history": value.get("decision_history"),
    }
    knowledge = _list(value.get("knowledge"))[:3]
    if knowledge:
        compact["knowledge"] = knowledge
    related = [dict(item) for item in _mapping_list(value.get("related_improvements"))[:5]]
    if related:
        compact["related_improvements"] = related
    observations = compact_repository_observations(_mapping_list(value.get("repository_observations")))
    if observations:
        compact["repository_observations"] = observations
    return {key: item for key, item in compact.items() if item not in (None, [], {})}


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
        source_id = _text(observation.get("id"))
        if source_id:
            item["id"] = source_id
        score = observation.get("score")
        if isinstance(score, int) and not isinstance(score, bool):
            item["score"] = score
        terms = _string_items(observation.get("matched_terms"))
        if terms:
            item["matched_terms"] = terms[:8]
        symbols = _string_items(observation.get("symbols"))
        if symbols:
            item["symbols"] = symbols[:8]
        matches = _string_items(observation.get("matches"))
        if matches:
            item["matches"] = matches[:3]
        snippets = [dict(snippet) for snippet in _mapping_list(observation.get("snippets"))[:3]]
        if snippets:
            item["snippets"] = snippets
        compacted.append(item)
        if len(compacted) >= limit:
            break
    return compacted


def merge_evidence(*groups: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
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
    return [dict(item) for item in _mapping_list(value.get("evidence"))]



def merge_evidence_digest(digest: dict[str, Any], controller_evidence: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    merged = dict(digest)
    merged["evidence"] = merge_evidence(controller_evidence, evidence_from_digest(digest))
    return merged


def normalize_exploration_map(exploration_map: Mapping[str, object], evidence: Sequence[Mapping[str, object]]) -> dict[str, object]:
    evidence_ids = {_text(item.get("id")) for item in evidence if _text(item.get("id"))}
    paths_by_evidence = _source_paths(evidence)
    normalized: dict[str, object] = dict(exploration_map)
    for section in (
        "surfaces", "behaviors", "constraints", "risks", "unknowns", "candidate_work_shapes", "verification_surfaces",
        "existing_functionality", "similar_functionality", "structural_signals", "security_signals",
    ):
        raw_items = normalized.get(section)
        if not isinstance(raw_items, list):
            continue
        items: list[dict[str, object]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, Mapping):
                continue
            item = dict(raw_item)
            for refs_field in ("evidence_refs", "supporting_evidence_refs", "counterevidence_refs"):
                if refs_field in item:
                    item[refs_field] = _valid_evidence_refs(item.get(refs_field), evidence_ids)
            refs = _string_items(item.get("evidence_refs"))
            if not _text(item.get("path")) and refs:
                resolved_path = _first_unambiguous_path(refs, paths_by_evidence)
                if resolved_path:
                    item["path"] = resolved_path
            _drop_empty_optional_strings(item, ("path", "severity", "handoff_phase", "best_resolved_by"))
            items.append(item)
        normalized[section] = items
    return normalized


def repair_entry_evidence_refs(bundle: dict[str, Any], evidence: Sequence[Mapping[str, object]]) -> None:
    evidence_ids = {_text(item.get("id")) for item in evidence if _text(item.get("id"))}
    fallback = next(iter(sorted(evidence_ids)), "")
    if not fallback:
        return
    for entry in _object_list(bundle.get("entries"), "entries"):
        refs = [ref for ref in _string_items(entry.get("evidence_refs")) if ref in evidence_ids]
        entry["evidence_refs"] = refs or [fallback]



def evidence_items(value: Mapping[str, object]) -> list[dict[str, Any]]:
    return _object_list(value.get("evidence"), "evidence")
