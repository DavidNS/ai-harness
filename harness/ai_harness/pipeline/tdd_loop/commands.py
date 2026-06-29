"""Command execution helpers for the TDD loop."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .types import Command, CommandEvidence


def run_command(command: Command, cwd: Path, timeout_seconds: float) -> CommandEvidence:
    """Run a required command with captured, bounded controller evidence."""

    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command), cwd=cwd, shell=False, check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_seconds,
        )
        return CommandEvidence(command, completed.stdout, completed.stderr, completed.returncode,
                               time.monotonic() - started)
    except FileNotFoundError as exc:
        return CommandEvidence(command, "", str(exc), None, time.monotonic() - started, missing=True)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return CommandEvidence(command, stdout, stderr, None, time.monotonic() - started, timed_out=True)
