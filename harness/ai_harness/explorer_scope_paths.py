"""Shared analysis-scope path policy helpers."""

from __future__ import annotations

from pathlib import Path, PurePath

IMPROVEMENTS_ROOT = "docs/explorer/improvements"
PUBLISHED_EXPLORER_MANIFEST = "published/explorer.json"


def normalize_relative_path(value: str) -> str:
    raw_value = value.strip().rstrip("/")
    if not raw_value:
        raise ValueError("path is empty")
    raw = PurePath(raw_value)
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("path must be relative and stay inside the repository")
    return "/".join(raw.parts)


def repository_relative_path(repository: Path, relative: str) -> Path:
    normalized = normalize_relative_path(relative)
    root = repository.resolve()
    candidate = root.joinpath(*PurePath(normalized).parts)
    if not candidate.parent.resolve().is_relative_to(root):
        raise ValueError("path escapes the repository")
    if candidate.exists() and not candidate.resolve().is_relative_to(root):
        raise ValueError("path symlink escapes the repository")
    return candidate


def is_improvements_scope(normalized: str) -> bool:
    return normalized == IMPROVEMENTS_ROOT or normalized.startswith(f"{IMPROVEMENTS_ROOT}/")


def is_improvement_artifact_path(normalized: str) -> bool:
    return is_improvements_scope(normalized) and normalized.endswith("/improvement.md")


def is_published_explorer_manifest(normalized: str, *, allow_nested: bool = False) -> bool:
    if normalized == PUBLISHED_EXPLORER_MANIFEST:
        return True
    return allow_nested and normalized.endswith(f"/{PUBLISHED_EXPLORER_MANIFEST}")


def explorer_scope_policy_error(normalized: str, *, allow_nested_manifest: bool = False) -> str | None:
    if is_published_explorer_manifest(normalized, allow_nested=allow_nested_manifest):
        return None
    if is_improvements_scope(normalized):
        return None
    return "full-SDD explorer scopes must be under docs/explorer/improvements or be published/explorer.json"
