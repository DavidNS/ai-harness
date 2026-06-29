"""Private subprocess execution support for CLI providers."""

from __future__ import annotations

import codecs
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Mapping, Sequence

from .base import ProviderProgress, ProviderResult

_PIPE_DRAIN_TIMEOUT_SECONDS = 1.0


class _BoundedCapture:
    """Capture the initial output window while readers continue draining pipes."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.parts: list[str] = []
        self.size = 0
        self.truncated = False

    def append(self, text: str) -> None:
        if not text or self.truncated:
            return
        remaining = self.limit - self.size
        if len(text) <= remaining:
            self.parts.append(text)
            self.size += len(text)
            return
        self.parts.append(text[:remaining] + "\n[output truncated]")
        self.size = self.limit
        self.truncated = True

    def value(self) -> str:
        return "".join(self.parts)


def _emit_progress(progress: ProviderProgress | None, stream: str, text: str) -> None:
    if progress is None or not text:
        return
    try:
        progress(stream, text)
    except Exception:
        pass


def _read_stream(
    pipe: object,
    stream: str,
    capture: _BoundedCapture,
    progress: ProviderProgress | None,
) -> None:
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
            text = decoder.decode(data)
            if text:
                capture.append(text)
                _emit_progress(progress, stream, text)
        tail = decoder.decode(b"", final=True)
        if tail:
            capture.append(tail)
            _emit_progress(progress, stream, tail)
    finally:
        try:
            pipe.close()  # type: ignore[attr-defined]
        except OSError:
            pass


def _join_reader_threads(threads: Sequence[threading.Thread], pipes: Sequence[object]) -> None:
    deadline = time.monotonic() + _PIPE_DRAIN_TIMEOUT_SECONDS
    for thread in threads:
        remaining = max(0.0, deadline - time.monotonic())
        thread.join(timeout=remaining)
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


def _stop_process(process: subprocess.Popen[bytes], *, interrupt: bool = False) -> None:
    if process.poll() is not None:
        return
    try:
        if interrupt:
            process.terminate()
        else:
            process.kill()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            return
        process.wait()


def run_cli_process(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    stdin_input: str | None,
    stdin_devnull: bool,
    timeout_seconds: float | None,
    output_limit: int,
    progress: ProviderProgress | None = None,
) -> ProviderResult:
    started = time.monotonic()
    stdout_capture = _BoundedCapture(output_limit)
    stderr_capture = _BoundedCapture(output_limit)
    process: subprocess.Popen[bytes] | None = None
    stdin_thread: threading.Thread | None = None
    reader_threads: list[threading.Thread] = []
    reader_pipes: list[object] = []
    try:
        popen_stdin = subprocess.DEVNULL if stdin_devnull else (
            subprocess.PIPE if stdin_input is not None else None
        )
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
        for stream, pipe, capture in (
            ("stdout", process.stdout, stdout_capture),
            ("stderr", process.stderr, stderr_capture),
        ):
            thread = threading.Thread(
                target=_read_stream,
                args=(pipe, stream, capture, progress),
                daemon=True,
            )
            thread.start()
            reader_threads.append(thread)
            reader_pipes.append(pipe)
        if stdin_input is not None:
            stdin_thread = threading.Thread(
                target=_write_stdin,
                args=(process, stdin_input),
                daemon=True,
            )
            stdin_thread.start()

        exit_code = process.wait(timeout=timeout_seconds)
        if stdin_thread is not None:
            stdin_thread.join(timeout=1)
        _join_reader_threads(reader_threads, reader_pipes)
        return ProviderResult(
            stdout=stdout_capture.value(),
            stderr=stderr_capture.value(),
            exit_code=exit_code,
            duration_seconds=time.monotonic() - started,
            truncated=stdout_capture.truncated or stderr_capture.truncated,
        )
    except subprocess.TimeoutExpired:
        if process is not None:
            _stop_process(process)
        if stdin_thread is not None:
            stdin_thread.join(timeout=1)
        _join_reader_threads(reader_threads, reader_pipes)
        return ProviderResult(
            stdout=stdout_capture.value(),
            stderr=stderr_capture.value(),
            exit_code=None,
            duration_seconds=time.monotonic() - started,
            timed_out=True,
            truncated=stdout_capture.truncated or stderr_capture.truncated,
        )
    except KeyboardInterrupt:
        if process is not None:
            _stop_process(process, interrupt=True)
        raise
