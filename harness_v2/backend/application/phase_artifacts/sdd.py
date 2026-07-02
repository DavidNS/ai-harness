"""SDD phase artifact builders and validators."""

from __future__ import annotations

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.json_schema import validate_json_schema


def validate_purpose_bundle(value: dict[str, Any]) -> None:
    validate_json_schema(value, "purpose_bundle")


def validate_spec_document(value: dict[str, Any]) -> None:
    validate_json_schema(value, "spec_document")


def validate_design_document(value: dict[str, Any]) -> None:
    validate_json_schema(value, "design_document")


def validate_tasks_document(value: dict[str, Any]) -> None:
    validate_json_schema(value, "tasks_document")
    seen: set[str] = set()
    completed: set[str] = set()
    for task in value["tasks"]:
        task_id = task["id"].strip()
        if task_id in seen:
            raise BundleValidationError("task ids must be unique")
        seen.add(task_id)
        if any(dep not in completed for dep in task["depends_on"]):
            raise BundleValidationError("tasks must be dependency ordered")
        completed.add(task_id)
