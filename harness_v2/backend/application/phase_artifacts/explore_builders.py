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

def build_context_pack(
    run: RunRecord,
    profile: dict[str, Any],
    artifacts: Any | None = None,
    *,
    related_improvements: Sequence[Mapping[str, object]] = (),
    repository_observations: Sequence[Mapping[str, object]] = (),
    explorer_scope: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    if not related_improvements:
        related_improvements = _safe_artifact_list(
            artifacts,
            run.run_id,
            "explore/related_improvements.json",
            keys=("related_improvements", "items"),
        )
    if not repository_observations:
        repository_observations = _safe_artifact_list(
            artifacts,
            run.run_id,
            "explore/repository_observations.json",
            keys=("repository_observations", "observations", "items"),
        )
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

def build_handoff(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "explore_handoff",
        "source_artifact": OUTCOME_BUNDLE_ARTIFACT,
        "status": bundle["status"],
        "normalized_request": bundle["normalized_request"],
        "exploration_map": bundle["exploration_map"],
    }

def _ci_barrier_from_digest(digest: Mapping[str, object], profile: Mapping[str, object]) -> dict[str, object]:
    requirement = "required" if "ci" in _string_items(profile.get("gatherers")) else "not_needed"
    blockers = [str(item) for item in _list(digest.get("blockers")) if isinstance(item, str) and item.strip()]
    if blockers:
        return {"ci_requirement": requirement, "status": "unavailable", "evidence": [], "blockers": blockers}
    return {"ci_requirement": requirement, "status": "ready" if requirement != "not_needed" else "not_needed", "evidence": [], "blockers": []}
