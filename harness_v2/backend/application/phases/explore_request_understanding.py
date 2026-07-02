"""EXPLORE_REQUEST_UNDERSTANDING phase."""

from __future__ import annotations

from harness_v2.backend.application.decision_service import DecisionRequest
from harness_v2.backend.application.phase_artifacts import explore, explore_inputs
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


def execute(context: PhaseExecutionContext) -> PhaseResult:
    run = context.run
    profile = context.artifacts.ensure_worker_json(run, BundleName.EXPLORE_BUNDLE, PhaseName.EXPLORE_REQUEST_UNDERSTANDING, explore.REQUEST_PROFILE_TASK, explore.REQUEST_PROFILE_ARTIFACT, {"request": run.request, "knowledge": [], "repository": {}, "explorer_scope": {}, "decision_history": explore_inputs.decision_history(run)}, explore.validate_request_profile)
    if explore_inputs.needs_clarification(profile) and not explore_inputs.has_explore_decision(run):
        questions = "; ".join(explore_inputs.clarification_questions(profile))
        return PhaseResult(decision_request=DecisionRequest(run.run_id, explore.CLARIFICATION_DECISION_ID, questions))
    return PhaseResult()
