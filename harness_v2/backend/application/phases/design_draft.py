"""DESIGN_DRAFT phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phase_artifacts import shared_inputs
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


def execute(context: PhaseExecutionContext) -> PhaseResult:
    context.artifacts.ensure_worker_json_candidate(
        context.run,
        BundleName.DESIGN_BUNDLE,
        PhaseName.DESIGN_DRAFT,
        "design",
        "design.json",
        {
            "explore_bundle_view": shared_inputs.read_explore_bundle_view(context),
            "purpose/bundle.json": shared_inputs.read_purpose_bundle(context),
            "spec.json": shared_inputs.read_required_json(context, "spec.json", "spec_document"),
            "explorer_scope": {},
        },
    )
    return PhaseResult()
