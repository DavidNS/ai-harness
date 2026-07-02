"""Knowledge synthesis phase implementation shared by knowledge bundles."""

from __future__ import annotations

import json

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.common import _source_artifacts
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


def execute(context: PhaseExecutionContext) -> PhaseResult:
    source_bundle, required = _knowledge_source(context.bundle)
    source_artifacts = _source_artifacts(context, required)
    output = context.artifacts.run_worker_text(context.run, context.bundle or BundleName.KNOWLEDGE_EXTRACT_EXPLORE, context.phase or PhaseName.KNOWLEDGE_EXTRACT_EXPLORE_SYNTHESIS, "knowledge_synthesis", {"run_id": context.run.run_id, "request": context.run.request, "source_phase": source_bundle.value.lower(), "source_artifacts": source_artifacts})
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise BundleValidationError("knowledge_synthesis output must be valid JSON") from exc
    context.artifacts.write_json(context.run.run_id, f"knowledge/{context.bundle.value}/synthesis.json", payload)
    return PhaseResult()


def _knowledge_source(bundle: BundleName | None) -> tuple[BundleName, tuple[str, ...]]:
    if bundle is BundleName.KNOWLEDGE_EXTRACT_TDD:
        return BundleName.TDD_BUNDLE, ("published/tdd-results.json", "published/tdd-handoff.json")
    return BundleName.EXPLORE_BUNDLE, ("explore/outcome_bundle.json", "published/explore-handoff.json")
