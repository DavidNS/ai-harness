"""Explore controller-owned artifact builders."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from harness_v2.backend.application.phase_artifacts import explore
from harness_v2.backend.application.phase_artifacts.explore_ci import ci_digest_from_artifacts
from harness_v2.backend.application.phase_artifacts.explore_inputs import decision_history
from harness_v2.backend.application.phase_artifacts.explore_map_builder import ExplorationMapBuilder
from harness_v2.backend.application.phase_artifacts.explore_mappers import (
    compact_repository_observations,
    normalize_exploration_map,
    repair_entry_evidence_refs,
)
from harness_v2.backend.application.phase_artifacts.explore_repository import (
    related_improvements as discover_related_improvements,
    repository_observations as discover_repository_observations,
)
from harness_v2.backend.application.phase_artifacts.explore_utils import (
    _candidate_paths,
    _list,
    _mapping_list,
    _object,
    _object_list,
    _safe_artifact_json,
    _safe_artifact_list,
    _string_items,
    _text,
)
from harness_v2.backend.domain.runs import RunRecord

OUTCOME_BUNDLE_ARTIFACT = explore.OUTCOME_BUNDLE_ARTIFACT
MANIFEST_ARTIFACT = explore.MANIFEST_ARTIFACT

def build_context_pack(
    run: RunRecord,
    profile: dict[str, Any],
    artifacts: Any | None = None,
    *,
    related_improvements: Sequence[Mapping[str, object]] = (),
    repository_observations: Sequence[Mapping[str, object]] = (),
    explorer_scope: Mapping[str, object] | None = None,
    repository_root: Any | None = None,
) -> dict[str, Any]:
    if not related_improvements:
        related_improvements = _safe_artifact_list(
            artifacts,
            run.run_id,
            "explore/related_improvements.json",
            keys=("related_improvements", "items"),
        )
    if not related_improvements and repository_root is not None:
        related_improvements = discover_related_improvements(repository_root, _context_query(run, profile))
    if not repository_observations:
        repository_observations = _safe_artifact_list(
            artifacts,
            run.run_id,
            "explore/repository_observations.json",
            keys=("repository_observations", "observations", "items"),
        )
    if not repository_observations and repository_root is not None:
        repository_observations = discover_repository_observations(repository_root, run.request, profile, related_improvements)
    if explorer_scope is None:
        explorer_scope = _safe_artifact_json(artifacts, run.run_id, "explore/explorer_scope.json")
    compact_observations = compact_repository_observations(repository_observations)
    return {
        "schema_version": 1,
        "kind": "explore_context_pack",
        "request": run.request,
        "profile": dict(profile),
        "request_profile": dict(profile),
        "decision_history": decision_history(run),
        "knowledge": [],
        "related_improvements": [dict(item) for item in related_improvements],
        "repository_observations": compact_observations,
        "git": _safe_artifact_json(artifacts, run.run_id, "git-run.json"),
        "ci_status": _safe_artifact_json(artifacts, run.run_id, "ci-status.json"),
        "ci_digest": ci_digest_from_artifacts(
            artifacts,
            run.run_id,
            relevant_paths=_candidate_paths(compact_observations, related_improvements),
        ),
        "explorer_scope": dict(explorer_scope or {}),
    }

def build_exploration_map(
    digest: dict[str, Any],
    *,
    profile: Mapping[str, object] | None = None,
    context_pack: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    evidence = _object_list(digest.get("evidence"), "evidence")
    context_pack = context_pack or {}
    profile = profile or _object(context_pack.get("profile") or context_pack.get("request_profile") or {}, "profile")
    builder = ExplorationMapBuilder(
        request_understanding={"explicit_constraints": _string_items(profile.get("constraints"))},
        triage={
            "complexity": profile.get("complexity"),
            "ambiguity": profile.get("ambiguity"),
            "risk": profile.get("risk"),
            "evidence_depth": profile.get("evidence_depth"),
        },
        evidence_plan={
            "questions": _string_items(profile.get("evidence_questions")),
            "ci_requirement": "required" if "ci" in _string_items(profile.get("gatherers")) else "not_needed",
        },
        evidence_collection={"evidence": evidence, "blockers": _list(digest.get("blockers"))},
        ci_barrier=_ci_barrier_from_digest(digest, profile),
        evidence_normalization={"evidence": evidence},
        repository_observations=_mapping_list(context_pack.get("repository_observations")),
        related_improvements=_mapping_list(context_pack.get("related_improvements")),
    )
    return normalize_exploration_map(builder.build(), evidence)

def build_outcome_bundle(synthesis: dict[str, Any], digest: dict[str, Any], exploration_map: dict[str, Any]) -> dict[str, Any]:
    evidence = list(_object_list(digest.get("evidence"), "evidence"))
    bundle = dict(synthesis)
    bundle["kind"] = "explore_outcome_bundle"
    bundle["evidence"] = evidence
    bundle["exploration_map"] = exploration_map
    repair_entry_evidence_refs(bundle, evidence)
    return bundle

def build_manifest(bundle: dict[str, Any]) -> dict[str, Any]:
    entries = [_manifest_entry(entry) for entry in _object_list(bundle.get("entries"), "entries")]
    actions = sorted({action for entry in entries if (action := _text(entry.get("action")))})
    targets = _manifest_targets(entries)
    return {
        "schema_version": 1,
        "kind": "explore_manifest",
        "source_artifact": OUTCOME_BUNDLE_ARTIFACT,
        "source_artifacts": [
            explore.OUTCOME_BUNDLE_ARTIFACT,
            explore.EVIDENCE_DIGEST_ARTIFACT,
            explore.EXPLORATION_MAP_ARTIFACT,
        ],
        "status": bundle.get("status"),
        "normalized_request": bundle.get("normalized_request"),
        "primary_entry_id": _text(entries[0].get("id")) if entries else "",
        "actions": actions,
        "targets": targets,
        "decision_ids": [_text(entry.get("decision_id")) for entry in entries if _text(entry.get("decision_id"))],
        "entries": entries,
    }


def build_handoff(bundle: dict[str, Any], manifest: Mapping[str, object] | None = None) -> dict[str, Any]:
    manifest = manifest or build_manifest(bundle)
    return {
        "schema_version": 1,
        "kind": "explore_handoff",
        "source_artifact": OUTCOME_BUNDLE_ARTIFACT,
        "manifest_artifact": MANIFEST_ARTIFACT,
        "status": bundle["status"],
        "normalized_request": bundle["normalized_request"],
        "actions": list(manifest.get("actions", [])) if isinstance(manifest.get("actions"), list) else [],
        "targets": list(manifest.get("targets", [])) if isinstance(manifest.get("targets"), list) else [],
        "entry_summary": list(manifest.get("entries", [])) if isinstance(manifest.get("entries"), list) else [],
        "exploration_map": bundle["exploration_map"],
    }

def _ci_barrier_from_digest(digest: Mapping[str, object], profile: Mapping[str, object]) -> dict[str, object]:
    requirement = "required" if "ci" in _string_items(profile.get("gatherers")) else "not_needed"
    blockers = [str(item) for item in _list(digest.get("blockers")) if isinstance(item, str) and item.strip()]
    if blockers:
        return {"ci_requirement": requirement, "status": "unavailable", "evidence": [], "blockers": blockers}
    return {"ci_requirement": requirement, "status": "ready" if requirement != "not_needed" else "not_needed", "evidence": [], "blockers": []}


def _context_query(run: RunRecord, profile: Mapping[str, object]) -> str:
    parts: list[str] = [run.request]
    for key in ("summary", "request_parts", "evidence_questions", "constraints"):
        value = profile.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value if isinstance(item, str))
    return "\n".join(parts)


def _manifest_entry(entry: Mapping[str, object]) -> dict[str, object]:
    action = _text(entry.get("action"))
    item: dict[str, object] = {
        "id": _text(entry.get("id")),
        "classification": _text(entry.get("classification")),
        "action": action,
        "title": _text(entry.get("title")),
        "evidence_refs": _string_items(entry.get("evidence_refs")),
        "publishability": _publishability(action),
    }
    target = entry.get("target")
    if isinstance(target, Mapping):
        item["target"] = {key: value for key, value in target.items() if key in {"path", "checksum"} and isinstance(value, str) and value.strip()}
    decision_id = _text(entry.get("decision_id"))
    if not decision_id and action == "ask_user":
        decision_id = f"explore-{_text(entry.get('id')) or 'entry'}-decision"
    if decision_id:
        item["decision_id"] = decision_id
    return {key: value for key, value in item.items() if value not in (None, "", [], {})}


def _publishability(action: str) -> str:
    if action == "ask_user":
        return "needs_user_decision"
    if action == "blocked":
        return "blocked"
    if action in {"duplicate_noop", "existing_functionality", "reject"}:
        return "no_implementation"
    return "ready"


def _manifest_targets(entries: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    targets: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        target = entry.get("target")
        if not isinstance(target, Mapping):
            continue
        path = _text(target.get("path"))
        checksum = _text(target.get("checksum"))
        if not path or (path, checksum) in seen:
            continue
        seen.add((path, checksum))
        item: dict[str, object] = {"path": path, "entry_id": _text(entry.get("id")), "action": _text(entry.get("action"))}
        if checksum:
            item["checksum"] = checksum
        targets.append(item)
    return targets
