"""Reusable JSON validation phase."""

from __future__ import annotations

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phase_artifacts import sdd
from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.lifecycle import PhaseName


_VALIDATORS = {
    PhaseName.SPEC_DRAFT: ("spec.json", sdd.validate_spec_document),
    PhaseName.DESIGN_DRAFT: ("design.json", sdd.validate_design_document),
    PhaseName.TASKS_DRAFT: ("tasks.json", sdd.validate_tasks_document),
}


def execute(context: PhaseExecutionContext) -> PhaseResult:
    if context.run.current_step_id is None:
        raise BundleValidationError("validation phase requires an active step")
    current_step = bundle_catalog.step_for_step_id(context.run.root_bundle, context.run.current_step_id)
    if current_step.step_index == 0:
        raise BundleValidationError("validation phase has no previous step to validate")
    previous_step = bundle_catalog.linearize_bundle(context.run.root_bundle)[current_step.step_index - 1]
    try:
        artifact_id, validator = _VALIDATORS[previous_step.phase_name]
    except KeyError as exc:
        raise BundleValidationError(f"no JSON validator registered for {previous_step.phase_name.value}") from exc
    value = context.artifacts.read_json(context.run.run_id, artifact_id)
    if value is None:
        raise BundleValidationError(f"required artifact {artifact_id} is missing")
    validator(value)
    return PhaseResult()
