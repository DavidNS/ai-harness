"""Phase registry and definition construction."""

from __future__ import annotations

from ..explorer_contracts import (
    validate_explorer_artifact,
    validate_explorer_decision,
    validate_explorer_discovery,
    validate_explorer_intake,
    validate_explorer_review,
)
from .errors import PhaseValidationError
from .markdown import markdown_validator
from .types import PhaseDefinition, Validator
from .validators.explorer import validate_explorer, validate_explorer_distill
from .validators.explore import (
    validate_explore_ci_barrier,
    validate_explore_clarification_gate,
    validate_explore_evidence_collection,
    validate_explore_evidence_normalization,
    validate_explore_evidence_plan,
    validate_explore_outcome_bundle,
    validate_explore_request_understanding,
    validate_explore_review,
    validate_explore_triage,
)
from .validators.knowledge import validate_knowledge_review, validate_learning
from .validators.review import validate_review
from .validators.tasks import validate_tasks


def _definition(
    name: str,
    artifact: str,
    inputs: tuple[str, ...],
    title: str,
    sections: tuple[str, ...],
    validator: Validator | None = None,
    heading: str | None = None,
) -> PhaseDefinition:
    required_heading = heading if heading is not None else (None if artifact.endswith(".json") else f"# {title} v1")
    return PhaseDefinition(name, artifact, inputs, sections, validator or markdown_validator(title, sections), required_heading)


PHASE_DEFINITIONS = {
    "explore": _definition("explore", "explore/outcome_bundle.json", ("request", "knowledge", "repository", "explorer_scope"), "Explore Outcome Bundle", (), validate_explore_outcome_bundle),
    "purpose": _definition("purpose", "purpose.md", ("request", "explore/outcome_bundle.json", "explorer_scope"), "Purpose", ("Problem", "Scope", "Approach", "Exclusions", "Acceptance Outline")),
    "spec": _definition("spec", "spec.md", ("explore/outcome_bundle.json", "purpose.md", "explorer_scope"), "Spec", ("Behavioral Requirements", "Acceptance Criteria")),
    "design": _definition("design", "design.md", ("explore/outcome_bundle.json", "spec.md", "explorer_scope"), "Design", ("Boundaries", "Invariants", "Implementation Approach", "Unit Test Design", "Integration Test Design", "End-to-End Test Design")),
    "tasks": _definition("tasks", "tasks.json", ("spec.md", "design.md", "explorer_scope"), "Tasks", (), validate_tasks),
    "explore_request_understanding": _definition("explore_request_understanding", "explore/request_understanding.json", ("request", "knowledge", "repository", "explorer_scope"), "Explore Request Understanding", (), validate_explore_request_understanding),
    "explore_clarification_gate": _definition("explore_clarification_gate", "explore/clarification_gate.json", ("request_understanding",), "Explore Clarification Gate", (), validate_explore_clarification_gate),
    "explore_triage": _definition("explore_triage", "explore/triage.json", ("request_understanding", "clarification_gate"), "Explore Triage", (), validate_explore_triage),
    "explore_evidence_plan": _definition("explore_evidence_plan", "explore/evidence_plan.json", ("request", "request_understanding", "triage", "knowledge", "repository", "explorer_scope"), "Explore Evidence Plan", (), validate_explore_evidence_plan),
    "explore_evidence_collection": _definition("explore_evidence_collection", "explore/evidence_collection.json", ("request", "request_understanding", "triage", "evidence_plan", "knowledge", "repository", "explorer_scope", "related_improvements", "repository_observations"), "Explore Evidence Collection", (), validate_explore_evidence_collection),
    "explore_ci_barrier": _definition("explore_ci_barrier", "explore/ci_evidence_barrier.json", ("evidence_plan", "ci_status", "git_run", "ci_signals"), "Explore CI Barrier", (), validate_explore_ci_barrier),
    "explore_evidence_normalization": _definition("explore_evidence_normalization", "explore/evidence_normalization.json", ("evidence_collection", "ci_barrier"), "Explore Evidence Normalization", (), validate_explore_evidence_normalization),
    "explore_outcome_synthesis": _definition("explore_outcome_synthesis", "explore/outcome_bundle.json", ("request", "request_understanding", "clarification_gate", "triage", "evidence_plan", "evidence_collection", "ci_barrier", "evidence_normalization"), "Explore Outcome Synthesis", (), validate_explore_outcome_bundle),
    "explore_review": _definition("explore_review", "explore/review.md", ("outcome_bundle", "request_understanding", "triage", "evidence_plan", "evidence_normalization"), "Review", ("Verdict", "Findings"), validate_explore_review),
    "explorer": _definition("explorer", "explorer/bundle.json", ("request", "knowledge", "repository", "runtime_context", "related_improvements", "repository_observations", "repair"), "Explorer Bundle", (), validate_explorer),
    "explorer_intake": _definition("explorer_intake", "explorer/intake.json", ("request", "knowledge", "repository", "runtime_context"), "Explorer Intake", (), validate_explorer_intake),
    "explorer_discovery": _definition("explorer_discovery", "explorer/discovery.json", ("request", "knowledge", "repository", "runtime_context", "intake", "related_improvements", "repository_observations", "refinement"), "Explorer Discovery", (), validate_explorer_discovery),
    "explorer_decision": _definition("explorer_decision", "explorer/decision.json", ("request", "knowledge", "repository", "runtime_context", "intake", "discovery", "related_improvements", "repository_observations", "refinement"), "Explorer Decision", (), validate_explorer_decision),
    "explorer_artifact": _definition("explorer_artifact", "explorer/artifact-candidate.txt", ("request", "knowledge", "repository", "runtime_context", "intake", "discovery", "decision", "related_improvements", "repository_observations", "repair"), "Explorer Artifact", (), validate_explorer_artifact),
    "explorer_distill": _definition("explorer_distill", "explorer/distilled-candidate.md", ("request", "artifact_candidate", "decision", "discovery", "review", "related_improvements", "repository_observations"), "Explorer Distill", (), validate_explorer_distill),
    "explorer_review": _definition("explorer_review", "explorer/review.md", ("request", "runtime_context", "intake", "discovery", "decision", "artifact_candidate", "related_improvements", "repository_observations"), "Review", ("Verdict", "Findings"), validate_explorer_review),
    "implement": _definition("implement", "implementation.md", ("design.md", "task", "repository", "prior_failures"), "Implementation", ("Changes", "Evidence")),
    "test": _definition("test", "tests.md", ("spec.md", "design.md", "task", "changes", "command_evidence"), "Tests", ("Commands", "Results")),
    "review": _definition("review", "review.md", ("spec.md", "task", "diff", "test_evidence", "ci/run-branch-signals.json", "ci/comparison.json"), "Review", ("Verdict", "Findings"), validate_review),
    "learning": _definition("learning", "learning.json", ("final_artifacts", "state", "learning_context"), "Learning", (), validate_learning),
    "knowledge_synthesis": _definition("knowledge_synthesis", "knowledge/synthesis.json", ("source", "run", "source_artifacts", "repository_snapshot", "accepted_evidence", "rejected_evidence", "context", "repair"), "Knowledge Synthesis", (), validate_learning),
    "knowledge_review": _definition("knowledge_review", "knowledge/review.json", ("proposal", "source", "context", "repository_snapshot", "accepted_evidence", "rejected_evidence"), "Knowledge Review", (), validate_knowledge_review),
}


def get_phase(name: str) -> PhaseDefinition:
    try:
        return PHASE_DEFINITIONS[name.lower()]
    except KeyError as exc:
        raise PhaseValidationError(f"unknown phase: {name}") from exc
