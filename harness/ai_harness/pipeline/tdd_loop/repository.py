"""Repository snapshot and rollback helpers for the TDD loop."""

from __future__ import annotations

import difflib
import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ...repository_policy import RepositoryPolicy, load_repository_policy


@dataclass(frozen=True, slots=True)
class _RepositoryEntry:
    kind: str
    content: bytes


def _repository_snapshot(root: Path, policy: RepositoryPolicy | None = None) -> dict[str, _RepositoryEntry]:
    """Capture worker-visible repository content without following symlinks."""

    policy = policy or load_repository_policy(root)
    snapshot: dict[str, _RepositoryEntry] = {}

    def visit(directory: Path) -> None:
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = path.relative_to(root).as_posix()
            if policy.ignores(relative):
                continue
            if path.is_symlink():
                snapshot[relative] = _RepositoryEntry("symlink", os.readlink(path).encode())
            elif path.is_dir():
                visit(path)
            elif path.is_file():
                snapshot[relative] = _RepositoryEntry("file", path.read_bytes())

    visit(root)
    return snapshot


def _repository_directories(root: Path, policy: RepositoryPolicy | None = None) -> set[str]:
    """Capture repository directories so rollback can restore empty directory state."""

    policy = policy or load_repository_policy(root)
    directories: set[str] = set()

    def visit(directory: Path) -> None:
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = path.relative_to(root).as_posix()
            if policy.ignores(relative):
                continue
            if path.is_dir() and not path.is_symlink():
                directories.add(relative)
                visit(path)

    visit(root)
    return directories


def _repository_changes(before: Mapping[str, _RepositoryEntry],
                        after: Mapping[str, _RepositoryEntry]) -> tuple[tuple[str, ...], str]:
    changed = tuple(path for path in sorted(set(before) | set(after)) if before.get(path) != after.get(path))
    sections: list[str] = []
    for path in changed:
        old, new = before.get(path), after.get(path)
        status = "A" if old is None else "D" if new is None else "M"
        sections.append(f"{status} {path}")
        old_content = b"" if old is None else old.content
        new_content = b"" if new is None else new.content
        try:
            old_lines = old_content.decode("utf-8").splitlines(keepends=True)
            new_lines = new_content.decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            old_hash = hashlib.sha256(old_content).hexdigest()
            new_hash = hashlib.sha256(new_content).hexdigest()
            sections.append(f"Binary change sha256 {old_hash} -> {new_hash}")
        else:
            sections.extend(difflib.unified_diff(old_lines, new_lines,
                fromfile=f"a/{path}", tofile=f"b/{path}"))
    return changed, "\n".join(sections)


def _restore_repository_snapshot(
    root: Path,
    snapshot: Mapping[str, _RepositoryEntry],
    directories: set[str],
) -> None:
    """Restore files, symlinks, and empty directories changed since a snapshot."""

    policy = load_repository_policy(root)
    current = _repository_snapshot(root, policy)
    changed = [relative for relative in set(snapshot) | set(current)
               if snapshot.get(relative) != current.get(relative)]
    for relative in sorted(changed, reverse=True):
        _remove_path(root / relative)
    for relative in sorted(_repository_directories(root, policy) - directories, reverse=True):
        _remove_path(root / relative)
    for relative in sorted(directories):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for relative in sorted(changed):
        before = snapshot.get(relative)
        if before is None:
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if before.kind == "file":
            target.write_bytes(before.content)
        elif before.kind == "symlink":
            os.symlink(before.content.decode(), target)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
