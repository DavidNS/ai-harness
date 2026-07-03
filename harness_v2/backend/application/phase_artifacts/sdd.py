"""SDD phase artifact builders and validators."""

from __future__ import annotations

from typing import Any

from harness_v2.backend.application.json_schema import validate_json_schema
from harness_v2.backend.application.phase_artifacts.reference_validation import ReferenceValidator


def validate_purpose_bundle(value: dict[str, Any]) -> None:
    validate_json_schema(value, "purpose_bundle")


def validate_spec_document(value: dict[str, Any]) -> None:
    validate_json_schema(value, "spec_document")


def validate_design_document(value: dict[str, Any]) -> None:
    validate_json_schema(value, "design_document")


def validate_tasks_document(value: dict[str, Any]) -> None:
    validate_json_schema(value, "tasks_document")
    ReferenceValidator.validate_unique_field(value["tasks"], "id", "task")
    ReferenceValidator.validate_ordered_refs(value["tasks"], "id", "depends_on", "task")


def validate_spec_against_purpose_and_explore(value: dict[str, Any], purpose: dict[str, Any], explore_bundle: dict[str, Any]) -> None:
    validate_spec_document(value)
    selected_entries = _selected_explore_entries(purpose, explore_bundle)
    _require_continuing_implementation(purpose, selected_entries, "spec")
    _require_selected_targets_preserved(value, selected_entries, "spec")


def validate_design_against_purpose_and_explore(value: dict[str, Any], purpose: dict[str, Any], explore_bundle: dict[str, Any]) -> None:
    validate_design_document(value)
    selected_entries = _selected_explore_entries(purpose, explore_bundle)
    _require_continuing_implementation(purpose, selected_entries, "design")
    _require_selected_targets_preserved(value, selected_entries, "design")


def validate_tasks_against_purpose_and_explore(value: dict[str, Any], purpose: dict[str, Any], explore_bundle: dict[str, Any]) -> None:
    validate_tasks_document(value)
    selected_entries = _selected_explore_entries(purpose, explore_bundle)
    _require_continuing_implementation(purpose, selected_entries, "tasks")
    _require_selected_targets_preserved(value, selected_entries, "tasks")


_IMPLEMENTABLE_MODES = {
    "direct_patch",
    "patch_with_local_refactor",
    "refactor_first_then_patch",
    "security_patch",
    "documentation_only",
}
def validate_purpose_against_explore(value: dict[str, Any], explore_bundle: dict[str, Any]) -> None:
    validate_purpose_bundle(value)
    entries = _entries_by_id(explore_bundle.get("entries"))
    selected = _strings(value.get("selected_entries"))
    if not selected:
        raise ValueError("purpose selected_entries must select at least one explore entry")
    unknown = [entry_id for entry_id in selected if entry_id not in entries]
    if unknown:
        raise ValueError("purpose selected_entries reference unknown explore entries: " + ", ".join(unknown))
    selected_entries = [entries[entry_id] for entry_id in selected]
    actions = {_text(entry.get("action")) for entry in selected_entries}
    mode = _text(value.get("implementation_mode"))
    outcome = _text(value.get("outcome"))
    if "create" in actions:
        _require_mode(mode, _IMPLEMENTABLE_MODES, "create")
        if outcome == "reject":
            raise ValueError("purpose must not reject selected create entries")
    if "update_existing" in actions:
        _require_mode(mode, {"update_existing"}, "update_existing")
        _require_targets_mentioned(value, selected_entries, "update_existing")
    if "existing_functionality" in actions:
        _require_mode(mode, {"existing_functionality"}, "existing_functionality")
        if outcome not in {"alternative", "reject"}:
            raise ValueError("existing_functionality entries require purpose outcome alternative or reject")
        _reject_new_acceptance(value, "existing_functionality")
    if actions & {"duplicate_noop", "reject"}:
        _require_reject(value, "duplicate_noop/reject")
    if "ask_user" in actions:
        if outcome != "clarify":
            raise ValueError("ask_user entries require purpose outcome clarify")
        if not _text(value.get("question")) or not _strings(value.get("options")):
            raise ValueError("ask_user entries require purpose question and options")
    if "blocked" in actions:
        _require_reject(value, "blocked")


def _entries_by_id(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        entry_id = _text(item.get("id"))
        if entry_id:
            entries[entry_id] = item
    return entries


def _require_mode(mode: str, allowed: set[str], action: str) -> None:
    if mode not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(f"{action} entries require purpose implementation_mode {allowed_text}")


def _require_targets_mentioned(value: dict[str, Any], entries: list[dict[str, Any]], action: str) -> None:
    haystack = "\n".join(_text(value.get(field)) for field in ("scope", "approach", "summary", "problem"))
    for entry in entries:
        if _text(entry.get("action")) != action:
            continue
        target = entry.get("target")
        if not isinstance(target, dict):
            raise ValueError(f"{action} explore entry requires target")
        path = _text(target.get("path"))
        if path and path in haystack:
            continue
        raise ValueError(f"{action} purpose must mention target path {path} in scope or approach")


def _require_reject(value: dict[str, Any], action: str) -> None:
    if _text(value.get("outcome")) != "reject":
        raise ValueError(f"{action} entries require purpose outcome reject")
    if not _text(value.get("rejection_reason")):
        raise ValueError(f"{action} entries require purpose rejection_reason")
    _reject_new_acceptance(value, action)


def _reject_new_acceptance(value: dict[str, Any], action: str) -> None:
    if _strings(value.get("acceptance_outline")):
        raise ValueError(f"{action} purpose must not define new implementation acceptance_outline")


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _selected_explore_entries(purpose: dict[str, Any], explore_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    entries = _entries_by_id(explore_bundle.get("entries"))
    selected = _strings(purpose.get("selected_entries"))
    if not selected:
        raise ValueError("purpose selected_entries must select at least one explore entry")
    unknown = [entry_id for entry_id in selected if entry_id not in entries]
    if unknown:
        raise ValueError("purpose selected_entries reference unknown explore entries: " + ", ".join(unknown))
    return [entries[entry_id] for entry_id in selected]


def _require_continuing_implementation(purpose: dict[str, Any], entries: list[dict[str, Any]], artifact: str) -> None:
    outcome = _text(purpose.get("outcome"))
    mode = _text(purpose.get("implementation_mode"))
    actions = {_text(entry.get("action")) for entry in entries}
    if outcome in {"reject", "clarify"}:
        raise ValueError(f"{artifact} must not continue after purpose outcome {outcome}")
    if mode == "existing_functionality" or actions <= {"existing_functionality", "duplicate_noop", "reject", "ask_user", "blocked"}:
        raise ValueError(f"{artifact} must not define new implementation work for non-implementation explore outcome")


def _require_selected_targets_preserved(value: dict[str, Any], entries: list[dict[str, Any]], artifact: str) -> None:
    haystack = _all_text(value)
    for entry in entries:
        action = _text(entry.get("action"))
        if action != "update_existing":
            continue
        target = entry.get("target")
        if not isinstance(target, dict):
            raise ValueError("update_existing explore entry requires target")
        path = _text(target.get("path"))
        if path and path in haystack:
            continue
        raise ValueError(f"{artifact} must preserve update_existing target path {path}")


def _all_text(value: object) -> str:
    parts: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list | tuple):
            for child in item:
                visit(child)

    visit(value)
    return "\n".join(parts)
