"""Explorer-scope selection helpers for launcher prompts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from ai_harness.explorer_scope_paths import (
    explorer_scope_policy_error,
    is_improvement_artifact_path,
    is_published_explorer_manifest,
    normalize_relative_path,
    repository_relative_path,
)

_FULL_IMPLEMENTATION_PATTERN = re.compile(r"\b(?:full[-\s]+sdd|full_implementation|full\s+implementation)\b", re.IGNORECASE)
_REQUEST_PATH_PATTERN = re.compile(r"(?<![\w/.-])((?:docs|published)(?:/[^\s\"<>]*)?)(?![\w/.-])")


class ImprovementCandidate(NamedTuple):
    path: str
    title: str


def clean_request_path_token(value: str) -> str:
    return value.strip().strip(".,;:)]}")


def request_path_tokens(request: str) -> list[str]:
    tokens: list[str] = []
    for match in _REQUEST_PATH_PATTERN.finditer(request):
        token = clean_request_path_token(match.group(1))
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def normalized_relative(value: str) -> tuple[str | None, str | None]:
    try:
        return normalize_relative_path(value), None
    except ValueError as exc:
        return None, str(exc)


def contained_path(repository: Path, relative: str) -> Path | None:
    try:
        return repository_relative_path(repository, relative)
    except (OSError, ValueError):
        return None


def improvement_title(path: Path, fallback: str) -> str:
    try:
        for line in path.read_text(encoding="utf-8").replace("\r\n", "\n").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            title = stripped.lstrip("# ").strip()
            if title.startswith("Improvement:"):
                title = title.split(":", 1)[1].strip()
            return title or fallback
    except (OSError, UnicodeDecodeError):
        return fallback
    return fallback


def discover_improvement_candidates(repository: Path) -> list[ImprovementCandidate]:
    root = repository / "docs" / "explorer" / "improvements"
    if not root.exists():
        return []
    candidates: list[ImprovementCandidate] = []
    try:
        paths = sorted(root.rglob("improvement.md"))
    except OSError:
        return []
    for path in paths:
        if not path.is_file() or path.parent == root:
            continue
        try:
            relative = "/".join(path.resolve().relative_to(repository.resolve()).parts)
        except (OSError, ValueError):
            continue
        candidates.append(ImprovementCandidate(relative, improvement_title(path, relative)))
    return candidates


def validate_explorer_scope(repository: Path, value: str) -> tuple[bool, str | None, str]:
    normalized, error = normalized_relative(value)
    if normalized is None:
        return False, None, error or "invalid path"
    candidate = contained_path(repository, normalized)
    if candidate is None:
        return False, None, "path escapes the repository"
    if is_published_explorer_manifest(normalized):
        return (candidate.is_file(), normalized if candidate.is_file() else None, "published/explorer.json does not exist")
    policy_error = explorer_scope_policy_error(normalized)
    if policy_error is not None:
        return False, None, policy_error
    if is_improvement_artifact_path(normalized):
        if candidate.is_file():
            return True, normalized, ""
        return False, None, f"improvement artifact does not exist: {normalized}"
    if candidate.is_dir():
        try:
            if any(path.is_file() for path in candidate.rglob("improvement.md")):
                return True, normalized, ""
        except OSError:
            return False, None, f"explorer scope folder is not readable: {normalized}"
        return False, None, f"explorer scope folder has no improvement artifacts: {normalized}"
    return False, None, "use an existing improvement.md artifact, an improvement folder, or published/explorer.json"


def request_scope_prompt_reason(repository: Path, request: str) -> str | None:
    if not _FULL_IMPLEMENTATION_PATTERN.search(request):
        return None
    saw_valid_scope = False
    for token in request_path_tokens(request):
        if token.startswith("docs") or token == "published/explorer.json":
            ok, _, reason = validate_explorer_scope(repository, token)
            if ok:
                saw_valid_scope = True
            else:
                return f"{token} is not a valid full-SDD explorer scope: {reason}"
    if saw_valid_scope:
        return None
    return "Full implementation needs an explorer scope under docs/explorer/improvements or published/explorer.json."


def request_with_scope(request: str, scope: str) -> str:
    stripped = request.strip()
    if scope in stripped:
        return stripped
    if stripped in {"docs", "docs/"}:
        return f"Implement {scope}"
    return f"{stripped} {scope}" if stripped else f"Implement {scope}"
