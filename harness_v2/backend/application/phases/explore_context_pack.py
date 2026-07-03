"""EXPLORE_CONTEXT_PACK phase."""

from __future__ import annotations

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.phase_artifacts import explore, explore_builders
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult


def execute(context: PhaseExecutionContext) -> PhaseResult:
    profile = context.artifacts.read_json(context.run.run_id, explore.REQUEST_PROFILE_ARTIFACT)
    if profile is None:
        raise BundleValidationError("request profile is missing")
    context.artifacts.ensure_controller_json(context.run.run_id, explore.CONTEXT_PACK_ARTIFACT, lambda: explore_builders.build_context_pack(context.run, profile, context.artifacts, repository_root=context.runtime.working_directory), explore.validate_context_pack)
    return PhaseResult()
