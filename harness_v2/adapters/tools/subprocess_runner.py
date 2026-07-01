"""Subprocess-backed tool runner adapter."""

from __future__ import annotations

import subprocess

from harness_v2.backend.ports.tool_runner import ToolRunRequest, ToolRunResult


class SubprocessToolRunner:
    def run(self, request: ToolRunRequest) -> ToolRunResult:
        try:
            completed = subprocess.run(
                list(request.command),
                cwd=request.cwd,
                text=True,
                capture_output=True,
                check=False,
                timeout=request.timeout_seconds,
            )
        except FileNotFoundError as exc:
            return ToolRunResult(request.command, None, "", str(exc), missing_executable=True)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return ToolRunResult(request.command, None, stdout, stderr, timed_out=True)
        return ToolRunResult(request.command, completed.returncode, completed.stdout, completed.stderr)
