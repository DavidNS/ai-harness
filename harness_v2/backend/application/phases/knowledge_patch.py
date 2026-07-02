"""Knowledge patch phase implementation shared by knowledge bundles."""

from __future__ import annotations

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.contracts import KnowledgePatchCreated
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.common import _required_json
from harness_v2.backend.application.phases.knowledge_synthesis import _knowledge_source
from harness_v2.backend.domain.knowledge import parse_learning_proposal


def execute(context: PhaseExecutionContext) -> PhaseResult:
    if context.knowledge_patches is None:
        raise BundleValidationError(f"{context.bundle.value} requires a knowledge patch store")
    payload = _required_json(context, f"knowledge/{context.bundle.value}/synthesis.json")
    proposal = parse_learning_proposal(payload)
    source_bundle, _required = _knowledge_source(context.bundle)
    patch = context.knowledge_patches.create_patch(context.run.run_id, source_bundle, proposal, context.clock.now_iso())
    return PhaseResult(events=(KnowledgePatchCreated(context.run.run_id, patch.patch_id, patch.origin_bundle.value, patch.path),))
