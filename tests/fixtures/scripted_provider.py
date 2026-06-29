from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.providers.base import ProviderResult


def learning_output(
    *,
    proposal_id: str = "proposal.deterministic-offline-completion.001",
    claim_id: str = "claim.deterministic-offline-completion.001",
    summary: str = "Completed offline.",
    text: str = "feature.py records the deterministic offline completion fixture behavior.",
) -> str:
    return json.dumps({
        "schema_version": 1,
        "phase": "learning",
        "proposal_manifest": {
            "schema_version": 1,
            "proposal_id": proposal_id,
            "summary": summary,
            "source_artifacts": ["implementation/T1/1.md"],
            "claims_file": "proposed_claims.jsonl",
        },
        "proposed_claims": [{
            "id": claim_id,
            "domain": "harness",
            "subjects": ["DeterministicOfflineCompletion"],
            "files": ["feature.py"],
            "symbols": [],
            "claim_type": "responsibility",
            "text": text,
            "status": "active",
            "evidence": [{"type": "code", "file": "feature.py"}],
            "valid_from": None,
            "valid_until": None,
            "last_verified": None,
        }],
        "proposed_relations": [],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n"




def knowledge_review_output(proposal_id: str, claim_ids: list[str], *, decision: str = "accept", reason: str = "Evidence supports a durable repository fact.") -> str:
    return json.dumps({
        "schema_version": 1,
        "phase": "knowledge_review",
        "proposal_id": proposal_id,
        "claim_reviews": [
            {"claim_id": claim_id, "decision": decision, "reason": reason}
            for claim_id in claim_ids
        ],
        "relation_reviews": [],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _fixture_claim_text(evidence: dict[str, object]) -> str:
    path = str(evidence.get("file", "")).strip()
    symbol = str(evidence.get("symbol", "")).strip()
    excerpt = " ".join(str(evidence.get("excerpt", "")).split())
    kind = str(evidence.get("type", "")).casefold()
    subject = f"{path}::{symbol}" if symbol else path
    if kind == "test":
        if symbol:
            return f"{path} covers test behavior for {symbol}."
        if excerpt:
            return f"{path} contains test coverage evidenced by: {excerpt[:160]}"
        return f"{path} contains test coverage for the investigated behavior."
    if kind == "documentation":
        if symbol:
            return f"{path} documents the repository contract for {symbol}."
        if excerpt:
            return f"{path} documents repository behavior evidenced by: {excerpt[:160]}"
        return f"{path} documents repository behavior for the investigated area."
    if kind == "decision":
        if excerpt:
            return f"{path} records a repository decision evidenced by: {excerpt[:160]}"
        return f"{path} records a repository decision for the investigated area."
    if symbol:
        return f"{path} defines source behavior for {symbol}."
    if excerpt:
        return f"{path} contains source behavior evidenced by: {excerpt[:160]}"
    return f"{subject} contains source behavior for the investigated area."


def explore_outcome_bundle() -> str:
    return json.dumps({
        "schema_version": 1,
        "kind": "explore_outcome_bundle",
        "status": "ready_for_purpose",
        "normalized_request": {"summary": "Implement the request."},
        "triage": {"complexity": "local_change", "ambiguity": "clear", "risk": "low", "evidence_depth": "standard"},
        "evidence": [{
            "id": "E1",
            "claim": "The deterministic fixture request is bounded enough for PURPOSE.",
            "status": "supported",
            "confidence": "high",
            "sources": [{"type": "knowledge", "description": "Scripted provider fixture evidence."}],
        }],
        "entries": [{
            "id": "entry-1",
            "classification": "improvement",
            "title": "Implement the request",
            "problem": "The requested bounded change should be implemented.",
            "evidence_refs": ["E1"],
            "constraints": ["Offline deterministic fixture."],
            "unknowns": [],
        }],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def synthesized_explorer_output(inputs: dict[str, object]) -> str:
    run = inputs.get("run", {}) if isinstance(inputs.get("run"), dict) else {}
    context = inputs.get("context", {}) if isinstance(inputs.get("context"), dict) else {}
    accepted = inputs.get("accepted_evidence", [])
    rejected = inputs.get("rejected_evidence", [])
    run_id = str(run.get("run_id", "run"))[:8]
    artifact_kind = str(context.get("artifact_kind", "improvement")).replace("_", "-")
    entry_id = str(context.get("entry_id", "entry"))[:32].replace("/", "-")
    proposal_id = f"proposal.{artifact_kind}.{entry_id}.{run_id}"
    sources_checked = context.get("evidence_sources_checked", [])
    claims = []
    if isinstance(accepted, list) and accepted:
        for index, item in enumerate(accepted, start=1):
            evidence = dict(item) if isinstance(item, dict) else {}
            path = str(evidence.get("file", "feature.py"))
            symbol = str(evidence.get("symbol", "")).strip()
            claim_id = f"claim.{artifact_kind}.{entry_id}.{run_id}.{index}"
            claims.append({
                "id": claim_id,
                "domain": "knowledge",
                "subjects": [path],
                "files": [path],
                "symbols": [symbol] if symbol else [],
                "claim_type": "test_coverage" if evidence.get("type") == "test" else "responsibility",
                "text": _fixture_claim_text(evidence),
                "status": "active",
                "evidence": [evidence],
                "valid_from": None,
                "valid_until": None,
                "last_verified": None,
                "metadata": {
                    "source": "knowledge_synthesis",
                    "entry_id": entry_id,
                    "evidence_sources_checked": sources_checked if isinstance(sources_checked, list) else [],
                },
            })
    else:
        claims.append({
            "id": f"claim.{artifact_kind}.{entry_id}.{run_id}",
            "domain": "knowledge",
            "subjects": [artifact_kind],
            "files": [],
            "symbols": [],
            "claim_type": "responsibility",
            "text": "No durable repository fact was supported by repository-backed evidence.",
            "status": "unverified",
            "evidence": [],
            "valid_from": None,
            "valid_until": None,
            "last_verified": None,
            "metadata": {
                "source": "knowledge_synthesis",
                "entry_id": entry_id,
                "unverified_reason": "repository_evidence_rejected" if rejected else "missing_repository_evidence",
                "evidence_sources_checked": sources_checked if isinstance(sources_checked, list) else [],
                "rejection_reasons": [dict(item) for item in rejected if isinstance(item, dict)] or ([{"source": "evidence_extraction", "reason": "no_repository_evidence"}] if not rejected else []),
            },
        })
    return json.dumps({
        "schema_version": 1,
        "phase": "learning",
        "proposal_manifest": {
            "schema_version": 1,
            "proposal_id": proposal_id,
            "summary": "AI synthesized repository knowledge.",
            "source_artifacts": ["explorer_artifact", "explorer_decision"],
            "claims_file": "proposed_claims.jsonl",
        },
        "proposed_claims": claims,
        "proposed_relations": [],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

MARKDOWN = {
    "explore": explore_outcome_bundle(),
    "purpose": "# Purpose v1\n## Problem\nImplement the request.\n## Scope\nOne bounded change.\n## Approach\nUse controller gates.\n## Exclusions\nNo unrelated work.\n## Acceptance Outline\nTests pass.\n",
    "spec": "# Spec v1\n## Behavioral Requirements\nThe feature works.\n## Acceptance Criteria\nController tests pass.\n",
    "design": "# Design v1\n## Boundaries\nRepository only.\n## Invariants\nController owns state.\n## Implementation Approach\nWrite feature.py.\n## Unit Test Design\nCheck content.\n## Integration Test Design\nRun a process.\n## End-to-End Test Design\nComplete the pipeline.\n",
    "implement": "# Implementation v1\n## Changes\nUpdated feature.py.\n## Evidence\nController tests must verify it.\n",
    "learning": learning_output(),
    "explorer": "# Improvement Analysis v1\n## Problem\nInvestigate a proposed improvement.\n## Context\nA draft improvement was supplied.\n## Findings\nThe improvement is viable.\n## Options\nProceed later through implementation.\n## Risks\nImplementation scope may expand.\n## Recommendation\nMove forward with a future implementation flow.\n## Outcome\nimprovement\n## Open Questions\nNone.\n",
}


class ScriptedProvider:
    """In-process provider with contract-valid phase output and controlled side effects."""

    def __init__(self, *, implementation_contents: tuple[str, ...] = ("ready\n",),
                 review_verdicts: tuple[str, ...] = ("APPROVE",),
                 review_findings: tuple[str, ...] = ("Deterministic fixture verdict.",)) -> None:
        self.implementation_contents = implementation_contents
        self.review_verdicts = review_verdicts
        self.review_findings = review_findings
        self.calls: list[str] = []
        self.counts: defaultdict[str, int] = defaultdict(int)
        self.phase_inputs: defaultdict[str, list[dict[str, object]]] = defaultdict(list)

    @staticmethod
    def _source_artifacts(prompt: str) -> list[str]:
        try:
            inputs = json.loads(prompt.split("Controller inputs:\n", 1)[1])
        except (IndexError, json.JSONDecodeError):
            return ["docs/explorer/improvements/jwt-authentication/improvement.md"]
        artifacts = inputs.get("explorer_scope", {}).get("artifacts", [])
        paths = [item.get("path") for item in artifacts if isinstance(item, dict) and isinstance(item.get("path"), str)]
        return paths or ["docs/explorer/improvements/jwt-authentication/improvement.md"]

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None) -> ProviderResult:
        del permissions, progress
        phase_names = (
            *MARKDOWN,
            "tasks",
            "review",
            "explore_request_understanding",
            "explore_clarification_gate",
            "explore_triage",
            "explore_evidence_plan",
            "explore_evidence_collection",
            "explore_ci_barrier",
            "explore_evidence_normalization",
            "explore_outcome_synthesis",
            "explore_review",
            "explorer_intake",
            "explorer_discovery",
            "explorer_decision",
            "explorer_artifact",
            "explorer_distill",
            "explorer_review",
            "knowledge_synthesis",
            "knowledge_review",
        )
        phase = next((
            name for name in phase_names
            if f"# {' '.join(part.title() for part in name.split('_'))} Worker v1" in prompt
        ), None)
        if phase is None:
            raise AssertionError("unrecognized worker prompt")
        self.calls.append(phase)
        index = self.counts[phase]
        self.counts[phase] += 1
        inputs = {}
        try:
            inputs = json.loads(prompt.split("Controller inputs:\n", 1)[1])
            self.phase_inputs[phase].append(inputs)
        except (IndexError, json.JSONDecodeError):
            pass

        if phase == "explore_request_understanding":
            output = json.dumps({
                "schema_version": 1,
                "phase": "explore_request_understanding",
                "intent": "implement_request",
                "summary": "Implement the request.",
                "mentioned_surfaces": [],
                "explicit_constraints": [],
                "unclear_parts": [],
                "request_type": "feature",
            })
        elif phase == "explore_clarification_gate":
            output = json.dumps({
                "schema_version": 1,
                "phase": "explore_clarification_gate",
                "status": "continue",
                "clarification_questions": [],
                "rationale": "The deterministic fixture request is bounded.",
            })
        elif phase == "explore_triage":
            output = json.dumps({
                "schema_version": 1,
                "phase": "explore_triage",
                "complexity": "local_change",
                "ambiguity": "clear",
                "novelty": "known_repo_pattern",
                "risk": "low",
                "evidence_depth": "standard",
                "rationale": "The fixture is small and deterministic.",
            })
        elif phase == "explore_evidence_plan":
            output = json.dumps({
                "schema_version": 1,
                "phase": "explore_evidence_plan",
                "required_gatherers": ["code", "knowledge"],
                "optional_gatherers": ["ci"],
                "ci_requirement": "optional",
                "questions": ["Is the request bounded enough for PURPOSE?"],
                "skip_reason": {"web": "No external current fact is required."},
            })
        elif phase == "explore_evidence_collection":
            output = json.dumps({
                "schema_version": 1,
                "phase": "explore_evidence_collection",
                "evidence": [{
                    "id": "R1",
                    "claim": "The deterministic fixture request is bounded enough for PURPOSE.",
                    "status": "supported",
                    "confidence": "high",
                    "sources": [{"type": "knowledge", "description": "Scripted provider fixture evidence."}],
                }],
                "blockers": [],
            })
        elif phase == "explore_ci_barrier":
            output = json.dumps({
                "schema_version": 1,
                "phase": "explore_ci_barrier",
                "ci_requirement": "optional",
                "status": "ready",
                "evidence": [],
                "blockers": [],
            })
        elif phase == "explore_evidence_normalization":
            output = json.dumps({
                "schema_version": 1,
                "phase": "explore_evidence_normalization",
                "evidence": [{
                    "id": "E1",
                    "claim": "The deterministic fixture request is bounded enough for PURPOSE.",
                    "status": "supported",
                    "confidence": "high",
                    "sources": [{"type": "knowledge", "description": "Scripted provider fixture evidence."}],
                }],
            })
        elif phase == "explore_outcome_synthesis":
            output = explore_outcome_bundle()
        elif phase == "explore_review":
            output = "# Review v1\n## Verdict\nAPPROVE\n## Findings\nThe deterministic outcome bundle is evidence-backed.\n"
        elif phase == "knowledge_synthesis":
            if inputs.get("source") == "explorer":
                output = synthesized_explorer_output(inputs)
            else:
                output = MARKDOWN["learning"]
        elif phase == "knowledge_review":
            proposal = inputs.get("proposal", {}) if isinstance(inputs.get("proposal"), dict) else {}
            manifest = proposal.get("proposal_manifest", {}) if isinstance(proposal.get("proposal_manifest"), dict) else {}
            claims = proposal.get("proposed_claims", [])
            claim_ids = [str(item.get("id")) for item in claims if isinstance(item, dict)] if isinstance(claims, list) else []
            output = knowledge_review_output(str(manifest.get("proposal_id", "proposal.unknown")), claim_ids)
        elif phase == "tasks":
            output = json.dumps({
                "schema_version": 1,
                "phase": "tasks",
                "tasks": [{
                    "id": "T1",
                    "title": "Write the feature",
                    "depends_on": [],
                    "source_artifacts": self._source_artifacts(prompt),
                    "acceptance_criteria": ["feature.py contains ready"],
                    "touched_paths": ["feature.py"],
                    "focused_tests": [[sys.executable, "-c", "from pathlib import Path; assert Path('feature.py').read_text() == 'ready\\n'"]],
                    "broader_tests": [[sys.executable, "-c", "print('broader gate passed')"]],
                    "status": "pending",
                }],
            })
        elif phase == "implement":
            content = self.implementation_contents[min(index, len(self.implementation_contents) - 1)]
            (cwd / "feature.py").write_text(content, encoding="utf-8")
            output = MARKDOWN[phase]
        elif phase == "review" or phase == "explorer_review":
            verdict = self.review_verdicts[min(index, len(self.review_verdicts) - 1)]
            finding = self.review_findings[min(index, len(self.review_findings) - 1)]
            output = f"# Review v1\n## Verdict\n{verdict}\n## Findings\n{finding}\n"
        elif phase == "explorer_intake":
            output = json.dumps({
                "schema_version": 1,
                "phase": "explorer_intake",
                "strategic_framing": {
                    "mode": "specific",
                    "value_targets": ["better implementation readiness"],
                    "needs_user_direction": False,
                    "rationale": "The deterministic fixture request is already bounded.",
                },
                "claims": [{
                    "id": "C1",
                    "class": "repository-factual",
                    "text": "The request describes a candidate explorer artifact.",
                    "evidence_targets": ["repository", "analysis docs"],
                }],
                "synthesis_notes": [],
            })
        elif phase == "explorer_discovery":
            output = json.dumps({
                "schema_version": 1,
                "phase": "explorer_discovery",
                "claims": [{
                    "id": "C1",
                    "status": "resolved",
                    "evidence": ["Controller supplied repository observations and related improvements."],
                }],
                "candidate_directions": [{
                    "id": "D1",
                    "title": "Publish improvement artifact",
                    "mechanism": "Use the existing staged explorer artifact path.",
                    "impact": "Medium because it produces implementation-ready analysis.",
                    "confidence": "High because the fixture path is deterministic.",
                    "cost": "Low because no new controller behavior is needed.",
                    "reversibility": "High because it is an artifact-only decision.",
                    "evidence_strength": "Medium based on supplied fixture observations.",
                    "behavioral_delta": "A future implementation flow can consume the published artifact.",
                    "evidence": ["Controller supplied repository observations and related improvements."],
                }],
                "critic_findings": [{
                    "direction_id": "D1",
                    "severity": "note",
                    "finding": "The fixture direction is intentionally compact.",
                    "recommendation": "Proceed for deterministic staged tests.",
                }],
                "related_improvements": inputs.get("related_improvements", []),
                "repository_observations": inputs.get("repository_observations", []),
            })
        elif phase == "explorer_decision":
            output = json.dumps({
                "schema_version": 1,
                "phase": "explorer_decision",
                "outcome": "new_improvement",
                "rationale": "The request is a viable new improvement.",
                "evidence": ["Discovery resolved the repository-factual claim."],
                "selected_direction": "D1",
                "value_hypothesis": "A compact artifact improves future implementation readiness.",
                "behavioral_delta": "The pipeline publishes an implementation-ready explorer artifact.",
                "rejected_alternatives": [{"id": "D2", "reason": "A no-op would not produce the requested artifact."}],
                "counterevidence": [],
                "falsifying_conditions": ["The artifact repeats existing functionality without a new behavior target."],
                "minimum_verification": "Review confirms the artifact follows the selected decision.",
            })
        elif phase == "explorer_artifact":
            output = MARKDOWN["explorer"]
        elif phase == "explorer_distill":
            output = str(inputs.get("artifact_candidate", MARKDOWN["explorer"]))
        else:
            output = MARKDOWN[phase]
        return ProviderResult(output, "", 0, 0.001)
