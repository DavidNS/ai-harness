"""PROPOSAL_HANDOFF phase."""

from __future__ import annotations

from harness_v2.backend.application.decision_service import DecisionRequest
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phase_artifacts import handoff, shared_inputs
from harness_v2.backend.domain.escalation import EscalationCategory, EscalationIssue
from harness_v2.backend.domain.lifecycle import BundleName


def execute(context: PhaseExecutionContext) -> PhaseResult:
    bundle = shared_inputs.read_purpose_bundle(context)
    outcome = str(bundle["outcome"])
    if outcome == "clarify":
        decision_id = str(bundle.get("decision_id") or "proposal-clarification")
        if not _decision_answered(context, decision_id):
            return PhaseResult(decision_request=DecisionRequest(
                context.run.run_id,
                decision_id,
                str(bundle.get("question") or bundle["summary"]),
                tuple(str(item) for item in bundle.get("options", ()) if str(item).strip()),
            ))
    if outcome == "reject":
        return PhaseResult(escalation_issue=EscalationIssue(
            "proposal-rejected",
            BundleName.PROPOSAL_BUNDLE,
            EscalationCategory.CONTRACT_INVALID,
            str(bundle.get("rejection_reason") or bundle["summary"]),
            evidence_artifact_ids=("purpose/bundle.json",),
        ))
    context.artifacts.ensure_controller_json(
        context.run.run_id,
        "published/proposal-handoff.json",
        lambda: handoff.build_bundle_handoff(
            "proposal",
            ["purpose/bundle.json"],
            "SPEC_BUNDLE",
            extra={"summary": bundle["summary"], "proposal_outcome": outcome, "implementation_mode": bundle["implementation_mode"], "selected_entries": bundle["selected_entries"]},
        ),
        handoff.validate_handoff,
    )
    return PhaseResult()


def _decision_answered(context: PhaseExecutionContext, decision_id: str) -> bool:
    return any(record.decision_id == decision_id for record in context.run.decision_history)
