"""Typed validators for staged explorer artifacts."""

from __future__ import annotations

import json
from typing import Any, Mapping

_CLAIM_CLASSES = frozenset({
    "repository-factual",
    "duplicate-check",
    "product-tradeoff",
    "artifact-synthesis",
})
_CLAIM_STATUSES = frozenset({"resolved", "unresolved", "not_applicable"})
_DECISION_OUTCOMES = frozenset({
    "new_improvement",
    "split_bundle",
    "update_existing",
    "duplicate_noop",
    "existing_functionality",
    "limitation",
    "not_worth_it",
    "needs_user_decision",
    "escalate_discovery",
})
_STRATEGIC_FRAMING_MODES = frozenset({"specific", "strategic", "needs_user_direction"})
_VALUE_DIMENSIONS = (
    "impact",
    "confidence",
    "cost",
    "reversibility",
    "evidence_strength",
)
_CRITIC_SEVERITIES = frozenset({"blocker", "warning", "note"})
_CRITIC_SEVERITY_ALIASES = {"info": "note"}

def _validation_error(message: str, cause: Exception | None = None) -> Exception:
    from .phases.base import PhaseValidationError

    error = PhaseValidationError(message)
    if cause is not None:
        error.__cause__ = cause
    return error


def _document(candidate: str) -> dict[str, Any]:
    if not isinstance(candidate, str) or not candidate.strip():
        raise _validation_error("explorer stage output must be nonempty JSON")
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise _validation_error("explorer stage output must be valid JSON", exc)
    if not isinstance(value, dict):
        raise _validation_error("explorer stage output must be a JSON object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _validation_error(f"{field} must be a nonempty string")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise _validation_error(f"{field} must be a list")
    return value


def _text_list(value: object, field: str, *, allow_empty: bool = True) -> list[str]:
    items = _list(value, field)
    if not allow_empty and not items:
        raise _validation_error(f"{field} must not be empty")
    for item in items:
        _text(item, field)
    return [str(item) for item in items]


def _optional_bool(value: object, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _validation_error(f"{field} must be a boolean")
    return value


def _optional_mapping(value: object, field: str) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _validation_error(f"{field} must be an object")
    return value


def _optional_object_list(value: object, field: str) -> list[Mapping[str, object]]:
    if value is None:
        return []
    items = _list(value, field)
    result: list[Mapping[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            raise _validation_error(f"{field} entries must be objects")
        result.append(item)
    return result


def _require_document(value: Mapping[str, object], phase: str) -> None:
    if value.get("schema_version") != 1 or value.get("phase") != phase:
        raise _validation_error(f"{phase} document version or phase is invalid")


def _validate_strategic_framing(value: object) -> None:
    framing = _optional_mapping(value, "strategic_framing")
    if framing is None:
        return
    mode = _text(framing.get("mode"), "strategic_framing mode")
    if mode not in _STRATEGIC_FRAMING_MODES:
        raise _validation_error("strategic_framing mode is invalid")
    _text_list(framing.get("value_targets", []), "strategic_framing value_targets")
    _optional_bool(framing.get("needs_user_direction"), "strategic_framing needs_user_direction")
    _optional_text(framing.get("rationale"), "strategic_framing rationale")


def _validate_candidate_directions(value: object) -> None:
    directions = _optional_object_list(value, "candidate_directions")
    seen: set[str] = set()
    for direction in directions:
        direction_id = _text(direction.get("id"), "candidate_directions id")
        if direction_id in seen:
            raise _validation_error("candidate_directions IDs must be unique")
        seen.add(direction_id)
        _text(direction.get("title"), "candidate_directions title")
        _text(direction.get("mechanism"), "candidate_directions mechanism")
        _text(direction.get("behavioral_delta"), "candidate_directions behavioral_delta")
        for dimension in _VALUE_DIMENSIONS:
            _text(direction.get(dimension), f"candidate_directions {dimension}")
        _text_list(direction.get("evidence", []), "candidate_directions evidence")


def _validate_critic_findings(value: object) -> None:
    findings = _optional_object_list(value, "critic_findings")
    for finding in findings:
        _text(finding.get("direction_id"), "critic_findings direction_id")
        severity = _text(finding.get("severity"), "critic_findings severity").casefold()
        severity = _CRITIC_SEVERITY_ALIASES.get(severity, severity)
        if severity not in _CRITIC_SEVERITIES:
            raise _validation_error("critic_findings severity is invalid")
        finding["severity"] = severity
        _text(finding.get("finding"), "critic_findings finding")
        _text(finding.get("recommendation"), "critic_findings recommendation")


def _validate_rejected_alternatives(value: object) -> None:
    alternatives = _optional_object_list(value, "rejected_alternatives")
    seen: set[str] = set()
    for alternative in alternatives:
        alternative_id = _text(alternative.get("id"), "rejected_alternatives id")
        if alternative_id in seen:
            raise _validation_error("rejected_alternatives IDs must be unique")
        seen.add(alternative_id)
        _text(alternative.get("reason"), "rejected_alternatives reason")


def validate_explorer_intake(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    _require_document(value, "explorer_intake")
    _validate_strategic_framing(value.get("strategic_framing"))
    claims = _list(value.get("claims"), "claims")
    if not claims:
        raise _validation_error("claims must be a nonempty list")
    seen: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            raise _validation_error("claim must be an object")
        claim_id = _text(claim.get("id"), "claim id")
        if claim_id in seen:
            raise _validation_error("claim IDs must be unique")
        seen.add(claim_id)
        claim_class = _text(claim.get("class"), "claim class")
        if claim_class not in _CLAIM_CLASSES:
            raise _validation_error("claim class is invalid")
        _text(claim.get("text"), "claim text")
        _text_list(claim.get("evidence_targets", []), "evidence_targets")
    _text_list(value.get("synthesis_notes", []), "synthesis_notes")
    return value


def validate_explorer_discovery(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    _require_document(value, "explorer_discovery")
    _validate_candidate_directions(value.get("candidate_directions"))
    _validate_critic_findings(value.get("critic_findings"))
    raw_claims = _list(value.get("claims"), "claims")
    if not raw_claims:
        raise _validation_error("discovery claims must be nonempty")
    seen: set[str] = set()
    for item in raw_claims:
        if not isinstance(item, dict):
            raise _validation_error("discovery claim must be an object")
        claim_id = _text(item.get("id"), "claim id")
        if claim_id in seen:
            raise _validation_error("discovery claim IDs must be unique")
        seen.add(claim_id)
        status = _text(item.get("status"), "claim status")
        if status not in _CLAIM_STATUSES:
            raise _validation_error("claim status is invalid")
        evidence = _text_list(item.get("evidence", []), "evidence")
        unresolved_reason = _optional_text(item.get("unresolved_reason"), "unresolved_reason")
        if status == "resolved" and not evidence:
            raise _validation_error("resolved claims require evidence")
        if status == "unresolved" and unresolved_reason is None:
            raise _validation_error("unresolved claims require unresolved_reason")
    _list(value.get("related_improvements", []), "related_improvements")
    _list(value.get("repository_observations", []), "repository_observations")
    return value


def validate_explorer_decision(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    _require_document(value, "explorer_decision")
    outcome = _text(value.get("outcome"), "outcome")
    if outcome not in _DECISION_OUTCOMES:
        raise _validation_error("explorer decision outcome is invalid")
    _text(value.get("rationale"), "rationale")
    evidence = _text_list(value.get("evidence", []), "evidence", allow_empty=False)
    _optional_text(value.get("selected_direction"), "selected_direction")
    _optional_text(value.get("value_hypothesis"), "value_hypothesis")
    _optional_text(value.get("behavioral_delta"), "behavioral_delta")
    _validate_rejected_alternatives(value.get("rejected_alternatives"))
    _text_list(value.get("counterevidence", []), "counterevidence")
    _text_list(value.get("falsifying_conditions", []), "falsifying_conditions")
    _optional_text(value.get("minimum_verification"), "minimum_verification")
    if outcome in {"update_existing", "duplicate_noop"}:
        target = value.get("target")
        if not isinstance(target, dict):
            raise _validation_error("duplicate/update decisions require target")
        _text(target.get("path"), "target path")
        _text(target.get("checksum"), "target checksum")
    if outcome == "needs_user_decision":
        request = value.get("decision_request")
        if not isinstance(request, dict):
            raise _validation_error("needs_user_decision requires decision_request")
        _text(request.get("question"), "decision question")
    if outcome == "escalate_discovery":
        _text(value.get("rediscovery_reason"), "rediscovery_reason")
    return value | {"evidence": evidence}


def validate_explorer_artifact(candidate: str) -> str:
    text = candidate.strip()
    if not text:
        raise _validation_error("explorer artifact candidate must be nonempty")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        from .phases.base import validate_explorer

        return validate_explorer(candidate)
    if not isinstance(value, dict):
        raise _validation_error("explorer artifact JSON must be an object")
    if value.get("kind") == "explorer_bundle":
        from .control_outputs import ExplorerBundle

        ExplorerBundle.from_mapping(value, expected_origin=str(value.get("origin_phase", "")))
        return candidate
    raise _validation_error("explorer artifact must be Markdown or explorer_bundle JSON")


def validate_explorer_review(candidate: str) -> str:
    from .phases.base import validate_review

    return validate_review(candidate)
