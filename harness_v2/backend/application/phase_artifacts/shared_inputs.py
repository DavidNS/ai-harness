"""Shared phase input readers."""

from __future__ import annotations

from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.json_schema import validate_json_schema
from harness_v2.backend.application.phase_executor import PhaseExecutionContext


def read_explore_bundle_view(context: PhaseExecutionContext) -> dict[str, Any]:
    value = context.artifacts.read_json(context.run.run_id, "explore/outcome_bundle.json")
    if value is None:
        raise BundleValidationError("required artifact explore/outcome_bundle.json is missing")
    validate_json_schema(value, "outcome_bundle")
    return value


def read_purpose_bundle(context: PhaseExecutionContext) -> dict[str, Any]:
    value = context.artifacts.read_json(context.run.run_id, "purpose/bundle.json")
    if value is None:
        raise BundleValidationError("required artifact purpose/bundle.json is missing")
    validate_json_schema(value, "purpose_bundle")
    return value


def read_required_json(context: PhaseExecutionContext, artifact_id: str, schema_name: str) -> dict[str, Any]:
    value = context.artifacts.read_json(context.run.run_id, artifact_id)
    if value is None:
        raise BundleValidationError(f"required artifact {artifact_id} is missing")
    validate_json_schema(value, schema_name)
    return value

