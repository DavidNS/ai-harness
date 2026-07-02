"""DESIGN_HANDOFF phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phase_artifacts import handoff


def execute(context: PhaseExecutionContext) -> PhaseResult:
    context.artifacts.ensure_controller_json(context.run.run_id, "published/design-handoff.json", lambda: handoff.build_bundle_handoff("design", ["design.json"], "TASKS_BUNDLE"), handoff.validate_handoff)
    return PhaseResult()
