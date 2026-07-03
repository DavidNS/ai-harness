"""Safe JSON artifact delta application."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError


def apply_json_artifact_delta(delta: dict[str, Any], *, target_artifact: str, current_artifact: dict[str, Any] | None) -> dict[str, Any]:
    if delta.get("schema_version") != 1:
        raise BundleValidationError("artifact delta schema_version must be 1")
    if delta.get("kind") != "json_artifact_delta":
        raise BundleValidationError("artifact delta kind must be json_artifact_delta")
    if delta.get("target_artifact") != target_artifact:
        raise BundleValidationError("artifact delta target_artifact does not match requested artifact")
    operations = delta.get("operations")
    if not isinstance(operations, list) or not operations:
        raise BundleValidationError("artifact delta operations must be a nonempty list")

    document: Any = deepcopy(current_artifact)
    for operation in operations:
        if not isinstance(operation, dict):
            raise BundleValidationError("artifact delta operations must be objects")
        op = operation.get("op")
        path = operation.get("path")
        if op not in {"add", "replace", "remove"}:
            raise BundleValidationError("artifact delta operation is unsupported")
        if not isinstance(path, str):
            raise BundleValidationError("artifact delta operation path must be a JSON Pointer string")
        if op in {"add", "replace"} and "value" not in operation:
            raise BundleValidationError("artifact delta add/replace operation requires value")
        document = _apply_operation(document, op, path, deepcopy(operation.get("value")))

    if not isinstance(document, dict):
        raise BundleValidationError("artifact delta must produce a JSON object")
    return document


def _apply_operation(document: Any, op: str, path: str, value: Any) -> Any:
    parts = _pointer_parts(path)
    if not parts:
        if op == "remove":
            raise BundleValidationError("artifact delta cannot remove the document root")
        return value
    parent, key = _resolve_parent(document, parts)
    if isinstance(parent, dict):
        if op == "add":
            parent[key] = value
            return document
        if key not in parent:
            raise BundleValidationError("artifact delta path does not exist")
        if op == "replace":
            parent[key] = value
        else:
            del parent[key]
        return document
    if isinstance(parent, list):
        index = _list_index(key, parent, allow_end=op == "add")
        if op == "add":
            parent.insert(index, value)
        elif op == "replace":
            parent[index] = value
        else:
            del parent[index]
        return document
    raise BundleValidationError("artifact delta parent path is not a container")


def _resolve_parent(document: Any, parts: tuple[str, ...]) -> tuple[Any, str]:
    if document is None:
        raise BundleValidationError("artifact delta cannot address nested paths without a current artifact")
    current = document
    for part in parts[:-1]:
        if isinstance(current, dict):
            if part not in current:
                raise BundleValidationError("artifact delta parent path does not exist")
            current = current[part]
        elif isinstance(current, list):
            current = current[_list_index(part, current, allow_end=False)]
        else:
            raise BundleValidationError("artifact delta parent path is not a container")
    return current, parts[-1]


def _pointer_parts(path: str) -> tuple[str, ...]:
    if path == "":
        return ()
    if not path.startswith("/"):
        raise BundleValidationError("artifact delta path must be a valid JSON Pointer")
    return tuple(part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/"))


def _list_index(value: str, items: list[Any], *, allow_end: bool) -> int:
    if allow_end and value == "-":
        return len(items)
    try:
        index = int(value)
    except ValueError as exc:
        raise BundleValidationError("artifact delta list path segment must be an integer") from exc
    upper = len(items) if allow_end else len(items) - 1
    if index < 0 or index > upper:
        raise BundleValidationError("artifact delta list index is out of range")
    return index
