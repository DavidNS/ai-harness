"""Reusable JSON validation and repair phase."""

from __future__ import annotations

import json
from typing import Any, Callable

from harness_v2.backend.application.bundle_artifacts import BundleValidationError, loads_json
from harness_v2.backend.application.json_delta import apply_json_artifact_delta
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phase_artifacts import sdd
from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName
from harness_v2.backend.domain.tasks import TaskStatus, TaskSummary

JsonValidator = Callable[[dict[str, Any]], None]

_VALIDATORS: dict[PhaseName, tuple[str, JsonValidator]] = {
    PhaseName.PROPOSAL_DRAFT: ("purpose/bundle.json", sdd.validate_purpose_bundle),
    PhaseName.SPEC_DRAFT: ("spec.json", sdd.validate_spec_document),
    PhaseName.DESIGN_DRAFT: ("design.json", sdd.validate_design_document),
    PhaseName.TASKS_DRAFT: ("tasks.json", sdd.validate_tasks_document),
}


def execute(context: PhaseExecutionContext) -> PhaseResult:
    if context.run.current_step_id is None:
        raise BundleValidationError("validation phase requires an active step")
    current_step = bundle_catalog.step_for_step_id(context.run.root_bundle, context.run.current_step_id)
    if current_step.phase_name is not PhaseName.VALIDATE_JSON:
        raise BundleValidationError("validate_json handler can only run VALIDATE_JSON")
    if current_step.step_index == 0:
        raise BundleValidationError("validation phase has no previous step to validate")
    previous_step = bundle_catalog.linearize_bundle(context.run.root_bundle)[current_step.step_index - 1]
    try:
        artifact_id, validator = _VALIDATORS[previous_step.phase_name]
    except KeyError as exc:
        raise BundleValidationError(f"no JSON validator registered for {previous_step.phase_name.value}") from exc

    if previous_step.phase_name is PhaseName.PROPOSAL_DRAFT:
        explore_bundle = _required_explore_bundle(context)
        base_validator = validator

        def validator(value: dict[str, Any]) -> None:
            base_validator(value)
            sdd.validate_purpose_against_explore(value, explore_bundle)

    elif previous_step.phase_name is PhaseName.SPEC_DRAFT:
        explore_bundle = _required_explore_bundle(context)
        purpose = _required_purpose_bundle(context)
        base_validator = validator

        def validator(value: dict[str, Any]) -> None:
            base_validator(value)
            sdd.validate_spec_against_purpose_and_explore(value, purpose, explore_bundle)

    elif previous_step.phase_name is PhaseName.DESIGN_DRAFT:
        explore_bundle = _required_explore_bundle(context)
        purpose = _required_purpose_bundle(context)
        base_validator = validator

        def validator(value: dict[str, Any]) -> None:
            base_validator(value)
            sdd.validate_design_against_purpose_and_explore(value, purpose, explore_bundle)

    elif previous_step.phase_name is PhaseName.TASKS_DRAFT:
        explore_bundle = _required_explore_bundle(context)
        purpose = _required_purpose_bundle(context)
        base_validator = validator

        def validator(value: dict[str, Any]) -> None:
            base_validator(value)
            sdd.validate_tasks_against_purpose_and_explore(value, purpose, explore_bundle)

    value = _validated_or_repaired(context, artifact_id, previous_step.phase_name, validator)
    if previous_step.phase_name is PhaseName.TASKS_DRAFT:
        tasks = tuple(TaskSummary(str(item["id"]), str(item["title"]), TaskStatus.PENDING) for item in value["tasks"])
        return PhaseResult(tasks=tasks)
    return PhaseResult()


def _validated_or_repaired(
    context: PhaseExecutionContext,
    artifact_id: str,
    source_phase: PhaseName,
    validator: JsonValidator,
    *,
    max_repairs: int = 2,
) -> dict[str, Any]:
    raw = context.artifacts.read_text(context.run.run_id, artifact_id)
    if raw is None:
        raise BundleValidationError(f"required artifact {artifact_id} is missing")
    value, error = _load_and_validate(raw, artifact_id, validator)
    if error is None and value is not None:
        context.artifacts.write_json(context.run.run_id, artifact_id, value)
        return value

    current = value
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, max_repairs + 1):
        repair_inputs = {
            "target_artifact": artifact_id,
            "original_phase": source_phase.value,
            "current_artifact": current,
            "raw_stdout": raw,
            "validation_error": error,
            "schema_label": artifact_id,
            "repair_attempt": attempt,
        }
        repair_stdout = context.artifacts.run_worker_text(
            context.run,
            context.bundle or BundleName.SDD_BUNDLE,
            PhaseName.VALIDATE_JSON,
            "artifact_delta_repair",
            repair_inputs,
        )
        attempt_record: dict[str, Any] = {"attempt": attempt, "validation_error": error}
        repaired: dict[str, Any] | None = None
        try:
            delta = loads_json(repair_stdout, "artifact_delta_repair")
            attempt_record["delta"] = delta
            repaired = apply_json_artifact_delta(delta, target_artifact=artifact_id, current_artifact=current)
            validator(repaired)
        except Exception as exc:
            error = str(exc) or type(exc).__name__
            attempt_record["repair_error"] = error
            attempts.append(attempt_record)
            _write_repair_diagnostic(context, artifact_id, attempts)
            if repaired is not None:
                current = repaired
            continue
        attempt_record["status"] = "repaired"
        attempts.append(attempt_record)
        context.artifacts.write_json(context.run.run_id, artifact_id, repaired)
        _write_repair_diagnostic(context, artifact_id, attempts)
        return repaired

    _write_repair_diagnostic(context, artifact_id, attempts)
    raise BundleValidationError(f"artifact {artifact_id} could not be repaired: {error}")


def _load_and_validate(text: str, label: str, validator: JsonValidator) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"{label} output is not JSON: {exc.msg}"
    if not isinstance(value, dict):
        return None, f"{label} output must be a JSON object"
    try:
        validator(value)
    except Exception as exc:
        return value, str(exc) or type(exc).__name__
    return value, None


def _required_explore_bundle(context: PhaseExecutionContext) -> dict[str, Any]:
    return _required_json_artifact(context, "explore/outcome_bundle.json")


def _required_purpose_bundle(context: PhaseExecutionContext) -> dict[str, Any]:
    return _required_json_artifact(context, "purpose/bundle.json")


def _required_json_artifact(context: PhaseExecutionContext, artifact_id: str) -> dict[str, Any]:
    value = context.artifacts.read_json(context.run.run_id, artifact_id)
    if value is None:
        raise BundleValidationError(f"required artifact {artifact_id} is missing")
    if not isinstance(value, dict):
        raise BundleValidationError(f"required artifact {artifact_id} must be a JSON object")
    return value


def _write_repair_diagnostic(context: PhaseExecutionContext, artifact_id: str, attempts: list[dict[str, Any]]) -> None:
    if context.run.current_step_id is None:
        return
    safe_step = context.run.current_step_id.replace(":", "_")
    safe_artifact = artifact_id.replace("/", "_").replace(":", "_")
    context.artifacts.write_json(
        context.run.run_id,
        f"validation/{safe_step}-{safe_artifact}-repair.json",
        {"schema_version": 1, "artifact_id": artifact_id, "attempts": attempts},
    )
