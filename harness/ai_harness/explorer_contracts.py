"""Typed validators for staged explorer artifacts."""

from __future__ import annotations

import json
import re
from pathlib import PurePath
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
_TRACE_CONFIDENCES = frozenset({"low", "medium", "high", "critical"})


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


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise _validation_error(f"{field} must be an object")
    return value


def _object_list(value: object, field: str, *, allow_empty: bool = True) -> list[Mapping[str, object]]:
    items = _list(value, field)
    if not allow_empty and not items:
        raise _validation_error(f"{field} must not be empty")
    result: list[Mapping[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            raise _validation_error(f"{field} entries must be objects")
        result.append(item)
    return result


def _safe_relative_path(value: object, field: str) -> str:
    text = _text(value, field).replace("\\", "/")
    path = PurePath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise _validation_error(f"{field} must be a safe repository-relative path")
    return text


def _validate_evidence_trace(value: object, claim_ids: set[str]) -> None:
    trace = _object_list(value, "evidence_trace")
    seen: set[str] = set()
    for item in trace:
        trace_id = _text(item.get("id"), "evidence_trace id")
        if trace_id in seen:
            raise _validation_error("evidence_trace IDs must be unique")
        seen.add(trace_id)
        claim_id = _text(item.get("claim_id"), "evidence_trace claim_id")
        if claim_id not in claim_ids:
            raise _validation_error("evidence_trace claim_id must reference a discovery claim")
        _text(item.get("source"), "evidence_trace source")
        _safe_relative_path(item.get("path"), "evidence_trace path")
        if item.get("line_start") is not None and not isinstance(item.get("line_start"), int):
            raise _validation_error("evidence_trace line_start must be an integer")
        if item.get("line_end") is not None and not isinstance(item.get("line_end"), int):
            raise _validation_error("evidence_trace line_end must be an integer")
        _optional_text(item.get("symbol"), "evidence_trace symbol")
        _text(item.get("excerpt"), "evidence_trace excerpt")
        confidence = _text(item.get("confidence"), "evidence_trace confidence")
        if confidence not in _TRACE_CONFIDENCES:
            raise _validation_error("evidence_trace confidence is invalid")


def _validate_duplicate_search(value: object, claim_ids: set[str]) -> None:
    duplicate_search = _mapping(value, "duplicate_search")
    _text_list(duplicate_search.get("searched_terms"), "duplicate_search searched_terms")
    _text_list(duplicate_search.get("searched_surfaces"), "duplicate_search searched_surfaces")
    for item in _object_list(duplicate_search.get("matches"), "duplicate_search matches"):
        _optional_text(item.get("claim_id"), "duplicate_search match claim_id")
        if item.get("claim_id") is not None and item.get("claim_id") not in claim_ids:
            raise _validation_error("duplicate_search match claim_id must reference a discovery claim")
        _safe_relative_path(item.get("path"), "duplicate_search match path")
        _optional_text(item.get("symbol"), "duplicate_search match symbol")
        _optional_text(item.get("excerpt"), "duplicate_search match excerpt")
        _optional_text(item.get("confidence"), "duplicate_search match confidence")
    for item in _object_list(duplicate_search.get("no_match_claims"), "duplicate_search no_match_claims"):
        claim_id = _text(item.get("claim_id"), "duplicate_search no_match_claim claim_id")
        if claim_id not in claim_ids:
            raise _validation_error("duplicate_search no_match_claim claim_id must reference a discovery claim")
        _text(item.get("searched_for"), "duplicate_search no_match_claim searched_for")
        _text(item.get("confidence"), "duplicate_search no_match_claim confidence")


def _mentions_repository_observations(value: object) -> bool:
    if isinstance(value, str):
        normalized = re.sub(r"[\s_-]+", " ", value.casefold())
        return "repository observation" in normalized or "supplied observation" in normalized
    if isinstance(value, list):
        return any(_mentions_repository_observations(item) for item in value)
    if isinstance(value, dict):
        return any(_mentions_repository_observations(item) for item in value.values())
    return False


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
    related_improvements = _list(value.get("related_improvements", []), "related_improvements")
    repository_observations = _list(value.get("repository_observations", []), "repository_observations")
    del related_improvements
    _validate_evidence_trace(value.get("evidence_trace"), seen)
    _validate_duplicate_search(value.get("duplicate_search"), seen)
    if not repository_observations and _mentions_repository_observations({
        "claims": value.get("claims", []),
        "candidate_directions": value.get("candidate_directions", []),
        "critic_findings": value.get("critic_findings", []),
    }):
        raise _validation_error("discovery cites repository observations but repository_observations is empty")
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
