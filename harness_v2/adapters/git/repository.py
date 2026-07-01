"""Filesystem repository snapshot adapter for v2 TDD."""

from __future__ import annotations

import shutil
from pathlib import Path

from harness_v2.backend.ports.repository import RepositoryDiff, RepositorySnapshot


class FilesystemRepositoryAdapter:
    """Capture and restore a working tree under one root directory."""

    def capture(self, root: Path | str) -> RepositorySnapshot:
        base = Path(root)
        files: dict[str, bytes] = {}
        directories: list[str] = []
        if not base.exists():
            raise FileNotFoundError(str(base))
        for path in sorted(base.rglob("*")):
            if _is_ignored(path, base):
                continue
            rel = path.relative_to(base).as_posix()
            if path.is_dir():
                directories.append(rel)
            elif path.is_file():
                files[rel] = path.read_bytes()
        return RepositorySnapshot(files=files, directories=tuple(directories))

    def diff(self, before: RepositorySnapshot, after: RepositorySnapshot) -> RepositoryDiff:
        before_paths = set(before.files)
        after_paths = set(after.files)
        added = tuple(sorted(after_paths - before_paths))
        deleted = tuple(sorted(before_paths - after_paths))
        modified = tuple(sorted(path for path in before_paths & after_paths if before.files[path] != after.files[path]))
        return RepositoryDiff(added=added, modified=modified, deleted=deleted)

    def restore(self, root: Path | str, snapshot: RepositorySnapshot) -> None:
        base = Path(root)
        base.mkdir(parents=True, exist_ok=True)
        snapshot_files = set(snapshot.files)
        snapshot_dirs = set(snapshot.directories)
        for path in sorted(base.rglob("*"), key=lambda item: len(item.relative_to(base).parts), reverse=True):
            if _is_ignored(path, base):
                continue
            rel = path.relative_to(base).as_posix()
            if path.is_file() or path.is_symlink():
                if rel not in snapshot_files:
                    path.unlink()
            elif path.is_dir() and rel not in snapshot_dirs:
                shutil.rmtree(path)
        for rel in snapshot_dirs:
            (base / rel).mkdir(parents=True, exist_ok=True)
        for rel, content in snapshot.files.items():
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)


def _is_ignored(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return ".git" in parts or "__pycache__" in parts
