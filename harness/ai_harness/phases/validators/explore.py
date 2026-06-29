"""Validators for the restructured EXPLORE pipeline artifacts."""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..errors import PhaseValidationError
from .review import validate_review

_BUNDLE_STATUSES = frozenset({"ready_for_purpose", "needs_clarification", "problem_gathering_info"})
_ENTRY_CLASSIFICATIONS = frozenset({"improvement", "limitation", "bullshit"})
_CLAIM_STATUSES = frozenset({
    "supported",
    "contradicted",
    "partially_supported",
    "unresolved",
    "not_applicable",
    "blocked",
})
_COMPLEXITIES = frozenset({"typo", "local_change", "multi_file", "cross_cutting", "architecture", "migration"})
_AMBIGUITIES = frozenset({"clear", "partial", "high", "blocked_by_product_decision"})
_NOVELTIES = frozenset({"known_repo_pattern", "low", "medium", "high", "uncertain_feasibility"})
_RISKS = frozenset({"low", "medium", "high", "critical"})
_EVIDENCE_DEPTHS = frozenset({"light", "standard", "deep"})
_GATHERERS = frozenset({"code", "git", "gitlab", "web", "knowledge", "ci"})
_CI_REQUIREMENTS = frozenset({"required", "optional", "not_needed"})
_CI_STATUSES = frozenset({"ready", "unavailable", "not_needed"})


def _validation_error(message: str, cause: Exception | None = None) -> PhaseValidationError:
    error = PhaseValidationError(message)
    if cause is not None:
        error.__cause__ = cause
    return error


def _document(candidate: str) -> dict[str, Any]:
    if not isinstance(candidate, str) or not candidate.strip():
        raise _validation_error("explore stage output must be nonempty JSON")
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise _validation_error("explore stage output must be valid JSON", exc)
    if not isinstance(value, dict):
        raise _validation_error("explore stage output must be a JSON object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _validation_error(f"{field} must be a nonempty string")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise _validation_error(f"{field} must be an object")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise _validation_error(f"{field} must be a list")
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


def _optional_object_list(value: object, field: str) -> list[Mapping[str, object]]:
    if value is None:
        return []
    return _object_list(value, field)


def _text_list(value: object, field: str, *, allow_empty: bool = True) -> list[str]:
    items = _list(value, field)
    if not allow_empty and not items:
        raise _validation_error(f"{field} must not be empty")
    result: list[str] = []
    for item in items:
        result.append(_text(item, field))
    return result


def _optional_text_list(value: object, field: str) -> list[str]:
    if value is None:
        return []
    return _text_list(value, field)


def _require_stage(value: Mapping[str, object], phase: str) -> None:
    if value.get("schema_version") != 1 or value.get("phase") != phase:
        raise _validation_error(f"{phase} document version or phase is invalid")


def _enum(value: object, field: str, allowed: frozenset[str]) -> str:
    text = _text(value, field)
    if text not in allowed:
        raise _validation_error(f"{field} is invalid")
    return text


def _validate_sources(value: object, field: str) -> None:
    for source in _optional_object_list(value, field):
        _enum(source.get("type"), f"{field} type", frozenset({"file", "artifact", "git", "gitlab", "web", "knowledge", "ci"}))
        if not (_optional_text(source.get("path"), f"{field} path") or _optional_text(source.get("url"), f"{field} url") or _optional_text(source.get("description"), f"{field} description")):
            raise _validation_error(f"{field} entries require path, url, or description")


def _validate_evidence_items(value: object, field: str, *, allow_empty: bool) -> list[Mapping[str, object]]:
    evidence = _object_list(value, field, allow_empty=allow_empty)
    seen: set[str] = set()
    for item in evidence:
        evidence_id = _text(item.get("id"), f"{field} id")
        if evidence_id in seen:
            raise _validation_error(f"{field} IDs must be unique")
        seen.add(evidence_id)
        _text(item.get("claim"), f"{field} claim")
        _enum(item.get("status"), f"{field} status", _CLAIM_STATUSES)
        _optional_text(item.get("confidence"), f"{field} confidence")
        _validate_sources(item.get("sources", []), f"{field} sources")
    return evidence


def validate_explore_request_understanding(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    _require_stage(value, "explore_request_understanding")
    _text(value.get("intent"), "intent")
    _text(value.get("summary"), "summary")
    _text_list(value.get("mentioned_surfaces", []), "mentioned_surfaces")
    _text_list(value.get("explicit_constraints", []), "explicit_constraints")
    _text_list(value.get("unclear_parts", []), "unclear_parts")
    _text(value.get("request_type"), "request_type")
    return value


def validate_explore_clarification_gate(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    _require_stage(value, "explore_clarification_gate")
    status = _enum(value.get("status"), "status", frozenset({"continue", "needs_clarification"}))
    questions = _text_list(value.get("clarification_questions", []), "clarification_questions")
    if status == "needs_clarification" and not questions:
        raise _validation_error("needs_clarification requires clarification_questions")
    _text(value.get("rationale"), "rationale")
    return value


def validate_explore_triage(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    _require_stage(value, "explore_triage")
    _enum(value.get("complexity"), "complexity", _COMPLEXITIES)
    _enum(value.get("ambiguity"), "ambiguity", _AMBIGUITIES)
    _enum(value.get("novelty"), "novelty", _NOVELTIES)
    _enum(value.get("risk"), "risk", _RISKS)
    _enum(value.get("evidence_depth"), "evidence_depth", _EVIDENCE_DEPTHS)
    _text(value.get("rationale"), "rationale")
    return value


def validate_explore_evidence_plan(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    _require_stage(value, "explore_evidence_plan")
    for field in ("required_gatherers", "optional_gatherers"):
        for gatherer in _text_list(value.get(field, []), field):
            if gatherer not in _GATHERERS:
                raise _validation_error(f"{field} contains unsupported gatherer")
    _text_list(value.get("questions"), "questions", allow_empty=False)
    _enum(value.get("ci_requirement", "not_needed"), "ci_requirement", _CI_REQUIREMENTS)
    skip_reason = value.get("skip_reason", {})
    if not isinstance(skip_reason, dict):
        raise _validation_error("skip_reason must be an object")
    return value


def validate_explore_evidence_collection(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    _require_stage(value, "explore_evidence_collection")
    _validate_evidence_items(value.get("evidence", []), "evidence", allow_empty=True)
    for blocker in _optional_object_list(value.get("blockers"), "blockers"):
        _text(blocker.get("gatherer"), "blocker gatherer")
        _text(blocker.get("reason"), "blocker reason")
    return value


def validate_explore_ci_barrier(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    _require_stage(value, "explore_ci_barrier")
    requirement = _enum(value.get("ci_requirement"), "ci_requirement", _CI_REQUIREMENTS)
    status = _enum(value.get("status"), "status", _CI_STATUSES)
    _validate_evidence_items(value.get("evidence", []), "evidence", allow_empty=True)
    blockers = _optional_text_list(value.get("blockers"), "blockers")
    if requirement == "required" and status == "unavailable" and not blockers:
        raise _validation_error("unavailable required CI evidence requires blockers")
    return value


def validate_explore_evidence_normalization(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    _require_stage(value, "explore_evidence_normalization")
    _validate_evidence_items(value.get("evidence"), "evidence", allow_empty=True)
    return value


def validate_explore_outcome_bundle(candidate: str) -> dict[str, Any]:
    value = _document(candidate)
    if value.get("schema_version") != 1 or value.get("kind") != "explore_outcome_bundle":
        raise _validation_error("explore outcome bundle version or kind is invalid")
    status = _enum(value.get("status"), "status", _BUNDLE_STATUSES)
    normalized_request = _mapping(value.get("normalized_request"), "normalized_request")
    _text(normalized_request.get("summary"), "normalized_request summary")
    triage = _mapping(value.get("triage"), "triage")
    _enum(triage.get("complexity"), "triage complexity", _COMPLEXITIES)
    _enum(triage.get("ambiguity"), "triage ambiguity", _AMBIGUITIES)
    _enum(triage.get("risk"), "triage risk", _RISKS)
    if "evidence_depth" in triage:
        _enum(triage.get("evidence_depth"), "triage evidence_depth", _EVIDENCE_DEPTHS)
    evidence = _validate_evidence_items(value.get("evidence", []), "evidence", allow_empty=True)
    evidence_ids = {str(item["id"]) for item in evidence}
    entries = _object_list(value.get("entries", []), "entries")
    entry_ids: set[str] = set()
    for entry in entries:
        entry_id = _text(entry.get("id"), "entry id")
        if entry_id in entry_ids:
            raise _validation_error("entry IDs must be unique")
        entry_ids.add(entry_id)
        _enum(entry.get("classification"), "entry classification", _ENTRY_CLASSIFICATIONS)
        _text(entry.get("title"), "entry title")
        _text(entry.get("problem"), "entry problem")
        for evidence_ref in _text_list(entry.get("evidence_refs", []), "entry evidence_refs"):
            if evidence_ids and evidence_ref not in evidence_ids:
                raise _validation_error("entry evidence_refs must reference evidence IDs")
        _text_list(entry.get("constraints", []), "entry constraints")
        _text_list(entry.get("unknowns", []), "entry unknowns")
    clarification_questions = _optional_text_list(value.get("clarification_questions"), "clarification_questions")
    operational_blockers = _optional_text_list(value.get("operational_blockers"), "operational_blockers")
    if status == "ready_for_purpose" and not entries:
        raise _validation_error("ready_for_purpose requires at least one entry")
    if status == "needs_clarification":
        if not clarification_questions:
            raise _validation_error("needs_clarification requires clarification_questions")
        if entries:
            raise _validation_error("needs_clarification must not include classified entries")
    if status == "problem_gathering_info" and not operational_blockers:
        raise _validation_error("problem_gathering_info requires operational_blockers")
    return value


def validate_explore_review(candidate: str) -> str:
    return validate_review(candidate)
