"""Deny-by-default worker capability manifests and enforcement helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


class CapabilityError(ValueError):
    """Raised when a manifest or requested capability fails closed."""


_MANIFEST_KEYS = {
    "schema_version",
    "phase",
    "paths",
    "commands",
    "skills",
    "mcp_tools",
    "required_evidence",
    "postconditions",
    "limits",
}
_PATH_KEYS = {"pattern", "mode"}
_COMMAND_KEYS = {"argv", "run_by"}
_TOOL_KEYS = {"server", "name", "access", "arguments"}
_LIMIT_KEYS = {"timeout_seconds", "output_bytes", "retries"}


def _exact_keys(value: Mapping[str, Any], expected: set[str], context: str) -> None:
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown or missing:
        raise CapabilityError(
            f"invalid {context} fields: missing={sorted(missing)}, unknown={sorted(unknown)}"
        )


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise CapabilityError(f"{field} must be a list of nonempty strings")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class PathCapability:
    pattern: str
    mode: str


@dataclass(frozen=True, slots=True)
class CommandCapability:
    argv: tuple[str, ...]
    run_by: str


@dataclass(frozen=True, slots=True)
class ToolCapability:
    server: str
    name: str
    access: str
    arguments: tuple[str, ...]

    @property
    def identifier(self) -> str:
        return f"{self.server}.{self.name}"


@dataclass(frozen=True, slots=True)
class CapabilityLimits:
    timeout_seconds: int
    output_bytes: int
    retries: int


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    schema_version: int
    phase: str
    paths: tuple[PathCapability, ...]
    commands: tuple[CommandCapability, ...]
    skills: tuple[str, ...]
    mcp_tools: tuple[ToolCapability, ...]
    required_evidence: tuple[str, ...]
    postconditions: tuple[str, ...]
    limits: CapabilityLimits

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CapabilityManifest":
        if not isinstance(data, Mapping):
            raise CapabilityError("capability manifest must be an object")
        _exact_keys(data, _MANIFEST_KEYS, "manifest")
        if data["schema_version"] != 1:
            raise CapabilityError("unsupported capability schema version")
        phase = data["phase"]
        if not isinstance(phase, str) or not phase:
            raise CapabilityError("phase must be a nonempty string")

        raw_paths = data["paths"]
        if not isinstance(raw_paths, list):
            raise CapabilityError("paths must be a list")
        paths: list[PathCapability] = []
        for item in raw_paths:
            if not isinstance(item, Mapping):
                raise CapabilityError("path capability must be an object")
            _exact_keys(item, _PATH_KEYS, "path capability")
            pattern, mode = item["pattern"], item["mode"]
            if not isinstance(pattern, str) or not _safe_pattern(pattern):
                raise CapabilityError("path pattern must be safe and repository-relative")
            if mode not in {"read", "write"}:
                raise CapabilityError("path mode must be read or write")
            paths.append(PathCapability(pattern, mode))

        raw_commands = data["commands"]
        if not isinstance(raw_commands, list):
            raise CapabilityError("commands must be a list")
        commands: list[CommandCapability] = []
        for item in raw_commands:
            if not isinstance(item, Mapping):
                raise CapabilityError("command capability must be an object")
            _exact_keys(item, _COMMAND_KEYS, "command capability")
            argv = _string_list(item["argv"], "command argv")
            if item["run_by"] not in {"controller", "worker"}:
                raise CapabilityError("command run_by must be controller or worker")
            commands.append(CommandCapability(argv, item["run_by"]))

        raw_tools = data["mcp_tools"]
        if not isinstance(raw_tools, list):
            raise CapabilityError("mcp_tools must be a list")
        tools: list[ToolCapability] = []
        for item in raw_tools:
            if not isinstance(item, Mapping):
                raise CapabilityError("MCP tool capability must be an object")
            _exact_keys(item, _TOOL_KEYS, "MCP tool capability")
            if item["access"] not in {"read", "mutate"}:
                raise CapabilityError("MCP access must be read or mutate")
            if not isinstance(item["server"], str) or not item["server"]:
                raise CapabilityError("MCP server must be a nonempty string")
            if not isinstance(item["name"], str) or not item["name"]:
                raise CapabilityError("MCP tool name must be a nonempty string")
            arguments = _string_list(item["arguments"], "MCP arguments")
            if len(arguments) != len(set(arguments)):
                raise CapabilityError("MCP argument names must be unique")
            tools.append(ToolCapability(item["server"], item["name"], item["access"], arguments))

        limits = data["limits"]
        if not isinstance(limits, Mapping):
            raise CapabilityError("limits must be an object")
        _exact_keys(limits, _LIMIT_KEYS, "limits")
        for key in _LIMIT_KEYS:
            if not isinstance(limits[key], int) or isinstance(limits[key], bool):
                raise CapabilityError(f"{key} must be an integer")
        if limits["timeout_seconds"] <= 0 or limits["output_bytes"] <= 0:
            raise CapabilityError("timeout and output limits must be positive")
        if not 0 <= limits["retries"] <= 3:
            raise CapabilityError("retries must be between zero and three")

        return cls(
            1,
            phase,
            tuple(paths),
            tuple(commands),
            _string_list(data["skills"], "skills"),
            tuple(tools),
            _string_list(data["required_evidence"], "required_evidence"),
            _string_list(data["postconditions"], "postconditions"),
            CapabilityLimits(limits["timeout_seconds"], limits["output_bytes"], limits["retries"]),
        )


def _safe_pattern(pattern: str) -> bool:
    path = PurePosixPath(pattern)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in pattern


def load_manifest(path: Path) -> CapabilityManifest:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityError(f"cannot load capability manifest: {exc}") from exc
    return CapabilityManifest.from_mapping(data)


class CapabilityPolicy:
    """Validate requested worker operations against one immutable manifest."""

    def __init__(self, manifest: CapabilityManifest, repository: Path):
        self.manifest = manifest
        self.repository = Path(repository).resolve()

    def reject_escalation(self, requested: object) -> None:
        if requested:
            raise CapabilityError("workers cannot request permission escalation")

    def authorize_path(self, path: Path | str, mode: str) -> Path:
        if mode not in {"read", "write"}:
            raise CapabilityError("path mode must be read or write")
        candidate = Path(path)
        resolved = candidate.resolve() if candidate.is_absolute() else (self.repository / candidate).resolve()
        try:
            relative = resolved.relative_to(self.repository).as_posix()
        except ValueError as exc:
            raise CapabilityError("path escapes the target repository") from exc
        for capability in self.manifest.paths:
            permits_mode = capability.mode == "write" or mode == "read"
            if permits_mode and fnmatchcase(relative, capability.pattern):
                return resolved
        raise CapabilityError(f"undeclared {mode} path: {relative}")

    def authorize_command(self, argv: Sequence[str], run_by: str) -> None:
        requested = tuple(argv)
        if not requested or any(not isinstance(arg, str) or not arg for arg in requested):
            raise CapabilityError("command must be a nonempty argument vector")
        if not any(item.argv == requested and item.run_by == run_by for item in self.manifest.commands):
            raise CapabilityError("undeclared command")

    def authorize_tool(self, server: str, name: str, access: str, arguments: Mapping[str, object]) -> ToolCapability:
        for tool in self.manifest.mcp_tools:
            if (tool.server, tool.name, tool.access) == (server, name, access):
                if set(arguments) != set(tool.arguments):
                    raise CapabilityError("tool arguments do not match the declaration")
                return tool
        raise CapabilityError("undeclared MCP tool")

    def worker_permissions(self) -> dict[str, object]:
        """Project only worker-executable capabilities; mutations remain controller-only."""
        return {
            "paths": [
                {"pattern": item.pattern, "mode": item.mode}
                for item in self.manifest.paths
            ],
            "commands": [
                list(item.argv) for item in self.manifest.commands if item.run_by == "worker"
            ],
            "skills": list(self.manifest.skills),
            "mcp_tools": [
                {"server": item.server, "name": item.name, "access": "read"}
                for item in self.manifest.mcp_tools if item.access == "read"
            ],
            "timeout_seconds": self.manifest.limits.timeout_seconds,
            "output_bytes": self.manifest.limits.output_bytes,
        }

    def validate_evidence(self, evidence: Mapping[str, object]) -> None:
        missing = set(self.manifest.required_evidence) - set(evidence)
        if missing:
            raise CapabilityError(f"missing required evidence: {sorted(missing)}")

