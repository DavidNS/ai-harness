"""Shared helpers for v2 phase functions."""

from __future__ import annotations

from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.phase_executor import PhaseExecutionContext


def _required_json(context: PhaseExecutionContext, artifact_id: str) -> dict[str, Any]:
    value = context.artifacts.read_json(context.run.run_id, artifact_id)
    if value is None:
        raise BundleValidationError(f"required artifact {artifact_id} is missing")
    return value


def _source_artifacts(context: PhaseExecutionContext, artifact_ids: tuple[str, ...]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for artifact_id in artifact_ids:
        if artifact_id.endswith(".json"):
            value = context.artifacts.read_json(context.run.run_id, artifact_id)
        else:
            value = context.artifacts.read_text(context.run.run_id, artifact_id)
        if value is None:
            raise BundleValidationError(f"required artifact {artifact_id} is missing")
        values[artifact_id] = value
    return values


