"""Extensible knowledge protocol and local SQLite implementation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..errors import KnowledgeError
from ..models import KnowledgeEntry


@runtime_checkable
class KnowledgeStore(Protocol):
    def add_entry(self, entry: KnowledgeEntry) -> None: ...
    def search(self, query: str, limit: int = 5) -> list[KnowledgeEntry]: ...
    def list_recent(self, limit: int = 10) -> list[KnowledgeEntry]: ...
    def clear(self) -> None: ...


class SQLiteKnowledgeStore:
    _LIST_FIELDS = ("decisions", "patterns", "errors", "solutions", "tags")

    def __init__(self, path: Path, *, enable_fts: bool | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("""CREATE TABLE IF NOT EXISTS knowledge (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, summary TEXT NOT NULL,
            decisions TEXT NOT NULL, patterns TEXT NOT NULL, errors TEXT NOT NULL,
            solutions TEXT NOT NULL, tags TEXT NOT NULL, created_at TEXT NOT NULL)""")
        self.fts_enabled = False
        if enable_fts is not False:
            try:
                self._connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(id UNINDEXED, summary, decisions, patterns, errors, solutions, tags)")
                self.fts_enabled = True
            except sqlite3.OperationalError:
                if enable_fts is True:
                    raise KnowledgeError("FTS5 was required but is unavailable")
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteKnowledgeStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def add_entry(self, entry: KnowledgeEntry) -> None:
        values = [entry.id, entry.run_id, entry.summary, *(json.dumps(getattr(entry, field), ensure_ascii=False) for field in self._LIST_FIELDS), entry.created_at]
        try:
            with self._connection:
                self._connection.execute("INSERT INTO knowledge VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
                if self.fts_enabled:
                    searchable = [entry.id, entry.summary, *(" ".join(getattr(entry, field)) for field in self._LIST_FIELDS)]
                    self._connection.execute("INSERT INTO knowledge_fts VALUES (?, ?, ?, ?, ?, ?, ?)", searchable)
        except sqlite3.Error as exc:
            raise KnowledgeError("failed to add knowledge entry") from exc

    def clear(self) -> None:
        try:
            with self._connection:
                self._connection.execute("DELETE FROM knowledge")
                if self.fts_enabled:
                    self._connection.execute("DELETE FROM knowledge_fts")
        except sqlite3.Error as exc:
            raise KnowledgeError("failed to clear knowledge cache") from exc

    @staticmethod
    def _entry(row: sqlite3.Row) -> KnowledgeEntry:
        return KnowledgeEntry(row["id"], row["run_id"], row["summary"], *(tuple(json.loads(row[field])) for field in SQLiteKnowledgeStore._LIST_FIELDS), row["created_at"])

    @staticmethod
    def _limit(limit: int) -> int:
        if isinstance(limit, bool) or limit < 1:
            raise KnowledgeError("limit must be a positive integer")
        return limit

    def list_recent(self, limit: int = 10) -> list[KnowledgeEntry]:
        rows = self._connection.execute("SELECT * FROM knowledge ORDER BY created_at DESC, id DESC LIMIT ?", (self._limit(limit),)).fetchall()
        return [self._entry(row) for row in rows]

    def search(self, query: str, limit: int = 5) -> list[KnowledgeEntry]:
        if not query.strip():
            return []
        if self.fts_enabled:
            rows = self._connection.execute("SELECT k.* FROM knowledge_fts f JOIN knowledge k ON k.id=f.id WHERE knowledge_fts MATCH ? ORDER BY k.created_at DESC, k.id DESC LIMIT ?", (query, self._limit(limit))).fetchall()
        else:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            fields = ("summary", "decisions", "patterns", "errors", "solutions", "tags")
            predicate = " OR ".join(f"{field} LIKE ? ESCAPE '\\'" for field in fields)
            rows = self._connection.execute(f"SELECT * FROM knowledge WHERE {predicate} ORDER BY created_at DESC, id DESC LIMIT ?", (*([pattern] * len(fields)), self._limit(limit))).fetchall()
        return [self._entry(row) for row in rows]
