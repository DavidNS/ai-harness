"""EXPLORE_HANDOFF phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_artifacts import explore, explore_builders
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.common import _required_json


def execute(context: PhaseExecutionContext) -> PhaseResult:
    synthesis = _required_json(context, explore.OUTCOME_SYNTHESIS_ARTIFACT)
    digest = _required_json(context, explore.EVIDENCE_DIGEST_ARTIFACT)
    exploration_map = _required_json(context, explore.EXPLORATION_MAP_ARTIFACT)
    bundle = context.artifacts.ensure_controller_json(context.run.run_id, explore.OUTCOME_BUNDLE_ARTIFACT, lambda: explore_builders.build_outcome_bundle(synthesis, digest, exploration_map), explore.validate_outcome_bundle)
    context.artifacts.ensure_controller_json(context.run.run_id, explore.HANDOFF_ARTIFACT, lambda: explore_builders.build_handoff(bundle), explore.validate_handoff)
    return PhaseResult()
