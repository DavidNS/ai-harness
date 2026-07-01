"""Explorer-specific decision recovery helpers."""

from __future__ import annotations

from typing import Any

from harness_v2.backend.application.bundle_orchestration import BundleContext, BundleExecutionResult, PhaseRecoveryRequest
from harness_v2.backend.application.contracts import InvalidRunStateError
from harness_v2.backend.application.decision_service import DecisionRequest
from harness_v2.backend.domain.decisions import DecisionAction
from harness_v2.backend.domain.lifecycle import PhaseName

EXPLORER_REFINEMENT_DECISION_ID = "explorer-refinement"
REFINEMENT_ARTIFACT = "explorer/refinement.json"


def handle_explorer_decision(context: BundleContext, decision: dict[str, Any]) -> BundleExecutionResult | None:
    outcome = decision.get("outcome")
    if outcome == "needs_user_decision":
        return BundleExecutionResult(
            decision_request=DecisionRequest(
                context.run.run_id,
                EXPLORER_REFINEMENT_DECISION_ID,
                explorer_decision_prompt(decision),
                default_action=DecisionAction.ESCALATE,
                default_target_phase=PhaseName.EXPLORER_DISCOVERY,
            )
        )
    if outcome == "escalate_discovery":
        return BundleExecutionResult(
            recovery_request=PhaseRecoveryRequest(
                PhaseName.EXPLORER_DISCOVERY,
                _text(decision.get("rationale"), "rationale"),
            )
        )
    return None


def explorer_decision_prompt(decision: dict[str, Any]) -> str:
    lines = ["Explorer needs user refinement before rediscovery."]
    for field in ("rationale", "selected_direction", "value_hypothesis", "behavioral_delta", "minimum_verification"):
        value = decision.get(field)
        if isinstance(value, str) and value.strip():
            lines.append(f"{field}: {value.strip()}")
    evidence = decision.get("evidence")
    if isinstance(evidence, list) and evidence:
        lines.append("evidence: " + "; ".join(str(item).strip() for item in evidence if str(item).strip()))
    return "\n".join(lines)


def ensure_refinement_artifact(context: BundleContext) -> None:
    if context.artifacts.read_json(context.run.run_id, REFINEMENT_ARTIFACT) is not None:
        return
    record = latest_explorer_refinement(context.run)
    if record is None:
        return
    context.artifacts.write_json(
        context.run.run_id,
        REFINEMENT_ARTIFACT,
        {
            "schema_version": 1,
            "phase": "explorer_refinement",
            "decision_id": record.decision_id,
            "origin_phase": record.origin_phase.value,
            "response": record.response,
            "answered_at": record.answered_at,
        },
    )


def latest_explorer_refinement(run: Any) -> Any | None:
    for record in reversed(run.decision_history):
        if record.decision_id == EXPLORER_REFINEMENT_DECISION_ID and record.origin_phase is PhaseName.EXPLORER_DECISION:
            return record
    return None




def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidRunStateError(f"{field} must be a nonempty string")
    return value.strip()
