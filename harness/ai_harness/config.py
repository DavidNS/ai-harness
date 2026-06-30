"""Validated configuration and harness-relative resource locations."""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import ConfigurationError

MINIMUM_PYTHON = (3, 11)
CONTROLLER_DEFAULT_ATTEMPTS = 3
CONTROLLER_MAX_ATTEMPTS = 10
ALLOWED_PROVIDERS = frozenset({"claude", "codex", "local", "unknown"})


def harness_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    root = harness_root()
    candidate = root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(root):
        raise ConfigurationError("resource path escapes the harness root")
    return candidate


def _command(value: str) -> tuple[str, ...]:
    try:
        result = tuple(shlex.split(value))
    except ValueError as exc:
        raise ConfigurationError("provider command is malformed") from exc
    if not result or any("\x00" in part for part in result):
        raise ConfigurationError("provider command must not be empty")
    return result


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    provider: str = "unknown"
    provider_command: tuple[str, ...] = ()
    model: str = ""
    timeout_seconds: float = 120.0
    max_attempts: int = CONTROLLER_DEFAULT_ATTEMPTS
    git_branch_mode: str = "current"
    github_ci_mode: str = "baseline"

    def __post_init__(self) -> None:
        if sys.version_info < MINIMUM_PYTHON:
            raise ConfigurationError("Python 3.11 or newer is required")
        if self.provider not in ALLOWED_PROVIDERS:
            raise ConfigurationError(f"unsupported provider: {self.provider}")
        if self.provider in {"claude", "codex"} and not self.provider_command:
            raise ConfigurationError("CLI providers require a command")
        if not isinstance(self.model, str):
            raise ConfigurationError("model must be a string")
        if isinstance(self.timeout_seconds, bool) or self.timeout_seconds <= 0:
            raise ConfigurationError("timeout must be positive")
        if isinstance(self.max_attempts, bool) or not 1 <= self.max_attempts <= CONTROLLER_MAX_ATTEMPTS:
            raise ConfigurationError("max attempts must be between one and ten")
        if self.git_branch_mode not in {"off", "current", "create", "create-from-main"}:
            raise ConfigurationError("git branch mode must be current or create-from-main")
        if self.github_ci_mode not in {"off", "baseline", "branch"}:
            raise ConfigurationError("GitHub CI mode must be off, baseline, or branch")


def load_config(values: Mapping[str, str] | None = None) -> HarnessConfig:
    env = os.environ if values is None else values
    provider = env.get("AI_HARNESS_PROVIDER", "unknown").strip().lower()
    default = provider if provider in {"claude", "codex"} else ""
    raw_command = env.get("AI_HARNESS_PROVIDER_COMMAND", default)
    model = env.get("AI_HARNESS_MODEL", "").strip()
    if not model and provider == "codex":
        model = env.get("AI_HARNESS_CODEX_MODEL", "").strip()
    if not model and provider == "claude":
        model = env.get("AI_HARNESS_CLAUDE_MODEL", "").strip()
    try:
        timeout = float(env.get("AI_HARNESS_TIMEOUT", "120"))
        attempts = int(env.get("AI_HARNESS_MAX_ATTEMPTS", str(CONTROLLER_DEFAULT_ATTEMPTS)))
    except ValueError as exc:
        raise ConfigurationError("timeout and max attempts must be numeric") from exc
    branch_mode = env.get("AI_HARNESS_GIT_BRANCH_MODE", "current").strip().lower()
    return HarnessConfig(provider, _command(raw_command) if raw_command else (), model, timeout, attempts, branch_mode)
