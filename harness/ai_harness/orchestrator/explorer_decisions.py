"""Decision-gate validation for explorer stages."""

from __future__ import annotations

from typing import Mapping

from ..control_outputs import DecisionRequest
from ..errors import HarnessError


def decision_request_from_explorer_decision(decision: Mapping[str, object]) -> DecisionRequest:
    request = decision.get("decision_request")
    if not isinstance(request, dict):
        raise HarnessError("explorer decision requires a decision_request object")
    payload = {
        "schema_version": 1,
        "kind": "decision_request",
        "origin_phase": "EXPLORER_DECISION",
        "reason": str(decision.get("rationale", "A product decision is required.")),
        "question": request.get("question"),
        "context": request.get("context", decision.get("evidence", [])),
        "options": request.get("options", []),
        "allows_freeform": request.get("allows_freeform", True),
        "scores": request.get("scores", {}),
        "score_signals": request.get("score_signals", {}),
        "ranked_paths": request.get("ranked_paths", []),
        "option_details": request.get("option_details", {}),
    }
    return DecisionRequest.from_mapping(payload, expected_origin="EXPLORER_DECISION")


def _nonempty_decision_text(value: Mapping[str, object], field: str) -> str:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise HarnessError(f"explorer value gate requires {field}")
    return raw.strip()


def _nonempty_decision_list(value: Mapping[str, object], field: str) -> list[object]:
    raw = value.get(field)
    if not isinstance(raw, list) or not raw:
        raise HarnessError(f"explorer value gate requires {field}")
    if not all(isinstance(item, (str, dict)) and str(item).strip() for item in raw):
        raise HarnessError(f"explorer value gate requires nonempty {field} entries")
    return raw


def _discovery_candidates(discovery: Mapping[str, object]) -> list[dict[str, object]]:
    raw = discovery.get("candidate_directions", [])
    if not isinstance(raw, list):
        raise HarnessError("explorer candidate_directions must be a list")
    candidates: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise HarnessError("explorer candidate_directions entries must be objects")
        candidate_id = item.get("id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise HarnessError("explorer candidate_directions entries require id")
        candidates.append(dict(item))
    return candidates


def _rejected_direction_ids(discovery: Mapping[str, object]) -> set[str]:
    raw = discovery.get("critic_findings", [])
    if not isinstance(raw, list):
        raise HarnessError("explorer critic_findings must be a list")
    rejected: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        verdict = str(item.get("verdict", item.get("status", ""))).casefold().replace("-", "_")
        severity = str(item.get("severity", "")).casefold()
        recommendation = str(item.get("recommendation", "")).casefold()
        if verdict not in {"reject", "rejected"} and severity != "blocker" and "reject" not in recommendation:
            continue
        direction_id = item.get("direction_id", item.get("candidate_id"))
        if isinstance(direction_id, str) and direction_id.strip():
            rejected.add(direction_id)
    return rejected


def _metadata_only_without_consumer(candidate: Mapping[str, object] | None, decision: Mapping[str, object]) -> bool:
    text = " ".join(
        str(value)
        for value in (
            decision.get("value_hypothesis", ""),
            decision.get("behavioral_delta", ""),
            None if candidate is None else candidate.get("mechanism", ""),
            None if candidate is None else candidate.get("behavioral_delta", ""),
        )
    ).casefold()
    metadata_terms = ("metadata", "prose", "prompt-only", "prompt only", "documentation-only", "documentation only")
    if not any(term in text for term in metadata_terms):
        return False
    consumer_terms = ("workflow", "gate", "route", "routing", "review", "validation", "user", "console", "controller")
    return not any(term in text for term in consumer_terms)


def validate_explorer_value_gate(decision: Mapping[str, object], discovery: Mapping[str, object]) -> None:
    outcome = str(decision.get("outcome", ""))
    if outcome not in {"new_improvement", "split_bundle", "update_existing"}:
        return
    candidates = _discovery_candidates(discovery)
    candidates_by_id = {str(item["id"]): item for item in candidates}
    selected = decision.get("selected_direction")
    if candidates:
        if not isinstance(selected, str) or not selected.strip():
            raise HarnessError("explorer value gate requires selected_direction")
        if selected not in candidates_by_id:
            raise HarnessError("explorer value gate selected an unknown direction")
        if selected in _rejected_direction_ids(discovery):
            raise HarnessError("explorer value gate selected a rejected direction")

    _nonempty_decision_text(decision, "value_hypothesis")
    _nonempty_decision_text(decision, "behavioral_delta")
    _nonempty_decision_list(decision, "rejected_alternatives")
    if not decision.get("counterevidence") and not decision.get("falsifying_conditions"):
        raise HarnessError("explorer value gate requires counterevidence or falsifying_conditions")
    if decision.get("counterevidence"):
        _nonempty_decision_list(decision, "counterevidence")
    if decision.get("falsifying_conditions"):
        _nonempty_decision_list(decision, "falsifying_conditions")
    _nonempty_decision_text(decision, "minimum_verification")

    rejected = {
        str(item.get("id", item)).strip() if isinstance(item, dict) else str(item).strip()
        for item in decision.get("rejected_alternatives", [])
    }
    if isinstance(selected, str) and selected in rejected:
        raise HarnessError("explorer value gate cannot select a rejected alternative")
    selected_candidate = candidates_by_id.get(str(selected)) if isinstance(selected, str) else None
    if _metadata_only_without_consumer(selected_candidate, decision):
        raise HarnessError("explorer value gate rejects metadata-only directions without downstream behavior")
