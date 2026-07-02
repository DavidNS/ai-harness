"""PROPOSAL_PURPOSE phase."""

from __future__ import annotations

from harness_v2.backend.application.decision_service import DecisionRequest
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phase_artifacts import sdd, shared_inputs
from harness_v2.backend.domain.escalation import EscalationCategory, EscalationIssue
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


def execute(context: PhaseExecutionContext) -> PhaseResult:
    run = context.run
    bundle = context.artifacts.ensure_worker_json(run, BundleName.PROPOSAL_BUNDLE, PhaseName.PROPOSAL_PURPOSE, "purpose", "purpose/bundle.json", {"request": run.request, "explore_bundle_view": shared_inputs.read_explore_bundle_view(context), "explorer_scope": {}}, sdd.validate_purpose_bundle)
    outcome = str(bundle["outcome"])
    if outcome == "clarify":
        return PhaseResult(decision_request=DecisionRequest(run.run_id, str(bundle.get("decision_id") or "proposal-clarification"), str(bundle.get("question") or bundle["summary"]), tuple(str(item) for item in bundle.get("options", ()) if str(item).strip())))
    if outcome == "reject":
        return PhaseResult(escalation_issue=EscalationIssue("proposal-rejected", BundleName.PROPOSAL_BUNDLE, EscalationCategory.CONTRACT_INVALID, str(bundle.get("rejection_reason") or bundle["summary"]), evidence_artifact_ids=("purpose/bundle.json",)))
    return PhaseResult()
