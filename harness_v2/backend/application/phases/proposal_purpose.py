"""PROPOSAL_DRAFT phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phase_artifacts import shared_inputs
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


def execute(context: PhaseExecutionContext) -> PhaseResult:
    run = context.run
    context.artifacts.ensure_worker_json_candidate(
        run,
        BundleName.PROPOSAL_BUNDLE,
        PhaseName.PROPOSAL_DRAFT,
        "purpose",
        "purpose/bundle.json",
        {
            "request": run.request,
            "explore_bundle_view": shared_inputs.read_explore_bundle_view(context),
            "explorer_scope": {},
        },
    )
    return PhaseResult()
