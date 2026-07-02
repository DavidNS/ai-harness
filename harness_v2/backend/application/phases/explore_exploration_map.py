"""EXPLORE_EXPLORATION_MAP phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_artifacts import explore, explore_builders
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.common import _required_json


def execute(context: PhaseExecutionContext) -> PhaseResult:
    profile = _required_json(context, explore.REQUEST_PROFILE_ARTIFACT)
    context_pack = _required_json(context, explore.CONTEXT_PACK_ARTIFACT)
    digest = _required_json(context, explore.EVIDENCE_DIGEST_ARTIFACT)
    context.artifacts.ensure_controller_json(context.run.run_id, explore.EXPLORATION_MAP_ARTIFACT, lambda: explore_builders.build_exploration_map(digest, profile=profile, context_pack=context_pack), lambda value: explore.validate_exploration_map(value, explore.evidence_ids(digest)))
    return PhaseResult()
