"""Durable live-run registry for repository-local harness state."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..models import utc_now

OPEN_STATUSES = frozenset({"active", "waiting_for_user"})
TERMINAL_STATUSES = frozenset({"archived", "completed", "failed", "impossible"})


@dataclass(frozen=True, slots=True)
class LiveRunEntry:
    run_id: str
    current_dir: str
    target_repository: str
    status: str
    created_at: str
    updated_at: str
    pid: int | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LiveRunEntry | None":
        try:
            run_id = str(value["run_id"])
            current_dir = str(value["current_dir"])
            target_repository = str(value["target_repository"])
            status = str(value["status"])
            created_at = str(value["created_at"])
            updated_at = str(value["updated_at"])
        except (KeyError, TypeError, ValueError):
            return None
        if not run_id or not current_dir or not target_repository or not status:
            return None
        pid_value = value.get("pid")
        pid = int(pid_value) if isinstance(pid_value, int) and pid_value > 0 else None
        return cls(run_id, current_dir, target_repository, status, created_at, updated_at, pid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "current_dir": self.current_dir,
            "target_repository": self.target_repository,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "pid": self.pid,
        }


class LiveRunRegistry:
    def __init__(self, target_repository: Path) -> None:
        self.target_repository = Path(target_repository).resolve()
        self.artifacts_root = self.target_repository / ".ai-harness" / "artifacts"
        self.path = self.artifacts_root / "live-runs.json"
        self._entries = self._load_entries()

    def _load_entries(self) -> dict[str, LiveRunEntry]:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        raw_runs = value.get("runs", []) if isinstance(value, dict) else []
        entries: dict[str, LiveRunEntry] = {}
        if isinstance(raw_runs, list):
            for raw in raw_runs:
                if not isinstance(raw, dict):
                    continue
                entry = LiveRunEntry.from_dict(raw)
                if entry is not None:
                    entries[entry.run_id] = entry
        return entries

    def entries(self) -> list[LiveRunEntry]:
        return sorted(self._entries.values(), key=lambda item: (item.created_at, item.run_id))

    def get(self, run_id: str) -> LiveRunEntry | None:
        return self._entries.get(run_id)

    def current_path(self, entry: LiveRunEntry) -> Path:
        current = Path(entry.current_dir)
        return current if current.is_absolute() else self.artifacts_root / current

    def open_entries(self) -> list[LiveRunEntry]:
        return [entry for entry in self.entries() if entry.status in OPEN_STATUSES]

    def upsert(self, entry: LiveRunEntry) -> None:
        existing = self._entries.get(entry.run_id)
        if existing is not None:
            entry = LiveRunEntry(
                entry.run_id,
                entry.current_dir,
                entry.target_repository,
                entry.status,
                existing.created_at,
                entry.updated_at,
                entry.pid,
            )
        self._entries[entry.run_id] = entry
        self._write()

    def record(
        self,
        run_id: str,
        current_dir: Path,
        status: str,
        *,
        created_at: str | None = None,
        updated_at: str | None = None,
        pid: int | None = None,
    ) -> None:
        now = utc_now()
        entry = LiveRunEntry(
            run_id,
            str(Path(current_dir).resolve()),
            str(self.target_repository),
            status,
            created_at or now,
            updated_at or now,
            pid if status in OPEN_STATUSES else None,
        )
        self.upsert(entry)

    def update_status(
        self,
        run_id: str,
        status: str,
        *,
        current_dir: Path | None = None,
        updated_at: str | None = None,
        pid: int | None = None,
    ) -> None:
        existing = self._entries.get(run_id)
        now = updated_at or utc_now()
        if existing is None:
            if current_dir is None:
                return
            self.record(run_id, current_dir, status, updated_at=now, pid=pid)
            return
        entry = LiveRunEntry(
            existing.run_id,
            str(Path(current_dir).resolve()) if current_dir is not None else existing.current_dir,
            existing.target_repository,
            status,
            existing.created_at,
            now,
            pid if status in OPEN_STATUSES else None,
        )
        self._entries[run_id] = entry
        self._write()

    def close(self, run_id: str, status: str, *, current_dir: Path | None = None) -> None:
        self.update_status(run_id, status, current_dir=current_dir, pid=None)

    def merge_entries(self, entries: Iterable[LiveRunEntry]) -> None:
        changed = False
        for entry in entries:
            if entry.run_id not in self._entries:
                self._entries[entry.run_id] = entry
                changed = True
        if changed:
            self._write()

    def _write(self) -> None:
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "runs": [entry.to_dict() for entry in self.entries()],
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
