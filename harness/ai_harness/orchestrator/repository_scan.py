"""RepositoryScanner — builds repository snapshots for LLM context.

Pure filesystem/git reads; no writes except appending to a shared warnings
list. Previously four staticmethods/instance-methods on AnalysisQualityMixin.

The scanner is stateless beyond its constructor arguments and cheap to
instantiate — callers may create it inline.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path, PurePath
from typing import Mapping

from ..contracts.limits import REPOSITORY_OBSERVATION as _REPO_OBS_LIMITS
from ..contracts.limits import REPOSITORY_SNAPSHOT as _REPO_SNAP_LIMITS
from ..repository_policy import load_repository_policy
from .classification import repository_observation_kind
from .quality import ImprovementQualityGate

_SNAPSHOT_LIMIT = _REPO_SNAP_LIMITS.max_files
_SNAPSHOT_BYTES = _REPO_SNAP_LIMITS.max_bytes
_SNAPSHOT_FILE_BYTES = _REPO_SNAP_LIMITS.max_file_bytes
_OBSERVATION_SUFFIXES = _REPO_OBS_LIMITS.suffixes

_QUALITY_GATE = ImprovementQualityGate()


class RepositoryScanner:
    """Reads the repository to build a JSON snapshot suitable for LLM context.

    ``warnings`` is mutated in-place when a subprocess call fails so the
    caller's warning list (held in RunContext) is kept in sync.
    """

    def __init__(self, target: Path, warnings: list[str]) -> None:
        self._target = target
        self._warnings = warnings

    # ------------------------------------------------------------------ #
    # Path admission                                                       #
    # ------------------------------------------------------------------ #

    def snapshot_path_allowed(self, relative: str) -> bool:
        path = PurePath(relative)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            return False
        if any(part.startswith(".") for part in path.parts) or load_repository_policy(self._target).ignores(relative):
            return False
        if path.parts[:3] == ("knowledge-source", "patches", "pending"):
            return False
        candidate = self._target / relative
        return candidate.is_file() and candidate.suffix.casefold() in _OBSERVATION_SUFFIXES

    # ------------------------------------------------------------------ #
    # Candidate discovery                                                  #
    # ------------------------------------------------------------------ #

    def snapshot_candidates(
        self,
        task_documents: dict[str, Mapping[str, object]],
        repository_observations: list[dict[str, object]],
    ) -> list[str]:
        candidates: list[str] = []
        for raw in task_documents.values():
            touched = raw.get("touched_paths", [])
            if isinstance(touched, list):
                candidates.extend(str(item) for item in touched if isinstance(item, str))
        for observation in repository_observations:
            if not isinstance(observation, Mapping):
                continue
            candidates.extend(_QUALITY_GATE.repository_observation_path_hints(observation))
        try:
            commands = (
                ["git", "-C", str(self._target), "diff", "--name-only", "HEAD", "--"],
                ["git", "-C", str(self._target), "ls-files", "--modified", "--others", "--exclude-standard"],
            )
            for command in commands:
                completed = subprocess.run(
                    command, capture_output=True, text=True, check=False, timeout=5,
                )
                if completed.returncode == 0:
                    candidates.extend(line.strip() for line in completed.stdout.splitlines() if line.strip())
        except Exception:
            self._warnings.append(
                "Repository snapshot changed-path discovery failed; continuing with bounded candidates"
            )
        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            relative = candidate.strip().replace("\\", "/")
            if relative and relative not in seen and self.snapshot_path_allowed(relative):
                seen.add(relative)
                unique.append(relative)
        return unique[:_SNAPSHOT_LIMIT]

    # ------------------------------------------------------------------ #
    # Entry building                                                       #
    # ------------------------------------------------------------------ #

    def snapshot_entry(self, relative: str) -> dict[str, object] | None:
        path = self._target / relative
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")[:_SNAPSHOT_FILE_BYTES]
        except OSError:
            return None
        snippets: list[dict[str, object]] = []
        for line_number, raw_line in enumerate(content.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            snippets.append({"line_start": line_number, "line_end": line_number, "excerpt": line[:220]})
            if len(snippets) >= 4:
                break
        symbols = re.findall(r"^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", content, re.MULTILINE)[:12]
        item: dict[str, object] = {
            "path": relative,
            "kind": repository_observation_kind(relative),
            "bytes_read": len(content),
            "snippets": snippets,
        }
        if symbols:
            item["symbols"] = symbols
        return item

    # ------------------------------------------------------------------ #
    # Full snapshot                                                        #
    # ------------------------------------------------------------------ #

    def snapshot(
        self,
        task_documents: dict[str, Mapping[str, object]],
        repository_observations: list[dict[str, object]],
    ) -> dict[str, object]:
        head = None
        try:
            completed = subprocess.run(
                ["git", "-C", str(self._target), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=False, timeout=5,
            )
            if completed.returncode == 0:
                head = completed.stdout.strip()
        except Exception:
            self._warnings.append(
                "Repository snapshot git metadata unavailable; continuing without git head"
            )
        entries: list[dict[str, object]] = []
        remaining = _SNAPSHOT_BYTES
        for relative in self.snapshot_candidates(task_documents, repository_observations):
            item = self.snapshot_entry(relative)
            if item is None:
                continue
            encoded = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if len(encoded) > remaining:
                compact = {"path": item["path"], "kind": item["kind"], "snippets": item.get("snippets", [])[:1]}
                encoded = json.dumps(compact, ensure_ascii=False, sort_keys=True)
                item = compact
            if len(encoded) > remaining:
                continue
            entries.append(item)
            remaining -= len(encoded)
        return {
            "repository_root": str(self._target),
            "git_head": head,
            "entries": entries,
            "excluded_roots": sorted(load_repository_policy(self._target).ignored_parts),
        }
