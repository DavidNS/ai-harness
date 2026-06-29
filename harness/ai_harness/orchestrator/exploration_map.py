"""Decision-neutral EXPLORE map construction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


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


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _object_list(value: object) -> list[Mapping[str, object]]:
    return [item for item in _list(value) if isinstance(item, Mapping)]


def _strings(value: object) -> list[str]:
    return [_text(item) for item in _list(value) if _text(item)]


def _confidence(value: object, *, default: str = "medium") -> str:
    text = _text(value).casefold()
    return text if text in {"low", "medium", "high", "critical"} else default


def _append_unique(items: list[dict[str, object]], item: dict[str, object]) -> None:
    key = (item.get("kind"), item.get("path"), item.get("text"), item.get("shape"))
    for existing in items:
        if (existing.get("kind"), existing.get("path"), existing.get("text"), existing.get("shape")) == key:
            return
    items.append(item)


def _source_paths(evidence: Sequence[Mapping[str, object]]) -> dict[str, list[str]]:
    paths_by_evidence: dict[str, list[str]] = {}
    for item in evidence:
        evidence_id = _text(item.get("id"))
        if not evidence_id:
            continue
        paths: list[str] = []
        for source in _object_list(item.get("sources", [])):
            path = _text(source.get("path"))
            if path and path not in paths:
                paths.append(path)
        paths_by_evidence[evidence_id] = paths
    return paths_by_evidence


def _surface_kind(observation: Mapping[str, object]) -> str:
    kind = _text(observation.get("kind")).casefold()
    path = _text(observation.get("path")).casefold()
    if kind == "test" or "/test" in path or path.startswith("tests/"):
        return "test_surface"
    if kind in {"ci", "ci_signal"}:
        return "ci_surface"
    if kind in {"analysis_doc", "documentation", "prompt", "worker"} or path.endswith(".md"):
        return "documentation_surface"
    if kind == "source" or path.endswith((".py", ".js", ".ts", ".tsx", ".jsx")):
        return "implementation_surface"
    return "repository_surface"


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


class ExplorationMapBuilder:
    """Builds a conservative map of what EXPLORE observed.

    The map is intentionally not a decision artifact. It groups evidence into
    surfaces, behaviors, risks, constraints, unknowns, and possible work shapes
    so later phases can choose purpose and design with better context.
    """

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
        evidence = _object_list(self._evidence_normalization.get("evidence", []))
        paths_by_evidence = _source_paths(evidence)
        surfaces = self._surfaces(paths_by_evidence)
        behaviors = self._behaviors(evidence)
        constraints = self._constraints()
        risks = self._risks(surfaces, evidence)
        unknowns = self._unknowns(evidence)
        verification = self._verification_surfaces(surfaces, risks)
        work_shapes = self._candidate_work_shapes(risks, unknowns, surfaces)
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
            "handoff_notes": self._handoff_notes(unknowns, risks, verification),
        }

    def _surfaces(self, paths_by_evidence: Mapping[str, list[str]]) -> list[dict[str, object]]:
        surfaces: list[dict[str, object]] = []
        seen_paths: set[str] = set()
        counter = 1
        for observation in self._repository_observations:
            path = _text(observation.get("path"))
            if not path or Path(path).is_absolute() or path in seen_paths:
                continue
            seen_paths.add(path)
            item: dict[str, object] = {
                "id": f"S{counter}",
                "kind": _surface_kind(observation),
                "path": path,
                "symbols": _strings(observation.get("symbols")),
                "why_relevant": self._surface_reason(observation),
                "evidence_refs": [],
                "confidence": "high" if isinstance(observation.get("score"), int) and int(observation["score"]) >= 20 else "medium",
            }
            if observation.get("kind") == "ci_signal":
                item["ci"] = {
                    "severity": _text(observation.get("severity")) or _text(observation.get("max_severity")) or "warning",
                    "signal_count": observation.get("signal_count", 1),
                    "tool": _text(observation.get("tool")),
                }
            surfaces.append(item)
            counter += 1
        for evidence_id, paths in paths_by_evidence.items():
            for path in paths:
                if not path or Path(path).is_absolute() or path in seen_paths:
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
    def _surface_reason(observation: Mapping[str, object]) -> str:
        matches = _strings(observation.get("matches"))
        if matches:
            return matches[0]
        terms = _strings(observation.get("matched_terms"))
        if terms:
            return "Matched request/evidence terms: " + ", ".join(terms[:6])
        if observation.get("kind") == "ci_signal":
            return "CI signal references this repository path."
        return "Repository observation selected this path."

    @staticmethod
    def _behaviors(evidence: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        behaviors: list[dict[str, object]] = []
        status_map = {
            "supported": "observed",
            "partially_supported": "partially_observed",
            "contradicted": "contradicted",
            "unresolved": "unresolved",
            "blocked": "unresolved",
            "not_applicable": "not_applicable",
        }
        for index, item in enumerate(evidence, start=1):
            behaviors.append({
                "id": f"B{index}",
                "status": status_map.get(_text(item.get("status")), "unresolved"),
                "text": _text(item.get("claim")) or "Evidence item did not include a claim.",
                "evidence_refs": [_text(item.get("id"))] if _text(item.get("id")) else [],
            })
        return behaviors

    def _constraints(self) -> list[dict[str, object]]:
        constraints: list[dict[str, object]] = []
        for index, item in enumerate(_strings(self._request_understanding.get("explicit_constraints")), start=1):
            constraints.append({"id": f"C{index}", "kind": "request", "text": item, "evidence_refs": []})
        ci_requirement = _text(self._evidence_plan.get("ci_requirement"))
        if ci_requirement and ci_requirement != "not_needed":
            constraints.append({
                "id": f"C{len(constraints) + 1}",
                "kind": "ci",
                "text": f"CI evidence requirement is {ci_requirement}.",
                "evidence_refs": [],
            })
        for blocker in _strings(self._ci_barrier.get("blockers")):
            constraints.append({
                "id": f"C{len(constraints) + 1}",
                "kind": "operational",
                "text": blocker,
                "evidence_refs": [],
            })
        return constraints

    @staticmethod
    def _risks(surfaces: Sequence[Mapping[str, object]], evidence: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        risks: list[dict[str, object]] = []
        for surface in surfaces:
            path = _text(surface.get("path"))
            text = " ".join([path, _text(surface.get("why_relevant")), str(surface.get("ci", ""))])
            kind = _risk_kind(text)
            if kind is not None:
                _append_unique(risks, {
                    "id": f"K{len(risks) + 1}",
                    "kind": kind,
                    "path": path,
                    "text": f"{kind} signal observed for {path}.",
                    "severity": _confidence(surface.get("confidence")),
                    "evidence_refs": _strings(surface.get("evidence_refs")),
                })
        for item in evidence:
            claim = _text(item.get("claim"))
            kind = _risk_kind(claim)
            if kind is not None:
                _append_unique(risks, {
                    "id": f"K{len(risks) + 1}",
                    "kind": kind,
                    "path": "",
                    "text": claim,
                    "severity": _confidence(item.get("confidence")),
                    "evidence_refs": [_text(item.get("id"))] if _text(item.get("id")) else [],
                })
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
    def _verification_surfaces(
        surfaces: Sequence[Mapping[str, object]],
        risks: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        verification: list[dict[str, object]] = []
        for surface in surfaces:
            if _text(surface.get("kind")) == "test_surface":
                verification.append({
                    "id": f"V{len(verification) + 1}",
                    "kind": "existing_test_surface",
                    "path": _text(surface.get("path")),
                    "text": "Existing test-related surface may verify the change.",
                    "evidence_refs": _strings(surface.get("evidence_refs")),
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
            verification.append({
                "id": f"V{len(verification) + 1}",
                "kind": f"{kind}_verification",
                "path": _text(risk.get("path")),
                "text": text,
                "evidence_refs": _strings(risk.get("evidence_refs")),
            })
        return verification

    @staticmethod
    def _candidate_work_shapes(
        risks: Sequence[Mapping[str, object]],
        unknowns: Sequence[Mapping[str, object]],
        surfaces: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
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
    def _handoff_notes(
        unknowns: Sequence[Mapping[str, object]],
        risks: Sequence[Mapping[str, object]],
        verification: Sequence[Mapping[str, object]],
    ) -> dict[str, list[str]]:
        return {
            "purpose": [_text(item.get("text")) for item in unknowns if _text(item.get("best_resolved_by")) == "purpose"],
            "design": [
                *[_text(item.get("text")) for item in unknowns if _text(item.get("best_resolved_by")) == "design"],
                *[_text(item.get("text")) for item in risks],
            ],
            "tasks": [_text(item.get("text")) for item in verification],
        }
