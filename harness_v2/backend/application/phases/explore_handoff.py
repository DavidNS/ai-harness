"""EXPLORE_HANDOFF phase."""

from __future__ import annotations

from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.decision_service import DecisionRequest
from harness_v2.backend.application.phase_artifacts import explore, explore_builders
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.common import _required_json
from harness_v2.backend.domain.decisions import DecisionAction, DecisionEffect
from harness_v2.backend.domain.escalation import EscalationCategory

_NONE_OF_ABOVE = "none_of_above"


def execute(context: PhaseExecutionContext) -> PhaseResult:
    synthesis = _required_json(context, explore.OUTCOME_SYNTHESIS_ARTIFACT)
    digest = _required_json(context, explore.EVIDENCE_DIGEST_ARTIFACT)
    exploration_map = _required_json(context, explore.EXPLORATION_MAP_ARTIFACT)
    bundle = context.artifacts.ensure_controller_json(context.run.run_id, explore.OUTCOME_BUNDLE_ARTIFACT, lambda: explore_builders.build_outcome_bundle(synthesis, digest, exploration_map), explore.validate_outcome_bundle)
    decision = _ask_user_decision(context, bundle)
    if decision is not None:
        return PhaseResult(decision_request=decision)
    manifest = context.artifacts.ensure_controller_json(context.run.run_id, explore.MANIFEST_ARTIFACT, lambda: explore_builders.build_manifest(bundle), explore.validate_manifest)
    context.artifacts.ensure_controller_json(context.run.run_id, explore.HANDOFF_ARTIFACT, lambda: explore_builders.build_handoff(bundle, manifest), explore.validate_handoff)
    return PhaseResult()


def _ask_user_decision(context: PhaseExecutionContext, bundle: dict[str, Any]) -> DecisionRequest | None:
    for entry in bundle.get("entries", []):
        if not isinstance(entry, dict) or entry.get("action") != "ask_user":
            continue
        decision_id = _decision_id(entry)
        if _decision_answered(context, decision_id):
            raise BundleValidationError(f"explore decision {decision_id} was already answered but outcome still asks the user")
        options = _options(entry)
        effects = tuple(DecisionEffect(option, DecisionAction.ESCALATE, EscalationCategory.EXPLORATION_GAP) for option in options)
        return DecisionRequest(
            context.run.run_id,
            decision_id,
            _text(entry.get("question")) or _text(entry.get("title")) or "Choose an EXPLORE direction",
            options,
            effects=effects,
            default_action=DecisionAction.ESCALATE,
            default_category=EscalationCategory.EXPLORATION_GAP,
        )
    return None


def _decision_answered(context: PhaseExecutionContext, decision_id: str) -> bool:
    return any(record.decision_id == decision_id for record in context.run.decision_history)


def _decision_id(entry: dict[str, Any]) -> str:
    explicit = _text(entry.get("decision_id"))
    if explicit:
        return explicit
    entry_id = _text(entry.get("id")) or "entry"
    return f"explore-{entry_id}-decision"


def _options(entry: dict[str, Any]) -> tuple[str, ...]:
    options: list[str] = []
    raw = entry.get("options")
    if isinstance(raw, list):
        for item in raw:
            option = _text(item)
            if option and option not in options:
                options.append(option)
    if _NONE_OF_ABOVE not in options:
        options.append(_NONE_OF_ABOVE)
    return tuple(options)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
