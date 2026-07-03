"""Subprocess-backed model provider adapters for v2."""

from __future__ import annotations

import codecs
import json
import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from harness_v2.backend.ports.model_provider import (
    CapabilityProjection,
    CapabilityProjectionError,
    ModelProviderError,
    ModelProviderRequest,
    ModelProviderResult,
)

DEFAULT_ENV_ALLOWLIST = frozenset(
    {
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TERM",
        "TMPDIR",
        "XDG_CONFIG_HOME",
    }
)
_PIPE_DRAIN_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class _ProjectedCommand:
    argv: list[str]
    stdin_input: str | None
    stdin_devnull: bool
    cleanup_paths: tuple[Path, ...] = ()


class _BoundedCapture:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.parts: list[str] = []
        self.size = 0
        self.truncated = False

    def append(self, text: str) -> None:
        if not text or self.truncated:
            return
        encoded = text.encode("utf-8")
        remaining = self.limit - self.size
        if len(encoded) <= remaining:
            self.parts.append(text)
            self.size += len(encoded)
            return
        self.parts.append(encoded[:remaining].decode("utf-8", "ignore") + "\n[output truncated]")
        self.size = self.limit
        self.truncated = True

    def value(self) -> str:
        return "".join(self.parts)


def _read_stream(pipe: object, capture: _BoundedCapture) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    try:
        fileno = pipe.fileno()  # type: ignore[attr-defined]
        while True:
            try:
                data = os.read(fileno, 4096)
            except OSError:
                break
            if not data:
                break
            capture.append(decoder.decode(data))
        capture.append(decoder.decode(b"", final=True))
    finally:
        try:
            pipe.close()  # type: ignore[attr-defined]
        except OSError:
            pass


def _join_readers(threads: Sequence[threading.Thread], pipes: Sequence[object]) -> None:
    deadline = time.monotonic() + _PIPE_DRAIN_TIMEOUT_SECONDS
    for thread in threads:
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
    if any(thread.is_alive() for thread in threads):
        for pipe in pipes:
            try:
                pipe.close()  # type: ignore[attr-defined]
            except OSError:
                pass


def _write_stdin(process: subprocess.Popen[bytes], stdin_input: str) -> None:
    assert process.stdin is not None
    try:
        process.stdin.write(stdin_input.encode("utf-8"))
    except BrokenPipeError:
        pass
    finally:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        process.kill()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _provider_name(command: Sequence[str]) -> str | None:
    executable = Path(command[0]).name.lower()
    return executable if executable in {"codex", "claude"} else None


def _effective_timeout(adapter_timeout: float | None, request_timeout: float | None) -> float | None:
    if request_timeout is None:
        return None
    if adapter_timeout is None:
        return request_timeout
    return min(adapter_timeout, request_timeout)


def _effective_env(source: Mapping[str, str], allowed: frozenset[str]) -> dict[str, str]:
    return {key: source[key] for key in allowed if key in source}


def _model_arg(model: str | None) -> list[str]:
    return ["--model", model] if model else []


def _codex_config(request: ModelProviderRequest) -> list[str]:
    args = _model_arg(request.model.model)
    effort = request.model.reasoning_effort
    if effort:
        escaped = effort.replace("\\", "\\\\").replace('"', '\\"')
        args.extend(("-c", f'model_reasoning_effort="{escaped}"'))
    return args


def _schema_json(request: ModelProviderRequest) -> str | None:
    if request.output_schema is None:
        return None
    return json.dumps(request.output_schema.schema, sort_keys=True, separators=(",", ":"))


def _schema_temp_file(request: ModelProviderRequest) -> Path | None:
    schema_json = _schema_json(request)
    if schema_json is None:
        return None
    safe_name = "".join(char if char.isalnum() or char in "._-" else "_" for char in request.output_schema.name)
    fd, raw_path = tempfile.mkstemp(prefix=f"ai-harness-{safe_name}-", suffix=".schema.json")
    path = Path(raw_path)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(schema_json)
        handle.write("\n")
    return path


def _project(command: Sequence[str], request: ModelProviderRequest) -> _ProjectedCommand:
    provider = _provider_name(command)
    capabilities = request.capabilities
    if provider == "claude":
        return _ProjectedCommand(_project_claude(command, capabilities, request), request.prompt, False)
    if provider == "codex":
        argv, cleanup_paths = _project_codex(command, capabilities, request)
        return _ProjectedCommand(argv, None, True, cleanup_paths)
    if _has_capabilities(capabilities) or request.output_schema is not None:
        raise CapabilityProjectionError("custom provider commands cannot enforce worker capabilities or output schemas")
    return _ProjectedCommand(list(command), request.prompt, False)


def _has_capabilities(capabilities: CapabilityProjection) -> bool:
    return bool(capabilities.paths or capabilities.commands or capabilities.skills or capabilities.mcp_tools)


def _mode(capabilities: CapabilityProjection) -> str:
    if len(capabilities.paths) != 1:
        raise CapabilityProjectionError("CLI providers require one repository-wide path rule")
    path = capabilities.paths[0]
    if path.pattern != "**":
        raise CapabilityProjectionError("CLI providers cannot enforce partial path permissions")
    return path.mode


def _reject_commands_and_mcp(capabilities: CapabilityProjection, provider: str) -> None:
    if capabilities.commands:
        raise CapabilityProjectionError(f"{provider} cannot enforce an argv command allow-list")
    if capabilities.mcp_tools:
        raise CapabilityProjectionError(f"{provider} cannot enforce per-tool MCP permissions")


def _project_claude(command: Sequence[str], capabilities: CapabilityProjection, request: ModelProviderRequest) -> list[str]:
    mode = _mode(capabilities)
    _reject_commands_and_mcp(capabilities, "Claude")
    tools = "Read,Glob,Grep" if mode == "read" else "Read,Glob,Grep,Edit,Write"
    projected = list(command[:1]) + _model_arg(request.model.model) + list(command[1:])
    projected.extend(("--tools", tools, "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}'))
    schema_json = _schema_json(request)
    if schema_json is not None:
        projected.extend(("--json-schema", schema_json))
    if mode == "write":
        projected.extend(("--permission-mode", "acceptEdits"))
    return projected


def _project_codex(command: Sequence[str], capabilities: CapabilityProjection, request: ModelProviderRequest) -> tuple[list[str], tuple[Path, ...]]:
    mode = _mode(capabilities)
    _reject_commands_and_mcp(capabilities, "Codex")
    projected = list(command)
    if projected[-1:] == ["-"]:
        projected = projected[:-1]
    if len(projected) >= 2 and Path(projected[0]).name == "codex" and projected[1] == "exec":
        projected = projected[:2] + _codex_config(request) + projected[2:]
    cleanup_paths: tuple[Path, ...] = ()
    schema_path = _schema_temp_file(request)
    if schema_path is not None:
        projected.extend(("--output-schema", str(schema_path)))
        cleanup_paths = (schema_path,)
    sandbox = "read-only" if mode == "read" else "workspace-write"
    projected.extend(("--sandbox", sandbox, request.prompt))
    return projected, cleanup_paths


@dataclass(frozen=True, slots=True)
class CliModelProvider:
    """Execute one configured CLI command without shell interpretation."""

    command: tuple[str, ...]
    timeout_seconds: float | None = 120.0
    output_limit: int = 1_000_000
    allowed_environment: frozenset[str] = field(default_factory=lambda: DEFAULT_ENV_ALLOWLIST)
    environment: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.command or any(not isinstance(arg, str) or not arg for arg in self.command):
            raise ValueError("provider command must contain nonempty arguments")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("provider timeout must be positive or None")
        if self.output_limit <= 0:
            raise ValueError("provider output limit must be positive")

    @classmethod
    def for_name(cls, name: str, **kwargs: object) -> "CliModelProvider":
        commands = {"claude": ("claude", "--print"), "codex": ("codex", "exec", "-")}
        try:
            command = commands[name.lower()]
        except KeyError as exc:
            raise ValueError(f"unsupported provider: {name}") from exc
        return cls(command, **kwargs)

    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        target = request.working_directory.resolve()
        if not target.is_dir():
            raise ModelProviderError(f"provider cwd is not a directory: {target}")
        projected = _project(self.command, request)
        try:
            return self._run_process(
                projected.argv,
                cwd=target,
                env=_effective_env(os.environ if self.environment is None else self.environment, self.allowed_environment),
                stdin_input=projected.stdin_input,
                stdin_devnull=projected.stdin_devnull,
                timeout_seconds=_effective_timeout(self.timeout_seconds, request.timeout.seconds),
                output_limit=min(self.output_limit, request.truncation.output_bytes),
            )
        finally:
            for path in projected.cleanup_paths:
                path.unlink(missing_ok=True)

    def _run_process(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        stdin_input: str | None,
        stdin_devnull: bool,
        timeout_seconds: float | None,
        output_limit: int,
    ) -> ModelProviderResult:
        started = time.monotonic()
        stdout = _BoundedCapture(output_limit)
        stderr = _BoundedCapture(output_limit)
        process: subprocess.Popen[bytes] | None = None
        stdin_thread: threading.Thread | None = None
        threads: list[threading.Thread] = []
        pipes: list[object] = []
        try:
            popen_stdin = subprocess.DEVNULL if stdin_devnull else (subprocess.PIPE if stdin_input is not None else None)
            process = subprocess.Popen(
                list(command),
                stdin=popen_stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=dict(env),
                shell=False,
            )
            assert process.stdout is not None
            assert process.stderr is not None
            for pipe, capture in ((process.stdout, stdout), (process.stderr, stderr)):
                thread = threading.Thread(target=_read_stream, args=(pipe, capture), daemon=True)
                thread.start()
                threads.append(thread)
                pipes.append(pipe)
            if stdin_input is not None:
                stdin_thread = threading.Thread(target=_write_stdin, args=(process, stdin_input), daemon=True)
                stdin_thread.start()
            exit_code = process.wait(timeout=timeout_seconds)
            if stdin_thread is not None:
                stdin_thread.join(timeout=1)
            _join_readers(threads, pipes)
            return ModelProviderResult(
                stdout.value(),
                stderr.value(),
                exit_code,
                time.monotonic() - started,
                truncated=stdout.truncated or stderr.truncated,
            )
        except subprocess.TimeoutExpired:
            if process is not None:
                _stop(process)
            if stdin_thread is not None:
                stdin_thread.join(timeout=1)
            _join_readers(threads, pipes)
            return ModelProviderResult(
                stdout.value(),
                stderr.value(),
                None,
                time.monotonic() - started,
                timed_out=True,
                truncated=stdout.truncated or stderr.truncated,
            )
        except OSError as exc:
            if process is not None:
                _stop(process)
            if stdin_thread is not None:
                stdin_thread.join(timeout=1)
            _join_readers(threads, pipes)
            raise ModelProviderError(f"provider process failed to start or run: {exc}") from exc
