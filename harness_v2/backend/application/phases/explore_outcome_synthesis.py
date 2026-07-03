"""EXPLORE_OUTCOME_SYNTHESIS phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_artifacts import explore, explore_inputs, explore_mappers
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.common import _required_json
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


def execute(context: PhaseExecutionContext) -> PhaseResult:
    run = context.run
    profile = _required_json(context, explore.REQUEST_PROFILE_ARTIFACT)
    context_pack = _required_json(context, explore.CONTEXT_PACK_ARTIFACT)
    digest = _required_json(context, explore.EVIDENCE_DIGEST_ARTIFACT)
    exploration_map = _required_json(context, explore.EXPLORATION_MAP_ARTIFACT)
    context.artifacts.ensure_worker_json(run, BundleName.EXPLORE_BUNDLE, PhaseName.EXPLORE_OUTCOME_SYNTHESIS, explore.OUTCOME_SYNTHESIS_TASK, explore.OUTCOME_SYNTHESIS_ARTIFACT, {"request": run.request, "request_profile": profile, "context_pack": explore_mappers.compact_context_pack(context_pack), "decision_history": explore_inputs.decision_history(run), "evidence": explore_mappers.evidence_items(digest), "exploration_map": exploration_map}, explore.validate_outcome_synthesis)
    return PhaseResult()
