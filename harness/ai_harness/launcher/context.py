"""Shared launcher command context."""

from __future__ import annotations

from pathlib import Path

from ..output import default_command_context

_RUNNER = Path(__file__).resolve().parents[2] / "run.py"


def command_context(repository: Path):
    return default_command_context(repository, _RUNNER)
