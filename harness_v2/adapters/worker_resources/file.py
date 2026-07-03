"""File-backed worker prompt resources for v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness_v2.backend.ports.model_provider import (
    CapabilityProjection,
    McpToolCapability,
    OutputSchema,
    PathCapability,
)
from harness_v2.backend.ports.worker_resources import (
    WorkerResourceNotFoundError,
    WorkerResourceSpec,
    WorkerResourceValidationError,
    require_task_id,
)


def default_resource_root() -> Path:
    return Path(__file__).resolve().parents[2]


class FileWorkerResourceStore:
    """Loads workers, prompts, and capability manifests from package resources."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root) if root is not None else default_resource_root()

    def get(self, task_id: str) -> WorkerResourceSpec:
        normalized = require_task_id(task_id)
        worker = self._read_text("workers", normalized, ".md")
        prompt = self._read_text("prompts", normalized, ".md")
        manifest = self._read_json("capabilities", normalized, ".json")
        return WorkerResourceSpec(
            task_id=normalized,
            playbook_markdown=worker,
            prompt_markdown=prompt,
            capabilities=_capabilities_from_manifest(normalized, manifest),
            output_schema=self._output_schema_from_manifest(manifest),
        )

    def _read_text(self, folder: str, task_id: str, suffix: str) -> str:
        path = self._root / folder / f"{task_id}{suffix}"
        try:
            value = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise WorkerResourceNotFoundError(str(path)) from exc
        if not value.strip():
            raise WorkerResourceValidationError(f"{path} must be nonempty")
        return value

    def _read_json(self, folder: str, task_id: str, suffix: str) -> dict[str, Any]:
        path = self._root / folder / f"{task_id}{suffix}"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise WorkerResourceNotFoundError(str(path)) from exc
        except json.JSONDecodeError as exc:
            raise WorkerResourceValidationError(f"{path} must be valid JSON") from exc
        if not isinstance(value, dict):
            raise WorkerResourceValidationError(f"{path} must contain a JSON object")
        return value

    def _output_schema_from_manifest(self, manifest: dict[str, Any]) -> OutputSchema | None:
        name = manifest.get("output_schema")
        if name is None:
            return None
        schema_name = require_task_id(_text(name, "output_schema"))
        path = self._root / "backend" / "application" / "json_schemas" / f"{schema_name}.schema.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise WorkerResourceNotFoundError(str(path)) from exc
        except json.JSONDecodeError as exc:
            raise WorkerResourceValidationError(f"{path} must be valid JSON") from exc
        if not isinstance(value, dict) or not value:
            raise WorkerResourceValidationError(f"{path} must contain a nonempty JSON object")
        return OutputSchema(schema_name, value)


def _capabilities_from_manifest(task_id: str, value: dict[str, Any]) -> CapabilityProjection:
    if value.get("schema_version") != 1:
        raise WorkerResourceValidationError("capability manifest schema_version must be 1")
    if value.get("phase") != task_id:
        raise WorkerResourceValidationError("capability manifest phase must match task_id")
    paths = tuple(_path_capability(item) for item in _object_list(value.get("paths", []), "paths"))
    commands = tuple(tuple(_text(arg, "command argument") for arg in item) for item in _list(value.get("commands", []), "commands"))
    if any(not command for command in commands):
        raise WorkerResourceValidationError("commands must not contain empty commands")
    skills = tuple(_text(item, "skills") for item in _list(value.get("skills", []), "skills"))
    mcp_tools = tuple(_mcp_tool(item) for item in _object_list(value.get("mcp_tools", []), "mcp_tools"))
    return CapabilityProjection(paths=paths, commands=commands, skills=skills, mcp_tools=mcp_tools)


def _path_capability(value: dict[str, Any]) -> PathCapability:
    return PathCapability(_text(value.get("pattern"), "path pattern"), _text(value.get("mode"), "path mode"))


def _mcp_tool(value: dict[str, Any]) -> McpToolCapability:
    return McpToolCapability(
        _text(value.get("server"), "mcp server"),
        _text(value.get("name"), "mcp tool name"),
        _text(value.get("access"), "mcp tool access"),
    )


def _object_list(value: object, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise WorkerResourceValidationError(f"{field} must be a list of objects")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise WorkerResourceValidationError(f"{field} must be a list")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerResourceValidationError(f"{field} must be a nonempty string")
    return value.strip()
