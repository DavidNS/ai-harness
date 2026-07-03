"""Explore exploration-map builder."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from harness_v2.backend.application.phase_artifacts.explore_utils import (
    _HANDOFF_LIMIT,
    _SIGNAL_LIMIT,
    _WORK_SHAPES,
    _append_unique,
    _confidence,
    _first_unambiguous_path,
    _mapping_list,
    _path,
    _risk_kind,
    _shape_from_risks,
    _source_paths,
    _string_items,
    _surface_kind,
    _surface_reason,
    _text,
)


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
        existing_functionality = self._existing_functionality()[:8]
        similar_functionality = self._similar_functionality(existing_functionality)[:8]
        duplicate_search = self._duplicate_search(existing_functionality, similar_functionality)
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
            "existing_functionality": existing_functionality,
            "similar_functionality": similar_functionality,
            "duplicate_search": duplicate_search,
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

    def _existing_functionality(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for observation in self._repository_observations:
            path = _path(observation.get("path"))
            if not path:
                continue
            kind = _text(observation.get("kind")).casefold()
            score = observation.get("score")
            score_value = score if isinstance(score, int) and not isinstance(score, bool) else 0
            matches = _string_items(observation.get("matches"))
            symbols = _string_items(observation.get("symbols"))
            if kind not in {"source", "test"} and not symbols:
                continue
            if score_value < 10 and not matches:
                continue
            item: dict[str, object] = {
                "id": f"EF{len(items) + 1}",
                "kind": kind or "repository",
                "path": path,
                "summary": matches[0] if matches else _surface_reason(observation),
                "confidence": "high" if score_value >= 20 or symbols else "medium",
                "evidence_refs": [],
            }
            if score_value:
                item["score"] = score_value
            source_id = _text(observation.get("id"))
            if source_id:
                item["source_id"] = source_id
                item["source_kind"] = "repository_observation"
            if symbols:
                item["symbols"] = symbols[:8]
            items.append(item)
        return items

    def _similar_functionality(self, existing: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        existing_paths = {_text(item.get("path")) for item in existing}
        for related in self._related_improvements:
            path = _path(related.get("path"))
            summary = _text(related.get("summary"))
            if not path and not summary:
                continue
            item: dict[str, object] = {
                "id": f"SF{len(items) + 1}",
                "kind": "related_improvement",
                "path": path,
                "summary": summary or path,
                "confidence": "high" if _score(related) >= 8 else "medium",
                "evidence_refs": [],
            }
            score = _score(related)
            if score:
                item["score"] = score
            source_id = _text(related.get("id"))
            if source_id:
                item["source_id"] = source_id
                item["source_kind"] = "related_improvement"
            checksum = _text(related.get("checksum"))
            if checksum:
                item["checksum"] = checksum
            items.append(item)
        for observation in self._repository_observations:
            path = _path(observation.get("path"))
            if not path or path in existing_paths:
                continue
            score = _score(observation)
            if score < 6:
                continue
            item = {
                "id": f"SF{len(items) + 1}",
                "kind": _text(observation.get("kind")) or "repository",
                "path": path,
                "summary": _surface_reason(observation),
                "confidence": "medium",
                "evidence_refs": [],
                "score": score,
            }
            source_id = _text(observation.get("id"))
            if source_id:
                item["source_id"] = source_id
                item["source_kind"] = "repository_observation"
            items.append(item)
        return items

    def _duplicate_search(
        self,
        existing: Sequence[Mapping[str, object]],
        similar: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        terms: list[str] = []
        surfaces: list[str] = []
        for observation in self._repository_observations:
            for term in _string_items(observation.get("matched_terms")):
                if term not in terms:
                    terms.append(term)
            kind = _text(observation.get("kind")) or "repository"
            if kind not in surfaces:
                surfaces.append(kind)
        for related in self._related_improvements:
            if "related_improvements" not in surfaces:
                surfaces.append("related_improvements")
            for term in _string_items(related.get("matched_terms")):
                if term not in terms:
                    terms.append(term)
        matches: list[dict[str, object]] = []
        for item in [*existing, *similar]:
            path = _text(item.get("path"))
            if not path:
                continue
            match: dict[str, object] = {
                "path": path,
                "kind": _text(item.get("kind")) or "repository",
                "summary": _text(item.get("summary")) or path,
                "confidence": _text(item.get("confidence")) or "medium",
            }
            for key in ("id", "source_id", "source_kind"):
                value = _text(item.get(key))
                if value:
                    match[key] = value
            score = item.get("score")
            if isinstance(score, int) and not isinstance(score, bool):
                match["score"] = score
            matches.append(match)
        no_match_claims: list[dict[str, object]] = []
        if not matches:
            no_match_claims.append({
                "searched_for": "Existing or duplicate functionality related to the request",
                "confidence": "medium" if terms or surfaces else "low",
            })
        return {
            "searched_terms": terms[:12],
            "searched_surfaces": surfaces[:8],
            "matches": matches[:8],
            "no_match_claims": no_match_claims,
        }

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



def _score(item: Mapping[str, object]) -> int:
    score = item.get("score")
    return score if isinstance(score, int) and not isinstance(score, bool) else 0
