"""Model provider port for one bounded worker request."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ModelProviderError(RuntimeError):
    """Base error for model provider failures before a result is available."""


class CapabilityProjectionError(ModelProviderError, ValueError):
    """Raised when an adapter cannot enforce requested worker capabilities."""


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field)


def _text_tuple(values: tuple[str, ...] | list[str], field: str) -> tuple[str, ...]:
    normalized = tuple(_require_text(value, field) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class ModelSelection:
    provider: str
    model: str | None = None
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _require_text(self.provider, "provider"))
        object.__setattr__(self, "model", _optional_text(self.model, "model"))
        object.__setattr__(self, "reasoning_effort", _optional_text(self.reasoning_effort, "reasoning_effort"))


@dataclass(frozen=True, slots=True)
class PathCapability:
    pattern: str
    mode: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "pattern", _require_text(self.pattern, "path pattern"))
        mode = _require_text(self.mode, "path mode")
        if mode not in {"read", "write"}:
            raise ValueError("path mode must be read or write")
        object.__setattr__(self, "mode", mode)


@dataclass(frozen=True, slots=True)
class McpToolCapability:
    server: str
    name: str
    access: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "server", _require_text(self.server, "mcp server"))
        object.__setattr__(self, "name", _require_text(self.name, "mcp tool name"))
        access = _require_text(self.access, "mcp tool access")
        if access not in {"read", "write"}:
            raise ValueError("mcp tool access must be read or write")
        object.__setattr__(self, "access", access)


@dataclass(frozen=True, slots=True)
class CapabilityProjection:
    paths: tuple[PathCapability, ...] = ()
    commands: tuple[tuple[str, ...], ...] = ()
    skills: tuple[str, ...] = ()
    mcp_tools: tuple[McpToolCapability, ...] = ()

    def __post_init__(self) -> None:
        paths = tuple(self.paths)
        if any(not isinstance(path, PathCapability) for path in paths):
            raise TypeError("paths must contain PathCapability")
        commands = tuple(tuple(_require_text(arg, "command argument") for arg in command) for command in self.commands)
        if any(not command for command in commands):
            raise ValueError("commands must not contain empty commands")
        mcp_tools = tuple(self.mcp_tools)
        if any(not isinstance(tool, McpToolCapability) for tool in mcp_tools):
            raise TypeError("mcp_tools must contain McpToolCapability")
        object.__setattr__(self, "paths", paths)
        object.__setattr__(self, "commands", commands)
        object.__setattr__(self, "skills", _text_tuple(self.skills, "skills"))
        object.__setattr__(self, "mcp_tools", mcp_tools)


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    seconds: float | None = 120.0

    def __post_init__(self) -> None:
        if self.seconds is not None and (isinstance(self.seconds, bool) or self.seconds <= 0):
            raise ValueError("timeout seconds must be positive or None")


@dataclass(frozen=True, slots=True)
class TruncationPolicy:
    output_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        if isinstance(self.output_bytes, bool) or self.output_bytes <= 0:
            raise ValueError("output_bytes must be positive")


@dataclass(frozen=True, slots=True)
class ModelProviderRequest:
    prompt: str
    working_directory: Path
    model: ModelSelection
    capabilities: CapabilityProjection
    timeout: TimeoutPolicy = TimeoutPolicy()
    truncation: TruncationPolicy = TruncationPolicy()

    def __post_init__(self) -> None:
        object.__setattr__(self, "prompt", _require_text(self.prompt, "prompt"))
        object.__setattr__(self, "working_directory", Path(self.working_directory))
        if not isinstance(self.model, ModelSelection):
            raise TypeError("model must be ModelSelection")
        if not isinstance(self.capabilities, CapabilityProjection):
            raise TypeError("capabilities must be CapabilityProjection")
        if not isinstance(self.timeout, TimeoutPolicy):
            raise TypeError("timeout must be TimeoutPolicy")
        if not isinstance(self.truncation, TruncationPolicy):
            raise TypeError("truncation must be TruncationPolicy")


@dataclass(frozen=True, slots=True)
class ModelProviderResult:
    stdout: str
    stderr: str
    exit_code: int | None
    duration_seconds: float
    timed_out: bool = False
    truncated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.stdout, str):
            raise TypeError("stdout must be str")
        if not isinstance(self.stderr, str):
            raise TypeError("stderr must be str")
        if self.exit_code is not None and isinstance(self.exit_code, bool):
            raise TypeError("exit_code must be int or None")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative")

    @property
    def succeeded(self) -> bool:
        return not self.timed_out and self.exit_code == 0


class ModelProviderPort(Protocol):
    """Boundary for executing exactly one bounded model request."""

    def run(self, request: ModelProviderRequest) -> ModelProviderResult: ...
