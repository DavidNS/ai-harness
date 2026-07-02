"""Deterministic model provider adapters for v2 tests."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
from time import monotonic

from harness_v2.backend.ports.model_provider import ModelProviderRequest, ModelProviderResult


class FakeModelProvider:
    """Queue-backed provider that records requests and returns canned results."""

    def __init__(self, results: tuple[ModelProviderResult, ...] | list[ModelProviderResult] | None = None) -> None:
        self._results = deque(results or ())
        self.requests: list[ModelProviderRequest] = []

    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        self.requests.append(request)
        if self._results:
            return self._results.popleft()
        return ModelProviderResult(stdout=request.prompt, stderr="", exit_code=0, duration_seconds=0.0)


@dataclass(frozen=True, slots=True)
class ScriptedModelProvider:
    """Prompt-prefix scripted provider for deterministic integration tests."""

    output_limit: int = 1_000_000

    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        started = monotonic()
        limit = min(self.output_limit, request.truncation.output_bytes)
        prompt = request.prompt
        if prompt.startswith("FAIL"):
            return ModelProviderResult("", "scripted provider failure", 7, monotonic() - started)
        if prompt.startswith("TIMEOUT"):
            return ModelProviderResult("", "", None, monotonic() - started, timed_out=True)
        if prompt.startswith("MALFORMED"):
            return ModelProviderResult("not json", "", 0, monotonic() - started)
        if prompt.startswith("LARGE"):
            stdout, truncated = _truncate("x" * (limit + 100), limit)
            return ModelProviderResult(stdout, "", 0, monotonic() - started, truncated=truncated)
        scripted = _scripted_output(prompt)
        stdout, truncated = _truncate(scripted if scripted is not None else prompt, limit)
        return ModelProviderResult(stdout, "", 0, monotonic() - started, truncated=truncated)


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text.encode("utf-8")) <= limit:
        return text, False
    encoded = text.encode("utf-8")[:limit]
    return encoded.decode("utf-8", "ignore") + "\n[output truncated]", True


def _scripted_output(prompt: str) -> str | None:
    payload = _prompt_payload(prompt)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        return None
    task_id = payload.get("task_id")
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    if task_id == "explore_request_profile":
        request = str(inputs.get("request", "Implement the request."))
        return _json({
            "schema_version": 1,
            "phase": "explore_request_profile",
            "summary": request,
            "request_type": "feature",
            "complexity": "local_change",
            "ambiguity": "clear",
            "risk": "low",
            "evidence_depth": "standard",
            "request_parts": [request],
            "constraints": [],
            "evidence_questions": ["Is the request bounded enough for the next bundle?"],
            "gatherers": ["code", "knowledge", "ci"],
            "clarification_questions": [],
        })
    if task_id == "explore_evidence_digest":
        return _json({
            "schema_version": 1,
            "phase": "explore_evidence_digest",
            "evidence": [{
                "id": "E1",
                "kind": "knowledge",
                "claim": "The deterministic v2 EXPLORE fixture is bounded enough for the next bundle.",
                "status": "supported",
                "confidence": "high",
                "severity": "info",
                "sources": [{"type": "knowledge", "description": "Scripted v2 provider fixture evidence."}],
            }],
            "blockers": [],
        })
    if task_id == "explore_outcome_synthesis":
        return _json({
            "schema_version": 1,
            "kind": "explore_outcome_synthesis",
            "status": "ready_for_purpose",
            "normalized_request": {"summary": "Implement the request."},
            "triage": {
                "complexity": "local_change",
                "ambiguity": "clear",
                "risk": "low",
                "evidence_depth": "standard",
            },
            "entries": [{
                "id": "entry-1",
                "classification": "improvement",
                "title": "Implement the request",
                "problem": "The requested bounded change should be implemented.",
                "evidence_refs": ["E1"],
                "constraints": [],
                "unknowns": [],
            }],
        })

    if task_id == "explorer_intake":
        request = str(inputs.get("request", "Investigate improvement."))
        return _json({
            "schema_version": 1,
            "phase": "explorer_intake",
            "strategic_framing": {
                "mode": "specific",
                "value_targets": ["Reduce migration uncertainty."],
                "needs_user_direction": False,
                "rationale": "The request is bounded enough for staged Explorer.",
            },
            "claims": [{
                "id": "C1",
                "class": "repository-factual",
                "text": request,
                "evidence_targets": ["repository"],
            }],
            "synthesis_notes": ["Use the v2 Explorer skeleton."],
        })
    if task_id == "explorer_discovery":
        return _json({
            "schema_version": 1,
            "phase": "explorer_discovery",
            "claims": [{
                "id": "C1",
                "status": "resolved",
                "evidence": ["The v2 Explorer skeleton can be mounted as a separate strategy."],
            }],
            "evidence_trace": [{
                "id": "T1",
                "claim_id": "C1",
                "source": "code",
                "path": "harness_v2/backend/domain/lifecycle.py",
                "excerpt": "RunStrategy and PhaseName define v2 lifecycle nodes.",
                "confidence": "high",
            }],
            "duplicate_search": {
                "searched_terms": ["Explorer workflow skeleton"],
                "searched_surfaces": ["harness_v2"],
                "matches": [],
                "no_match_claims": [{
                    "claim_id": "C1",
                    "searched_for": "existing v2 Explorer workflow",
                    "confidence": "medium",
                }],
            },
            "candidate_directions": [{
                "id": "D1",
                "title": "Mount staged Explorer in v2",
                "mechanism": "Use the generic bundle orchestrator with Explorer phases.",
                "impact": "High",
                "confidence": "High",
                "cost": "Medium",
                "reversibility": "High",
                "evidence_strength": "Strong",
                "behavioral_delta": "EXPLORER runs complete through staged artifacts.",
                "evidence": ["T1"],
            }],
            "critic_findings": [],
            "related_improvements": [],
            "repository_observations": [],
        })
    if task_id == "explorer_decision":
        return _json({
            "schema_version": 1,
            "phase": "explorer_decision",
            "outcome": "new_improvement",
            "selected_direction": "D1",
            "rationale": "The skeleton is bounded and useful for migration.",
            "evidence": ["T1"],
            "value_hypothesis": "A separate Explorer graph preserves architecture boundaries.",
            "behavioral_delta": "A run can execute intake through distill.",
            "rejected_alternatives": [],
            "counterevidence": [],
            "falsifying_conditions": [],
            "minimum_verification": "Run v2 Explorer integration tests.",
        })
    if task_id == "explorer_artifact":
        return (
            "# Explorer Candidate v1\n"
            "## Problem\nExplorer phases are not represented in v2.\n"
            "## Context\nThe SDD EXPLORE_BUNDLE is separate from the Explorer workflow.\n"
            "## Recommendation\nMount Explorer as an independent v2 strategy.\n"
        )
    if task_id == "explorer_review":
        return "# Review v1\n## Verdict\nAPPROVE\n## Findings\n- The candidate is bounded for Stage 6.5.\n"
    if task_id == "explorer_distill":
        return (
            "# Explorer Workflow Skeleton\n"
            "## Problem\nExplorer lacks staged v2 orchestration.\n"
            "## Recommendation\nUse the v2 bundle orchestrator for Explorer phases.\n"
        )

    if task_id == "knowledge_synthesis":
        source_phase = str(inputs.get("source_phase", "EXPLORE_BUNDLE")).lower()
        source_artifacts = inputs.get("source_artifacts") if isinstance(inputs.get("source_artifacts"), dict) else {}
        return _json({
            "schema_version": 1,
            "phase": "learning",
            "proposal_manifest": {
                "schema_version": 1,
                "proposal_id": f"proposal.v2.{source_phase}.001",
                "summary": f"Candidate knowledge extracted from {source_phase}.",
                "source_artifacts": list(source_artifacts.keys()),
                "claims_file": "proposed_claims.jsonl",
            },
            "proposed_claims": [{
                "id": f"claim.v2.{source_phase}.001",
                "domain": "harness",
                "subjects": ["V2KnowledgeLifecycle"],
                "files": ["harness_v2/backend/domain/lifecycle.py"],
                "symbols": [],
                "claim_type": "behavior",
                "text": f"The v2 lifecycle produced candidate knowledge after {source_phase}.",
                "status": "active",
                "evidence": [{"type": "code", "file": "harness_v2/backend/domain/lifecycle.py"}],
                "valid_from": None,
                "valid_until": None,
                "last_verified": None,
            }],
            "proposed_relations": [],
        })

    if task_id == "purpose":
        return _json({
            "schema_version": 1,
            "kind": "purpose_bundle",
            "summary": "Implement the request.",
            "selected_entries": ["entry-1"],
            "implementation_mode": "direct_patch",
            "problem": "Implement the request.",
            "scope": "One bounded change.",
            "approach": "Use controller-owned SDD bundle gates.",
            "structural_work": [],
            "exclusions": ["No unrelated work."],
            "acceptance_outline": ["Tests pass."],
            "evidence_refs": ["E1"],
        })
    if task_id == "spec":
        return "# Spec v1\n## Behavioral Requirements\nThe feature works.\n## Acceptance Criteria\nController tests pass.\n"
    if task_id == "design":
        return (
            "# Design v1\n"
            "## Boundaries\nRepository only.\n"
            "## Invariants\nController owns state.\n"
            "## Implementation Approach\nWrite the bounded change.\n"
            "## Unit Test Design\nCheck focused behavior.\n"
            "## Integration Test Design\nRun the SDD skeleton.\n"
            "## End-to-End Test Design\nComplete the bundle graph.\n"
        )
    if task_id == "tasks":
        return _json({
            "schema_version": 1,
            "phase": "tasks",
            "tasks": [{
                "id": "T1",
                "title": "Implement the bounded change",
                "depends_on": [],
                "acceptance_criteria": ["The SDD skeleton completes."],
                "touched_paths": ["."],
                "focused_tests": [["python3", "-B", "-m", "unittest", "discover", "test_v2"]],
                "broader_tests": [],
                "status": "pending",
            }],
        })
    return None


def _prompt_payload(prompt: str) -> dict[str, object] | None:
    marker = "Return only the required artifact. Controller inputs:"
    candidates = [prompt]
    if marker in prompt:
        candidates.insert(0, prompt.rsplit(marker, 1)[1].strip())
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
