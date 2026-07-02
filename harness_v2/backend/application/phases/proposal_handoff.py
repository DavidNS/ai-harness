"""PROPOSAL_HANDOFF phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phase_artifacts import handoff, shared_inputs


def execute(context: PhaseExecutionContext) -> PhaseResult:
    bundle = shared_inputs.read_purpose_bundle(context)
    context.artifacts.ensure_controller_json(context.run.run_id, "published/proposal-handoff.json", lambda: handoff.build_bundle_handoff("proposal", ["purpose/bundle.json"], "SPEC_BUNDLE", extra={"summary": bundle["summary"], "proposal_outcome": str(bundle["outcome"])}), handoff.validate_handoff)
    return PhaseResult()
