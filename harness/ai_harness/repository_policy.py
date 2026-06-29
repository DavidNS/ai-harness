"""Repository-local ignore policy for harness scans and change tracking."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from .errors import ConfigurationError

_CONFIG_FILE = "ai-harness.yml"

_DEFAULT_IGNORED_PARTS = frozenset({
    ".git",
    ".ai-harness",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    "target",
    ".gradle",
    "out",
    "coverage",
})
_DEFAULT_IGNORED_GLOBS = frozenset({"*.pyc", "*.pyo", "*.class", "*.log"})


def _normalize_path(value: str) -> str:
    normalized = value.strip().strip('"\'').replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("../") or "/../" in f"/{normalized}/" or normalized in {".", ".."}:
        raise ConfigurationError("ai-harness.yml ignore paths must be repository-relative")
    return normalized


def _normalize_glob(value: str) -> str:
    normalized = value.strip().strip('"\'')
    if not normalized:
        raise ConfigurationError("ai-harness.yml ignore globs must be nonempty")
    return normalized.replace("\\", "/")


@dataclass(frozen=True, slots=True)
class RepositoryPolicy:
    ignored_parts: frozenset[str] = _DEFAULT_IGNORED_PARTS
    ignored_paths: tuple[str, ...] = ()
    ignored_globs: frozenset[str] = _DEFAULT_IGNORED_GLOBS

    def ignores(self, relative: str | PurePosixPath | Path) -> bool:
        path = PurePosixPath(str(relative).replace("\\", "/"))
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            return True
        parts = path.parts
        if any(part in self.ignored_parts for part in parts):
            return True
        normalized = path.as_posix().strip("/")
        for base in self.ignored_paths:
            if normalized == base or normalized.startswith(f"{base}/"):
                return True
        name = path.name
        return any(fnmatch(normalized, pattern) or fnmatch(name, pattern) for pattern in self.ignored_globs)


def default_repository_policy() -> RepositoryPolicy:
    return RepositoryPolicy()


def _parse_ignore_config(text: str) -> tuple[list[str], list[str]]:
    paths: list[str] = []
    globs: list[str] = []
    section: str | None = None
    saw_content = False
    in_ignore = False
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        saw_content = True
        if line == "ignore:":
            in_ignore = True
            section = None
            continue
        if not in_ignore:
            raise ConfigurationError(f"ai-harness.yml line {line_number}: expected ignore:")
        if line in {"  paths:", "  globs:"}:
            section = line.strip()[:-1]
            continue
        if line in {"  paths: []", "  globs: []"}:
            section = line.strip().split(":", 1)[0]
            continue
        stripped = line.strip()
        if not line.startswith("    - ") or section not in {"paths", "globs"}:
            raise ConfigurationError(f"ai-harness.yml line {line_number}: expected an ignore list item")
        value = stripped[2:].strip()
        if section == "paths":
            paths.append(_normalize_path(value))
        else:
            globs.append(_normalize_glob(value))
    if not saw_content:
        return [], []
    if not in_ignore:
        raise ConfigurationError("ai-harness.yml must contain an ignore section")
    return paths, globs


def load_repository_policy(root: Path) -> RepositoryPolicy:
    config = Path(root) / _CONFIG_FILE
    paths: list[str] = []
    globs: list[str] = []
    if config.is_file():
        paths, globs = _parse_ignore_config(config.read_text(encoding="utf-8"))
    return RepositoryPolicy(
        ignored_parts=_DEFAULT_IGNORED_PARTS,
        ignored_paths=tuple(dict.fromkeys(paths)),
        ignored_globs=frozenset(_DEFAULT_IGNORED_GLOBS | frozenset(globs)),
    )
