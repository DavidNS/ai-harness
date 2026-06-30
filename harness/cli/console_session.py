"""Mutable launcher console session state."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ConsoleSession:
    cwd: Path
    provider: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    github_ci_mode: str | None = None
    branch: str | None = None
    prompt_file: Path | None = None
    verbose: bool = False
    dry_run: bool = False
    skip_warnings: bool = False
    recovery_blocked: bool = False

    @classmethod
    def from_namespace(cls, namespace: argparse.Namespace) -> "ConsoleSession":
        return cls(
            cwd=namespace.cwd,
            provider=getattr(namespace, "provider", None),
            model=getattr(namespace, "model", None),
            reasoning_effort=getattr(namespace, "reasoning_effort", None),
            github_ci_mode=getattr(namespace, "github_ci_mode", None),
            branch=getattr(namespace, "branch", None),
            prompt_file=getattr(namespace, "prompt_file", None),
            verbose=bool(getattr(namespace, "verbose", False)),
            dry_run=bool(getattr(namespace, "dry_run", False)),
            skip_warnings=bool(getattr(namespace, "skip_warnings", False)),
            recovery_blocked=bool(getattr(namespace, "_recovery_blocked", False)),
        )

    def sync_namespace(self, namespace: argparse.Namespace) -> None:
        namespace.cwd = self.cwd
        namespace.provider = self.provider
        namespace.model = self.model
        namespace.reasoning_effort = self.reasoning_effort
        namespace.github_ci_mode = self.github_ci_mode
        namespace.branch = self.branch
        namespace.prompt_file = self.prompt_file
        namespace.verbose = self.verbose
        namespace.dry_run = self.dry_run
        namespace.skip_warnings = self.skip_warnings
        setattr(namespace, "_recovery_blocked", self.recovery_blocked)
