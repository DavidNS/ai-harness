"""Subprocess-backed provider with bounded input, output, time, and environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ._cli_process import run_cli_process
from .base import ProviderProgress, ProviderResult
from .cli_projection import (
    DEFAULT_ENV_ALLOWLIST,
    CapabilityProjectionError,
    claude_config_arguments,
    codex_config_arguments,
    project_arguments,
    project_environment,
    provider_name,
)


@dataclass(frozen=True, slots=True)
class CliProvider:
    """Execute one configured CLI command without shell interpretation."""

    command: tuple[str, ...]
    timeout_seconds: float | None = 120.0
    output_limit: int = 1_000_000
    allowed_environment: frozenset[str] = field(
        default_factory=lambda: DEFAULT_ENV_ALLOWLIST
    )
    environment: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.command or any(not isinstance(arg, str) or not arg for arg in self.command):
            raise ValueError("provider command must contain nonempty arguments")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("provider timeout must be positive or None")
        if self.output_limit <= 0:
            raise ValueError("provider output limit must be positive")

    @classmethod
    def for_name(
        cls,
        name: str,
        *,
        timeout_seconds: float | None = 120.0,
        output_limit: int = 1_000_000,
        environment: Mapping[str, str] | None = None,
    ) -> "CliProvider":
        commands = {
            "claude": ("claude", "--print"),
            "codex": ("codex", "exec", "-"),
        }
        try:
            command = commands[name.lower()]
        except KeyError as exc:
            raise ValueError(f"unsupported provider: {name}") from exc
        return cls(command, timeout_seconds, output_limit, environment=environment)

    def _source_environment(self) -> Mapping[str, str]:
        return os.environ if self.environment is None else self.environment

    def _environment(self, temp_dir: Path | None = None) -> dict[str, str]:
        return project_environment(self._source_environment(), self.allowed_environment, temp_dir=temp_dir)

    def run_prompt(
        self,
        prompt: str,
        *,
        cwd: Path,
        permissions: Mapping[str, object] | None = None,
        progress: ProviderProgress | None = None,
        temp_dir: Path | None = None,
    ) -> ProviderResult:
        target = Path(cwd).resolve()
        if not target.is_dir():
            raise ValueError(f"provider cwd is not a directory: {target}")

        command = list(self.command)
        timeout = self.timeout_seconds
        output_limit = self.output_limit
        if permissions is not None:
            command, requested_timeout, requested_output = project_arguments(
                self.command, permissions
            )
            if requested_timeout is None:
                timeout = None
            elif timeout is None:
                timeout = requested_timeout
            else:
                timeout = min(timeout, requested_timeout)
            output_limit = min(output_limit, requested_output)
        provider = provider_name(command)
        stdin_input: str | None = prompt
        stdin_devnull = False
        if provider == "codex" and len(command) >= 2 and command[1] == "exec":
            command = command[:2] + codex_config_arguments(self._source_environment()) + command[2:]
            if len(command) >= 3 and command[-1] == "-":
                command = command[:-1] + [prompt]
                stdin_input = None
                stdin_devnull = True
        elif provider == "claude":
            command = command[:1] + claude_config_arguments(self._source_environment()) + command[1:]

        return run_cli_process(
            command,
            cwd=target,
            env=self._environment(temp_dir),
            stdin_input=stdin_input,
            stdin_devnull=stdin_devnull,
            timeout_seconds=timeout,
            output_limit=output_limit,
            progress=progress,
        )
