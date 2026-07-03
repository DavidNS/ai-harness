"""Explore phase artifact contracts and validators."""

from __future__ import annotations

from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.json_schema import validate_json_schema
from harness_v2.backend.application.phase_artifacts.reference_validation import ReferenceValidator
from harness_v2.backend.domain.lifecycle import BundleName

EXPLORE_BUNDLE = BundleName.EXPLORE_BUNDLE
REQUEST_PROFILE_TASK = "explore_request_profile"
EVIDENCE_DIGEST_TASK = "explore_evidence_digest"
OUTCOME_SYNTHESIS_TASK = "explore_outcome_synthesis"
REQUEST_PROFILE_ARTIFACT = "explore/request_profile.json"
CONTEXT_PACK_ARTIFACT = "explore/context_pack.json"
EVIDENCE_DIGEST_ARTIFACT = "explore/evidence_digest.json"
EXPLORATION_MAP_ARTIFACT = "explore/exploration_map.json"
OUTCOME_SYNTHESIS_ARTIFACT = "explore/outcome_synthesis.json"
OUTCOME_BUNDLE_ARTIFACT = "explore/outcome_bundle.json"
MANIFEST_ARTIFACT = "explore/manifest.json"
HANDOFF_ARTIFACT = "published/explore-handoff.json"
CLARIFICATION_DECISION_ID = "EXPLORE_BUNDLE-clarification"


def validate_request_profile(value: dict[str, Any]) -> None:
    validate_json_schema(value, "request_profile")


def validate_context_pack(value: dict[str, Any]) -> None:
    validate_json_schema(value, "context_pack")


def validate_evidence_digest(value: dict[str, Any]) -> None:
    validate_json_schema(value, "evidence_digest")
    validate_unique_evidence_ids(value)


def validate_exploration_map(value: dict[str, Any], evidence_ids: set[str]) -> None:
    validate_json_schema(value, "exploration_map")
    validate_exploration_map_refs(value, evidence_ids)


def validate_outcome_synthesis(value: dict[str, Any]) -> None:
    validate_json_schema(value, "outcome_synthesis")


def validate_outcome_bundle(value: dict[str, Any]) -> None:
    validate_json_schema(value, "outcome_bundle")
    validate_unique_evidence_ids(value)
    ids = evidence_ids(value)
    validate_exploration_map(value["exploration_map"], ids)
    validate_entry_refs(value, ids)
    validate_outcome_entries(value)


def validate_handoff(value: dict[str, Any]) -> None:
    validate_json_schema(value, "explore_handoff")


def validate_manifest(value: dict[str, Any]) -> None:
    validate_json_schema(value, "explore_manifest")


def evidence_ids(value: dict[str, Any]) -> set[str]:
    return ReferenceValidator.ids_by_field(value["evidence"], "id")


_EXPLORATION_MAP_REF_SECTIONS = {
    "surfaces": ("evidence_refs",),
    "behaviors": ("evidence_refs",),
    "constraints": ("evidence_refs",),
    "risks": ("evidence_refs",),
    "unknowns": ("evidence_refs",),
    "candidate_work_shapes": ("supporting_evidence_refs", "counterevidence_refs"),
    "verification_surfaces": ("evidence_refs",),
}


def validate_unique_evidence_ids(value: dict[str, Any]) -> None:
    ReferenceValidator.validate_unique_field(value["evidence"], "id", "evidence")


def validate_exploration_map_refs(value: dict[str, Any], ids: set[str]) -> None:
    validator = ReferenceValidator(ids, label="evidence refs")
    for section, fields in _EXPLORATION_MAP_REF_SECTIONS.items():
        validator.validate_refs_in_items(value[section], fields)


def validate_entry_refs(value: dict[str, Any], ids: set[str]) -> None:
    ReferenceValidator(ids, label="evidence refs").validate_refs_in_items(value["entries"], ("evidence_refs",))


_IMPLEMENTABLE_ACTIONS = {"create", "update_existing"}
_ACTION_CLASSIFICATIONS = {
    "create": {"improvement"},
    "update_existing": {"improvement"},
    "duplicate_noop": {"not_worth_it", "improvement"},
    "existing_functionality": {"not_worth_it", "improvement"},
    "document_limitation": {"limitation"},
    "reject": {"not_worth_it", "limitation"},
    "ask_user": {"decision_needed"},
    "blocked": {"blocked"},
}


def validate_outcome_entries(value: dict[str, Any]) -> None:
    exploration_map = value["exploration_map"]
    existing_paths = _paths(exploration_map.get("existing_functionality"))
    similar_targets = _targets(exploration_map.get("similar_functionality"), require_checksum=True)
    duplicate_paths = _duplicate_match_paths(exploration_map.get("duplicate_search"))
    strong_existing = bool(existing_paths)
    strong_duplicate = bool(duplicate_paths)
    for entry in value["entries"]:
        action = _text(entry.get("action"), "entry action")
        classification = _text(entry.get("classification"), "entry classification")
        allowed = _ACTION_CLASSIFICATIONS.get(action)
        if allowed is None:
            raise BundleValidationError(f"unsupported outcome action: {action}")
        if classification not in allowed:
            raise BundleValidationError(f"outcome action {action} is incompatible with classification {classification}")
        if action in _IMPLEMENTABLE_ACTIONS:
            _require_substantive_text(entry.get("behavioral_delta"), f"{action} behavioral_delta", entry)
            verification = _require_substantive_text(entry.get("minimum_verification"), f"{action} minimum_verification", entry)
            if not _looks_verifiable(verification):
                raise BundleValidationError(f"{action} minimum_verification must describe an observable verification step")
        if action == "update_existing":
            target = _target(entry, action)
            if (target["path"], target.get("checksum", "")) not in similar_targets:
                raise BundleValidationError("update_existing target must match similar_functionality path and checksum")
        if action == "duplicate_noop":
            target = _target(entry, action)
            if target["path"] not in duplicate_paths:
                raise BundleValidationError("duplicate_noop target must match duplicate_search matches")
        if action == "existing_functionality":
            target = _target(entry, action)
            if target["path"] not in existing_paths:
                raise BundleValidationError("existing_functionality target must match exploration_map existing_functionality")
        if action == "create" and (strong_existing or strong_duplicate):
            if not _object_items(entry.get("rejected_alternatives")) or not _strings(entry.get("counterevidence")):
                raise BundleValidationError("create entries require rejected_alternatives and counterevidence when duplicate or existing functionality signals are present")
            for alternative in _object_items(entry.get("rejected_alternatives")):
                _require_substantive_text(alternative.get("reason"), "rejected_alternatives reason", entry)
            for counterevidence in _strings(entry.get("counterevidence")):
                _require_substantive_text(counterevidence, "counterevidence", entry)
        if action == "ask_user":
            _require_text(entry.get("question"), "ask_user question")
            if not _strings(entry.get("options")):
                raise BundleValidationError("ask_user entries require options")


def _target(entry: dict[str, Any], action: str) -> dict[str, str]:
    raw = entry.get("target")
    if not isinstance(raw, dict):
        raise BundleValidationError(f"{action} entries require target")
    path = _require_text(raw.get("path"), f"{action} target path")
    target = {"path": path}
    checksum = _text(raw.get("checksum"), f"{action} target checksum")
    if checksum:
        target["checksum"] = checksum
    elif action == "update_existing":
        raise BundleValidationError("update_existing target requires checksum")
    return target


def _targets(value: object, *, require_checksum: bool) -> set[tuple[str, str]]:
    targets: set[tuple[str, str]] = set()
    for item in _object_items(value):
        path = _text(item.get("path"), "target path")
        checksum = _text(item.get("checksum"), "target checksum")
        if path and (checksum or not require_checksum):
            targets.add((path, checksum))
    return targets


def _duplicate_match_paths(value: object) -> set[str]:
    if not isinstance(value, dict):
        return set()
    return _paths(value.get("matches"))


def _paths(value: object) -> set[str]:
    return {path for path in (_text(item.get("path"), "path") for item in _object_items(value)) if path}


def _object_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _require_text(value: object, field: str) -> str:
    text = _text(value, field)
    if not text:
        raise BundleValidationError(f"{field} must be a nonempty string")
    return text


def _require_substantive_text(value: object, field: str, entry: dict[str, Any]) -> str:
    text = _require_text(value, field)
    title = _text(entry.get("title"), "entry title").casefold()
    normalized = text.casefold()
    if len(normalized) < 16:
        raise BundleValidationError(f"{field} must be substantive")
    if title and normalized in {title, f"{title}."}:
        raise BundleValidationError(f"{field} must add detail beyond the entry title")
    return text


def _looks_verifiable(value: str) -> bool:
    lowered = value.casefold()
    return any(term in lowered for term in ("assert", "check", "inspect", "review", "run", "test", "verify", "validate", "coverage", "baseline", "ci"))


def _text(value: object, _field: str) -> str:
    return value.strip() if isinstance(value, str) else ""
