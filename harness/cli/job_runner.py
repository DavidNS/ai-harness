"""Background backend job runner for the interactive console."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .bootstrap import RUNNER


JobStatus = Literal["running", "finished", "cancelled", "interrupted", "failed"]


@dataclass(frozen=True, slots=True)
class JobHandle:
    job_id: str
    command: list[str]
    root: Path
    events_path: Path
    status: JobStatus = "running"
    pid: int | None = None
    exit_code: int | None = None


class JobStore:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()
        self.root = self.repository / ".ai-harness" / "runtime" / "jobs"

    def job_root(self, job_id: str) -> Path:
        return self.root / job_id

    def events_path(self, job_id: str) -> Path:
        return self.job_root(job_id) / "events.jsonl"

    def write_metadata(self, handle: JobHandle) -> None:
        handle.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "job_id": handle.job_id,
            "command": handle.command,
            "status": handle.status,
            "pid": handle.pid,
            "exit_code": handle.exit_code,
            "events_path": str(handle.events_path),
            "updated_at": _utc_now(),
        }
        (handle.root / "job.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        path = self.events_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"time": _utc_now(), **event}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")

    def read_metadata(self, job_id: str) -> dict[str, Any] | None:
        path = self.job_root(job_id) / "job.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        if not self.root.is_dir():
            return jobs
        for path in sorted(self.root.iterdir(), reverse=True):
            metadata = self.read_metadata(path.name)
            if metadata is not None:
                jobs.append(metadata)
        return jobs

    def read_events(self, job_id: str, *, start: int = 0) -> tuple[int, list[dict[str, Any]]]:
        path = self.events_path(job_id)
        if not path.is_file():
            return start, []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as stream:
            stream.seek(start)
            for line in stream:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    events.append(value)
            return stream.tell(), events


class BackgroundJobRunner:
    def __init__(self, repository: Path) -> None:
        self.store = JobStore(repository)
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    def submit(self, args: list[str], *, request: str | None = None) -> JobHandle:
        job_id = _new_job_id()
        command = [sys.executable, "-B", str(RUNNER), *args]
        root = self.store.job_root(job_id)
        handle = JobHandle(job_id, command, root, self.store.events_path(job_id))
        self.store.write_metadata(handle)
        self.store.append_event(job_id, {"type": "started", "command": command})
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        handle = JobHandle(job_id, command, root, self.store.events_path(job_id), pid=process.pid)
        self.store.write_metadata(handle)
        with self._lock:
            self._processes[job_id] = process
        if process.stdin is not None:
            try:
                process.stdin.write(request or "")
            except BrokenPipeError:
                pass
            finally:
                process.stdin.close()
        for stream_name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            if stream is not None:
                threading.Thread(target=self._capture_stream, args=(job_id, stream_name, stream), daemon=True).start()
        threading.Thread(target=self._wait, args=(job_id, process, command, root), daemon=True).start()
        return handle

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            process = self._processes.get(job_id)
        if process is None or process.poll() is not None:
            return False
        with self._lock:
            self._cancelled.add(job_id)
        self.store.append_event(job_id, {"type": "cancelled"})
        process.terminate()
        return True

    def process(self, job_id: str) -> subprocess.Popen[str] | None:
        with self._lock:
            return self._processes.get(job_id)

    def _capture_stream(self, job_id: str, stream_name: str, stream) -> None:
        try:
            for line in stream:
                event_type = "progress" if stream_name == "stderr" and line.startswith("Running ") else stream_name
                self.store.append_event(job_id, {"type": event_type, "stream": stream_name, "text": line.rstrip("\n")})
        finally:
            stream.close()

    def _wait(self, job_id: str, process: subprocess.Popen[str], command: list[str], root: Path) -> None:
        started = time.monotonic()
        try:
            code = process.wait()
        finally:
            with self._lock:
                self._processes.pop(job_id, None)
        with self._lock:
            cancelled = job_id in self._cancelled
            self._cancelled.discard(job_id)
        status: JobStatus = "finished" if process.returncode == 0 else "failed"
        if cancelled:
            status = "cancelled"
        elif process.returncode is not None and process.returncode < 0:
            status = "interrupted"
        elapsed = round(time.monotonic() - started, 3)
        self._append_waiting_decisions(job_id)
        self.store.append_event(job_id, {"type": "finished", "exit_code": code, "elapsed_seconds": elapsed})
        self.store.write_metadata(JobHandle(job_id, command, root, self.store.events_path(job_id), status=status, pid=process.pid, exit_code=code))

    def _append_waiting_decisions(self, job_id: str) -> None:
        try:
            from .runtime import _unfinished_runs

            waiting = [state for _, state in _unfinished_runs(self.store.repository) if state.get("status") == "waiting_for_user"]
        except Exception:
            return
        for state in waiting:
            run_id = state.get("run_id")
            if isinstance(run_id, str):
                self.store.append_event(job_id, {"type": "decision_requested", "run_id": run_id})


def _new_job_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
