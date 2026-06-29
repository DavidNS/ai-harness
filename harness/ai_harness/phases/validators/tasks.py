"""Tasks phase validator."""

from __future__ import annotations

import json
import re

from ..errors import PhaseValidationError


def _command(value: object, field: str) -> None:
    if not isinstance(value, list) or not value:
        raise PhaseValidationError(f"{field} must be a nonempty argument vector")
    if any(not isinstance(argument, str) or not argument for argument in value):
        raise PhaseValidationError(f"{field} contains an invalid argument")


def validate_tasks(candidate: str) -> dict[str, object]:
    try:
        data = json.loads(candidate)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PhaseValidationError("tasks output must be valid JSON") from exc
    allowed_document_fields = {"schema_version", "phase", "tasks", "deferrals"}
    required_document_fields = {"schema_version", "phase", "tasks"}
    if not isinstance(data, dict) or not required_document_fields <= set(data) or not set(data) <= allowed_document_fields:
        raise PhaseValidationError("tasks document has invalid fields")
    if data["schema_version"] != 1 or data["phase"] != "tasks":
        raise PhaseValidationError("tasks document version or phase is invalid")
    tasks = data["tasks"]
    if not isinstance(tasks, list) or not tasks:
        raise PhaseValidationError("tasks must be a nonempty list")
    required = {
        "id", "title", "depends_on", "acceptance_criteria", "touched_paths",
        "focused_tests", "broader_tests", "status",
    }
    allowed_task_fields = required | {"source_artifacts"}
    ids: list[str] = []
    for task in tasks:
        if not isinstance(task, dict) or not required <= set(task) or not set(task) <= allowed_task_fields:
            raise PhaseValidationError("task has invalid fields")
        task_id = task["id"]
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", task_id):
            raise PhaseValidationError("task ID is invalid")
        if task_id in ids:
            raise PhaseValidationError("task IDs must be unique")
        ids.append(task_id)
        if not isinstance(task["title"], str) or not task["title"].strip():
            raise PhaseValidationError("task title is required")
        for field in ("depends_on", "acceptance_criteria", "touched_paths"):
            value = task[field]
            if not isinstance(value, list) or (field != "depends_on" and not value):
                raise PhaseValidationError(f"{field} must be a valid list")
            if any(not isinstance(item, str) or not item for item in value):
                raise PhaseValidationError(f"{field} contains an invalid value")
        if "source_artifacts" in task:
            value = task["source_artifacts"]
            if not isinstance(value, list) or not value:
                raise PhaseValidationError("source_artifacts must be a nonempty list")
            if any(not isinstance(item, str) or not item for item in value) or len(value) != len(set(value)):
                raise PhaseValidationError("source_artifacts contains an invalid value")
        if task["status"] != "pending":
            raise PhaseValidationError("new tasks must be pending")
        for field in ("focused_tests", "broader_tests"):
            if not isinstance(task[field], list):
                raise PhaseValidationError(f"{field} must be a list")
            for command in task[field]:
                _command(command, field)
        if not task["focused_tests"]:
            raise PhaseValidationError("each task requires a focused test command")
    deferrals = data.get("deferrals", [])
    if not isinstance(deferrals, list):
        raise PhaseValidationError("deferrals must be a list")
    deferred_sources: list[str] = []
    for deferral in deferrals:
        if not isinstance(deferral, dict) or set(deferral) != {"source_artifact", "reason"}:
            raise PhaseValidationError("deferral has invalid fields")
        source = deferral["source_artifact"]
        reason = deferral["reason"]
        if not isinstance(source, str) or not source or not isinstance(reason, str) or not reason.strip():
            raise PhaseValidationError("deferral source_artifact and reason are required")
        if source in deferred_sources:
            raise PhaseValidationError("deferral sources must be unique")
        deferred_sources.append(source)
    known: set[str] = set()
    all_ids = set(ids)
    for task in tasks:
        dependencies = task["depends_on"]
        if len(dependencies) != len(set(dependencies)) or not set(dependencies) <= all_ids:
            raise PhaseValidationError("task dependency is duplicate or unknown")
        if not set(dependencies) <= known:
            raise PhaseValidationError("tasks must be dependency ordered and acyclic")
        known.add(task["id"])
    return data
