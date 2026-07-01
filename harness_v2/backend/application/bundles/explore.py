"""EXPLORE_BUNDLE definition for the v2 SDD bundle registry."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.bundle_orchestration import BundleContext, BundleExecutionResult
from harness_v2.backend.application.decision_service import DecisionRequest
from harness_v2.backend.domain.lifecycle import PhaseName
from harness_v2.backend.domain.runs import RunRecord

EXPLORE_PHASE = PhaseName.EXPLORE_BUNDLE
REQUEST_PROFILE_TASK = "explore_request_profile"
EVIDENCE_DIGEST_TASK = "explore_evidence_digest"
OUTCOME_SYNTHESIS_TASK = "explore_outcome_synthesis"
REQUEST_PROFILE_ARTIFACT = "explore/request_profile.json"
CONTEXT_PACK_ARTIFACT = "explore/context_pack.json"
EVIDENCE_DIGEST_ARTIFACT = "explore/evidence_digest.json"
EXPLORATION_MAP_ARTIFACT = "explore/exploration_map.json"
OUTCOME_SYNTHESIS_ARTIFACT = "explore/outcome_synthesis.json"
OUTCOME_BUNDLE_ARTIFACT = "explore/outcome_bundle.json"
HANDOFF_ARTIFACT = "published/explore-handoff.json"
CLARIFICATION_DECISION_ID = "EXPLORE_BUNDLE-clarification"

ExploreValidationError = BundleValidationError

_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2, "critical": 3}
_EVIDENCE_KINDS = {"code", "test", "documentation", "knowledge", "ci", "git", "structure", "security", "scope", "external"}
_CLAIM_STATUSES = {"supported", "contradicted", "partial", "partially_supported", "unresolved", "not_applicable", "blocked"}
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
_HANDOFF_PHASES = {"purpose", "design", "tasks"}
_SURFACE_KINDS = {
    "implementation_surface",
    "test_surface",
    "documentation_surface",
    "ci_surface",
    "repository_surface",
    "security_surface",
    "performance_surface",
    "data_surface",
    "integration_surface",
}
_BEHAVIOR_STATUSES = {"observed", "not_observed", "partially_observed", "contradicted", "unresolved", "not_applicable"}
_OBSERVATION_LIMIT = 12
_SIGNAL_LIMIT = 8
_HANDOFF_LIMIT = 8


@dataclass(frozen=True, slots=True)
class ExploreBundleDefinition:
    phase: PhaseName = EXPLORE_PHASE
    failure_code: str = "EXPLORE_BUNDLE_FAILED"

    def execute(self, context: BundleContext) -> BundleExecutionResult:
        run = context.run
        profile = context.artifacts.ensure_worker_json(
            run,
            self.phase,
            REQUEST_PROFILE_TASK,
            REQUEST_PROFILE_ARTIFACT,
            {
                "request": run.request,
                "knowledge": [],
                "repository": {},
                "explorer_scope": {},
                "decision_history": _decision_history(run),
            },
            validate_request_profile,
        )
        if _needs_clarification(profile) and not _has_phase_decision(run):
            questions = "; ".join(_string_list(profile.get("clarification_questions"), "clarification_questions"))
            waiting = context.decision_service.execute(
                DecisionRequest(run.run_id, CLARIFICATION_DECISION_ID, questions)
            )
            return BundleExecutionResult(waiting=waiting)

        context_pack = context.artifacts.ensure_controller_json(
            run.run_id,
            CONTEXT_PACK_ARTIFACT,
            lambda: build_context_pack(run, profile, context.artifacts),
            validate_context_pack,
        )
        compact_pack = compact_context_pack(context_pack)
        controller_evidence = ci_evidence_from_artifacts(
            context.artifacts,
            run.run_id,
            relevant_paths=_candidate_paths(
                _object_list(context_pack.get("repository_observations", []), "repository_observations"),
                _object_list(context_pack.get("related_improvements", []), "related_improvements"),
            ),
        )
        digest = context.artifacts.ensure_worker_json(
            run,
            self.phase,
            EVIDENCE_DIGEST_TASK,
            EVIDENCE_DIGEST_ARTIFACT,
            {"request_profile": profile, "context_pack": compact_pack, "controller_evidence": controller_evidence},
            validate_evidence_digest,
        )
        digest = merge_evidence_digest(digest, controller_evidence)
        validate_evidence_digest(digest)
        context.artifacts.write_json(run.run_id, EVIDENCE_DIGEST_ARTIFACT, digest)
        exploration_map = context.artifacts.ensure_controller_json(
            run.run_id,
            EXPLORATION_MAP_ARTIFACT,
            lambda: build_exploration_map(digest, profile=profile, context_pack=context_pack),
            lambda value: validate_exploration_map(value, _evidence_ids(digest)),
        )
        synthesis = context.artifacts.ensure_worker_json(
            run,
            self.phase,
            OUTCOME_SYNTHESIS_TASK,
            OUTCOME_SYNTHESIS_ARTIFACT,
            {
                "request": run.request,
                "request_profile": profile,
                "context_pack": compact_pack,
                "evidence": _object_list(digest.get("evidence"), "evidence"),
                "exploration_map": exploration_map,
            },
            validate_outcome_synthesis,
        )
        bundle = context.artifacts.ensure_controller_json(
            run.run_id,
            OUTCOME_BUNDLE_ARTIFACT,
            lambda: build_outcome_bundle(synthesis, digest, exploration_map),
            validate_outcome_bundle,
        )
        context.artifacts.ensure_controller_json(
            run.run_id,
            HANDOFF_ARTIFACT,
            lambda: build_handoff(bundle),
            validate_handoff,
        )
        return BundleExecutionResult()


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
        "decision_history": _decision_history(run),
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
        compacted.append(item)
        if len(compacted) >= limit:
            break
    return compacted


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


class ExplorationMapBuilder:
    def __init__(
        self,
        *,
        request_understanding: Mapping[str, object],
        triage: Mapping[str, object],
        evidence_plan: Mapping[str, object],
        evidence_collection: Mapping[str, object],
        ci_barrier: Mapping[str, object],
        evidence_normalization: Mapping[str, object],
        repository_observations: Sequence[Mapping[str, object]],
        related_improvements: Sequence[Mapping[str, object]],
    ) -> None:
        self._request_understanding = request_understanding
        self._triage = triage
        self._evidence_plan = evidence_plan
        self._evidence_collection = evidence_collection
        self._ci_barrier = ci_barrier
        self._evidence_normalization = evidence_normalization
        self._repository_observations = repository_observations
        self._related_improvements = related_improvements

    def build(self) -> dict[str, object]:
        evidence = _mapping_list(self._evidence_normalization.get("evidence", []))
        paths_by_evidence = _source_paths(evidence)
        surfaces = self._surfaces(paths_by_evidence)[:16]
        behaviors = self._behaviors(evidence)[:20]
        constraints = self._constraints()
        risks = self._risks(evidence, paths_by_evidence)[:12]
        unknowns = self._unknowns(evidence)
        verification = self._verification_surfaces(surfaces, risks)[:12]
        work_shapes = self._candidate_work_shapes(risks, unknowns, surfaces)
        structural_signals = self._signals_by_kind(risks, "coupling")[:_SIGNAL_LIMIT]
        security_signals = self._signals_by_kind(risks, "security")[:_SIGNAL_LIMIT]
        return {
            "schema_version": 1,
            "kind": "exploration_map",
            "surfaces": surfaces,
            "behaviors": behaviors,
            "constraints": constraints,
            "risks": risks,
            "unknowns": unknowns,
            "candidate_work_shapes": work_shapes,
            "verification_surfaces": verification,
            "existing_functionality": [],
            "similar_functionality": [],
            "structural_signals": structural_signals,
            "security_signals": security_signals,
            "handoff_notes": self._handoff_notes(unknowns, risks, verification),
        }

    def _surfaces(self, paths_by_evidence: Mapping[str, list[str]]) -> list[dict[str, object]]:
        surfaces: list[dict[str, object]] = []
        seen_paths: set[str] = set()
        counter = 1
        for observation in self._repository_observations:
            path = _path(observation.get("path"))
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            surfaces.append({
                "id": f"S{counter}",
                "kind": _surface_kind(observation),
                "path": path,
                "symbols": _string_items(observation.get("symbols")),
                "why_relevant": _surface_reason(observation),
                "evidence_refs": [],
                "confidence": "high" if isinstance(observation.get("score"), int) and int(observation["score"]) >= 20 else "medium",
            })
            counter += 1
        for evidence_id, paths in paths_by_evidence.items():
            for path in paths:
                if not path or path in seen_paths:
                    continue
                seen_paths.add(path)
                surfaces.append({
                    "id": f"S{counter}",
                    "kind": "test_surface" if path.startswith("tests/") else "implementation_surface",
                    "path": path,
                    "symbols": [],
                    "why_relevant": f"Referenced by normalized evidence {evidence_id}.",
                    "evidence_refs": [evidence_id],
                    "confidence": "medium",
                })
                counter += 1
        return surfaces

    @staticmethod
    def _behaviors(evidence: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        status_map = {
            "supported": "observed",
            "partially_supported": "partially_observed",
            "contradicted": "contradicted",
            "unresolved": "unresolved",
            "partial": "partially_observed",
            "blocked": "unresolved",
            "not_applicable": "not_applicable",
        }
        return [{
            "id": f"B{index}",
            "status": status_map.get(_text(item.get("status")), "unresolved"),
            "text": _text(item.get("claim")) or "Evidence item did not include a claim.",
            "evidence_refs": [_text(item.get("id"))] if _text(item.get("id")) else [],
        } for index, item in enumerate(evidence, start=1)]

    @staticmethod
    def _signals_by_kind(risks: Sequence[Mapping[str, object]], kind: str) -> list[dict[str, object]]:
        signals: list[dict[str, object]] = []
        for index, risk in enumerate([item for item in risks if _text(item.get("kind")) == kind], start=1):
            signals.append({
                "id": f"SS{index}" if kind == "coupling" else f"SEC{index}",
                "kind": kind,
                "text": _text(risk.get("text")),
                "severity": _text(risk.get("severity")) or "medium",
                "evidence_refs": _string_items(risk.get("evidence_refs")),
            })
        return signals

    def _constraints(self) -> list[dict[str, object]]:
        constraints: list[dict[str, object]] = []
        for index, item in enumerate(_string_items(self._request_understanding.get("explicit_constraints")), start=1):
            constraints.append({"id": f"C{index}", "kind": "request", "text": item, "evidence_refs": []})
        ci_requirement = _text(self._evidence_plan.get("ci_requirement"))
        if ci_requirement and ci_requirement != "not_needed":
            constraints.append({"id": f"C{len(constraints) + 1}", "kind": "ci", "text": f"CI evidence requirement is {ci_requirement}.", "evidence_refs": []})
        for blocker in _string_items(self._ci_barrier.get("blockers")):
            constraints.append({"id": f"C{len(constraints) + 1}", "kind": "operational", "text": blocker, "evidence_refs": []})
        return constraints

    @staticmethod
    def _risks(evidence: Sequence[Mapping[str, object]], paths_by_evidence: Mapping[str, list[str]]) -> list[dict[str, object]]:
        risks: list[dict[str, object]] = []
        for item in evidence:
            claim = _text(item.get("claim"))
            kind = _risk_kind(claim)
            if kind is None:
                continue
            evidence_refs = [_text(item.get("id"))] if _text(item.get("id")) else []
            risk: dict[str, object] = {
                "id": f"K{len(risks) + 1}",
                "kind": kind,
                "text": claim,
                "severity": _confidence(item.get("confidence")),
                "evidence_refs": evidence_refs,
            }
            resolved_path = _first_unambiguous_path(evidence_refs, paths_by_evidence)
            if resolved_path:
                risk["path"] = resolved_path
            _append_unique(risks, risk)
        return risks

    @staticmethod
    def _unknowns(evidence: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        unknowns: list[dict[str, object]] = []
        for item in evidence:
            status = _text(item.get("status"))
            if status not in {"unresolved", "blocked", "partially_supported"}:
                continue
            unknowns.append({
                "id": f"U{len(unknowns) + 1}",
                "text": _text(item.get("claim")) or "Evidence remained unresolved.",
                "best_resolved_by": "design" if status == "partially_supported" else "purpose",
                "evidence_refs": [_text(item.get("id"))] if _text(item.get("id")) else [],
            })
        return unknowns

    @staticmethod
    def _verification_surfaces(surfaces: Sequence[Mapping[str, object]], risks: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        verification: list[dict[str, object]] = []
        for surface in surfaces:
            if _text(surface.get("kind")) == "test_surface":
                verification.append({
                    "id": f"V{len(verification) + 1}",
                    "kind": "existing_test_surface",
                    "path": _text(surface.get("path")),
                    "text": "Existing test-related surface may verify the change.",
                    "evidence_refs": _string_items(surface.get("evidence_refs")),
                })
        for risk in risks:
            kind = _text(risk.get("kind"))
            if kind == "performance":
                text = "Capture a before/after performance baseline if this surface is changed."
            elif kind == "security":
                text = "Include security-sensitive negative coverage for this surface."
            elif kind == "regression":
                text = "Add or update regression coverage for this behavior."
            else:
                continue
            item: dict[str, object] = {"id": f"V{len(verification) + 1}", "kind": f"{kind}_verification", "text": text, "evidence_refs": _string_items(risk.get("evidence_refs"))}
            path = _text(risk.get("path"))
            if path:
                item["path"] = path
            verification.append(item)
        return verification

    @staticmethod
    def _candidate_work_shapes(risks: Sequence[Mapping[str, object]], unknowns: Sequence[Mapping[str, object]], surfaces: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        shapes = _shape_from_risks(risks)
        if unknowns:
            shapes.append("investigation_needed")
        if surfaces and "direct_change" not in shapes:
            shapes.append("direct_change")
        if not surfaces:
            shapes.append("investigation_needed")
        result: list[dict[str, object]] = []
        for shape in dict.fromkeys(item for item in shapes if item in _WORK_SHAPES):
            result.append({
                "id": f"W{len(result) + 1}",
                "shape": shape,
                "description": shape.replace("_", " "),
                "supporting_evidence_refs": [],
                "counterevidence_refs": [],
                "handoff_phase": "design" if shape != "investigation_needed" else "purpose",
            })
        return result

    @staticmethod
    def _handoff_notes(unknowns: Sequence[Mapping[str, object]], risks: Sequence[Mapping[str, object]], verification: Sequence[Mapping[str, object]]) -> dict[str, list[str]]:
        return {
            "purpose": [_text(item.get("text")) for item in unknowns if _text(item.get("best_resolved_by")) == "purpose"][:_HANDOFF_LIMIT],
            "design": [
                *[_text(item.get("text")) for item in unknowns if _text(item.get("best_resolved_by")) == "design"],
                *[_text(item.get("text")) for item in risks],
            ][:_HANDOFF_LIMIT],
            "tasks": [_text(item.get("text")) for item in verification][:_HANDOFF_LIMIT],
        }


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


def build_outcome_bundle(synthesis: dict[str, Any], digest: dict[str, Any], exploration_map: dict[str, Any]) -> dict[str, Any]:
    evidence = list(_object_list(digest.get("evidence"), "evidence"))
    bundle = dict(synthesis)
    bundle["kind"] = "explore_outcome_bundle"
    bundle["evidence"] = evidence
    bundle["exploration_map"] = exploration_map
    repair_entry_evidence_refs(bundle, evidence)
    return bundle


def repair_entry_evidence_refs(bundle: dict[str, Any], evidence: Sequence[Mapping[str, object]]) -> None:
    evidence_ids = {_text(item.get("id")) for item in evidence if _text(item.get("id"))}
    fallback = next(iter(sorted(evidence_ids)), "")
    if not fallback:
        return
    for entry in _object_list(bundle.get("entries"), "entries"):
        refs = [ref for ref in _string_items(entry.get("evidence_refs")) if ref in evidence_ids]
        entry["evidence_refs"] = refs or [fallback]


def build_handoff(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "explore_handoff",
        "source_artifact": OUTCOME_BUNDLE_ARTIFACT,
        "status": bundle["status"],
        "normalized_request": bundle["normalized_request"],
        "exploration_map": bundle["exploration_map"],
    }


def validate_request_profile(value: dict[str, Any]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_equal(value, "phase", REQUEST_PROFILE_TASK)
    for field in ("summary", "request_type", "complexity", "ambiguity", "risk", "evidence_depth"):
        _require_text(value.get(field), field)
    for field in ("request_parts", "constraints", "evidence_questions", "gatherers", "clarification_questions"):
        _string_list(value.get(field), field)


def validate_context_pack(value: dict[str, Any]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_equal(value, "kind", "explore_context_pack")
    _require_text(value.get("request"), "request")
    validate_request_profile(_object(value.get("profile") or value.get("request_profile"), "profile"))
    _object_list(value.get("decision_history"), "decision_history")
    _object(value.get("ci_digest"), "ci_digest")
    _object(value.get("git"), "git")
    _object(value.get("explorer_scope"), "explorer_scope")


def validate_evidence_digest(value: dict[str, Any]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_equal(value, "phase", EVIDENCE_DIGEST_TASK)
    _validate_evidence_items(value.get("evidence"), "evidence", allow_empty=True)
    blockers = value.get("blockers", [])
    if isinstance(blockers, list):
        for blocker in blockers:
            if isinstance(blocker, str):
                _require_text(blocker, "blocker")
            elif isinstance(blocker, dict):
                _require_text(blocker.get("reason"), "blocker reason")
            else:
                raise BundleValidationError("blockers must contain strings or objects")
    else:
        raise BundleValidationError("blockers must be a list")


def validate_exploration_map(value: dict[str, Any], evidence_ids: set[str]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_equal(value, "kind", "exploration_map")
    for field in ("surfaces", "behaviors", "constraints", "risks", "unknowns", "candidate_work_shapes", "verification_surfaces", "existing_functionality", "similar_functionality", "structural_signals", "security_signals"):
        _object_list(value.get(field), field)
    for surface in _object_list(value.get("surfaces"), "surfaces"):
        _require_text(surface.get("id"), "surface id")
        _enum(_require_text(surface.get("kind"), "surface kind"), "surface kind", _SURFACE_KINDS)
        _require_text(surface.get("why_relevant"), "surface why_relevant")
        _validate_refs(_string_list(surface.get("evidence_refs", []), "surface evidence_refs"), evidence_ids)
    for behavior in _object_list(value.get("behaviors"), "behaviors"):
        _require_text(behavior.get("id"), "behavior id")
        _enum(_require_text(behavior.get("status"), "behavior status"), "behavior status", _BEHAVIOR_STATUSES)
        _require_text(behavior.get("text"), "behavior text")
        _validate_refs(_string_list(behavior.get("evidence_refs", []), "behavior evidence_refs"), evidence_ids)
    for item in _object_list(value.get("constraints"), "constraints"):
        _require_text(item.get("id"), "constraint id")
        _require_text(item.get("kind"), "constraint kind")
        _require_text(item.get("text"), "constraint text")
        _validate_refs(_string_list(item.get("evidence_refs", []), "constraint evidence_refs"), evidence_ids)
    for item in _object_list(value.get("risks"), "risks"):
        _require_text(item.get("id"), "risk id")
        _require_text(item.get("kind"), "risk kind")
        _require_text(item.get("text"), "risk text")
        _validate_refs(_string_list(item.get("evidence_refs", []), "risk evidence_refs"), evidence_ids)
    for item in _object_list(value.get("unknowns"), "unknowns"):
        _require_text(item.get("id"), "unknown id")
        _require_text(item.get("text"), "unknown text")
        phase = _optional_text(item.get("best_resolved_by"), "unknown best_resolved_by")
        if phase is not None and phase not in _HANDOFF_PHASES:
            raise BundleValidationError("unknown best_resolved_by is invalid")
        _validate_refs(_string_list(item.get("evidence_refs", []), "unknown evidence_refs"), evidence_ids)
    for item in _object_list(value.get("candidate_work_shapes"), "candidate_work_shapes"):
        _require_text(item.get("id"), "work shape id")
        _enum(_require_text(item.get("shape"), "candidate shape"), "candidate shape", _WORK_SHAPES)
        _require_text(item.get("description"), "work shape description")
        _validate_refs(_string_list(item.get("supporting_evidence_refs", []), "supporting_evidence_refs"), evidence_ids)
        _validate_refs(_string_list(item.get("counterevidence_refs", []), "counterevidence_refs"), evidence_ids)
        phase = _optional_text(item.get("handoff_phase"), "work shape handoff_phase")
        if phase is not None and phase not in _HANDOFF_PHASES:
            raise BundleValidationError("work shape handoff_phase is invalid")
    for item in _object_list(value.get("verification_surfaces"), "verification_surfaces"):
        _require_text(item.get("id"), "verification id")
        _require_text(item.get("kind"), "verification kind")
        _require_text(item.get("text"), "verification text")
        _validate_refs(_string_list(item.get("evidence_refs", []), "verification evidence_refs"), evidence_ids)
    handoff = _object(value.get("handoff_notes"), "handoff_notes")
    for phase in _HANDOFF_PHASES:
        _string_list(handoff.get(phase, []), f"handoff_notes {phase}")


def validate_outcome_synthesis(value: dict[str, Any]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_equal(value, "kind", "explore_outcome_synthesis")
    if "evidence" in value or "exploration_map" in value:
        raise BundleValidationError("outcome synthesis must not contain controller-owned fields")
    _require_text(value.get("status"), "status")
    _object(value.get("normalized_request"), "normalized_request")
    _object(value.get("triage"), "triage")
    for entry in _object_list(value.get("entries"), "entries"):
        _require_text(entry.get("id"), "entry id")
        _require_text(entry.get("classification"), "entry classification")
        _require_text(entry.get("title"), "entry title")
        _string_list(entry.get("evidence_refs"), "entry evidence refs")


def validate_outcome_bundle(value: dict[str, Any]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_equal(value, "kind", "explore_outcome_bundle")
    _validate_evidence_items(value.get("evidence"), "evidence", allow_empty=True)
    evidence_ids = _evidence_ids(value)
    validate_exploration_map(_object(value.get("exploration_map"), "exploration_map"), evidence_ids)
    _require_text(value.get("status"), "status")
    _object(value.get("normalized_request"), "normalized_request")
    _object(value.get("triage"), "triage")
    for entry in _object_list(value.get("entries"), "entries"):
        _validate_refs(_string_list(entry.get("evidence_refs"), "entry evidence refs"), evidence_ids)


def validate_handoff(value: dict[str, Any]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_equal(value, "kind", "explore_handoff")
    _require_equal(value, "source_artifact", OUTCOME_BUNDLE_ARTIFACT)
    _require_text(value.get("status"), "status")
    _object(value.get("normalized_request"), "normalized_request")
    _object(value.get("exploration_map"), "exploration_map")


def _validate_evidence_items(value: object, field: str, *, allow_empty: bool) -> list[dict[str, Any]]:
    evidence = _object_list(value, field)
    if not allow_empty and not evidence:
        raise BundleValidationError(f"{field} must not be empty")
    seen: set[str] = set()
    for item in evidence:
        evidence_id = _require_text(item.get("id"), f"{field} id")
        if evidence_id in seen:
            raise BundleValidationError(f"{field} ids must be unique")
        seen.add(evidence_id)
        _enum(_require_text(item.get("kind"), f"{field} kind"), f"{field} kind", _EVIDENCE_KINDS)
        _require_text(item.get("claim"), f"{field} claim")
        _enum(_require_text(item.get("status"), f"{field} status"), f"{field} status", _CLAIM_STATUSES)
        _require_text(item.get("confidence"), f"{field} confidence")
        _require_text(item.get("severity"), f"{field} severity")
        _object_list(item.get("sources"), f"{field} sources")
    return evidence


def _ci_barrier_from_digest(digest: Mapping[str, object], profile: Mapping[str, object]) -> dict[str, object]:
    requirement = "required" if "ci" in _string_items(profile.get("gatherers")) else "not_needed"
    blockers = [str(item) for item in _list(digest.get("blockers")) if isinstance(item, str) and item.strip()]
    if blockers:
        return {"ci_requirement": requirement, "status": "unavailable", "evidence": [], "blockers": blockers}
    return {"ci_requirement": requirement, "status": "ready" if requirement != "not_needed" else "not_needed", "evidence": [], "blockers": []}


def _needs_clarification(profile: dict[str, Any]) -> bool:
    return bool(_string_list(profile.get("clarification_questions"), "clarification_questions"))


def _has_phase_decision(run: RunRecord) -> bool:
    return any(decision.origin_phase is EXPLORE_PHASE for decision in run.decision_history)


def _decision_history(run: RunRecord) -> list[dict[str, str]]:
    return [{"decision_id": decision.decision_id, "origin_phase": decision.origin_phase.value, "prompt": decision.prompt, "response": decision.response, "created_at": decision.created_at, "answered_at": decision.answered_at} for decision in run.decision_history]


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


def _require_equal(value: dict[str, Any], field: str, expected: object) -> None:
    if value.get(field) != expected:
        raise BundleValidationError(f"{field} must be {expected!r}")


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BundleValidationError(f"{field} is required")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field)


def _enum(value: str, field: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise BundleValidationError(f"{field} is invalid")
    return value


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


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise BundleValidationError(f"{field} must be a list of nonempty strings")
    normalized = tuple(item.strip() for item in value)
    if len(normalized) != len(set(normalized)):
        raise BundleValidationError(f"{field} must not contain duplicates")
    return normalized


def _string_items(value: object) -> list[str]:
    return [_text(item) for item in _list(value) if _text(item)]


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
