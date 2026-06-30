"""Analysis-scope resolution for full SDD runs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping

from ..explorer_scope_paths import (
    explorer_scope_policy_error,
    is_published_explorer_manifest,
    normalize_relative_path,
    repository_relative_path,
)
from ..canonical import checksum
from ..contracts.limits import ANALYSIS_SCOPE as _SCOPE_LIMITS
from ..errors import HarnessError

_ANALYSIS_SCOPE_MAX_ARTIFACTS = _SCOPE_LIMITS.max_artifacts
_ANALYSIS_SCOPE_ARTIFACT_BYTES = _SCOPE_LIMITS.artifact_bytes
_ANALYSIS_SCOPE_TOTAL_BYTES = _SCOPE_LIMITS.total_bytes
_ANALYSIS_SCOPE_TARGET_PATTERN = re.compile(
    r"(?<![\w/.-])(docs/explorer/improvements(?:/[\w.-]+)*(?:/improvement\.md)?/?)(?![\w.-])"
)
_ANALYSIS_SCOPE_MANIFEST_PATTERN = re.compile(
    r"(?<![\w/.-])([\w./-]*published/explorer\.json)(?![\w.-])"
)


def explorer_scope_target_tokens(request: str) -> tuple[str, ...]:
    matches: list[tuple[int, str]] = []
    for pattern in (_ANALYSIS_SCOPE_TARGET_PATTERN, _ANALYSIS_SCOPE_MANIFEST_PATTERN):
        matches.extend((match.start(), match.group(1)) for match in pattern.finditer(request))
    targets: list[str] = []
    for _, raw in sorted(matches, key=lambda item: item[0]):
        target = raw.strip().rstrip("/")
        if target and target not in targets:
            targets.append(target)
    return tuple(targets)


def _normalize_relative_path(relative: str) -> str:
    try:
        return normalize_relative_path(relative)
    except ValueError as exc:
        raise HarnessError("explorer scope target must be relative and contained") from exc


class ExplorerScopeResolver:
    def __init__(self, target: Path, artifacts: object, canonical: object) -> None:
        self.target = Path(target)
        self.artifacts = artifacts
        self.canonical = canonical
        self._explorer_handoff: dict[str, object] | None = None

    def repository_relative_path(self, relative: str) -> Path:
        try:
            return repository_relative_path(self.target, relative)
        except ValueError as exc:
            message = str(exc)
            if "symlink" in message:
                raise HarnessError("explorer scope target symlink escapes repository") from exc
            raise HarnessError("explorer scope target escapes repository") from exc

    def _read_json_artifact_or_file(self, relative: str) -> Mapping[str, object] | None:
        normalized = _normalize_relative_path(relative)
        if self.artifacts.exists(normalized):
            data = self.artifacts.read_json(normalized)
        else:
            path = self.repository_relative_path(normalized)
            if not path.is_file():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None

    def _load_manifest_handoff(self, manifest: Mapping[str, object]) -> None:
        raw = manifest.get("handoff_artifact")
        if not isinstance(raw, str) or not raw.strip():
            return
        try:
            handoff = self._read_json_artifact_or_file(raw)
        except Exception:
            return
        if handoff is not None and handoff.get("kind") == "explorer_handoff":
            self._explorer_handoff = dict(handoff)

    def _handoff_entry_for_path(self, normalized: str) -> Mapping[str, object] | None:
        handoff = self._explorer_handoff
        if not isinstance(handoff, dict):
            return None
        entries = handoff.get("entries")
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            raw_path = entry.get("path") or entry.get("suggested_path")
            if isinstance(raw_path, str) and _normalize_relative_path(raw_path) == normalized:
                return entry
        return None

    def manifest_json(self, relative: str) -> Mapping[str, object]:
        normalized = _normalize_relative_path(relative)
        if normalized == "published/explorer.json" and self.artifacts.exists(normalized):
            data = self.artifacts.read_json(normalized)
        else:
            path = self.repository_relative_path(normalized)
            if not path.is_file():
                raise HarnessError(f"explorer manifest does not exist: {normalized}")
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise HarnessError(f"explorer manifest is not readable JSON: {normalized}") from exc
        if not isinstance(data, dict):
            raise HarnessError("explorer manifest must be a JSON object")
        self._load_manifest_handoff(data)
        return data

    def paths_from_manifest(self, relative: str) -> tuple[list[str], str | None]:
        manifest = self.manifest_json(relative)
        raw_primary = manifest.get("primary_artifact")
        primary = _normalize_relative_path(raw_primary) if isinstance(raw_primary, str) and raw_primary else None
        paths: list[str] = []

        def add_path(value: object, kind: object = "improvement") -> None:
            if kind != "improvement" or not isinstance(value, str) or not value:
                return
            normalized = _normalize_relative_path(value)
            if normalized not in paths:
                paths.append(normalized)

        add_path(manifest.get("path") or manifest.get("suggested_path"), manifest.get("kind"))
        raw_artifacts = manifest.get("artifacts", [])
        if not isinstance(raw_artifacts, list):
            raise HarnessError("explorer manifest artifacts must be a list")
        for artifact in raw_artifacts:
            if not isinstance(artifact, Mapping):
                raise HarnessError("explorer manifest artifacts must be objects")
            add_path(artifact.get("path") or artifact.get("suggested_path"), artifact.get("kind"))
        if primary is not None and primary in paths:
            paths.remove(primary)
            paths.insert(0, primary)
        if not paths:
            raise HarnessError("explorer manifest does not contain improvement artifacts")
        return paths, primary

    def paths_from_analysis_target(self, target: str) -> tuple[list[str], str | None]:
        normalized = _normalize_relative_path(target)
        if is_published_explorer_manifest(normalized, allow_nested=True):
            return self.paths_from_manifest(normalized)
        if explorer_scope_policy_error(normalized, allow_nested_manifest=True) is not None:
            raise HarnessError("explorer scope target must be under docs/explorer/improvements")
        candidate = self.repository_relative_path(normalized)
        root = self.repository_relative_path("docs/explorer/improvements").resolve()
        if candidate.is_dir():
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root):
                raise HarnessError("explorer scope folder escapes docs/explorer/improvements")
            paths = sorted(
                str(path.relative_to(self.target))
                for path in candidate.rglob("improvement.md")
                if path.is_file() and path.resolve().is_relative_to(root)
            )
            if not paths:
                raise HarnessError(f"explorer scope folder has no improvement artifacts: {normalized}")
            return paths, None
        if not candidate.is_file():
            raise HarnessError(f"explorer scope target does not exist: {normalized}")
        return [normalized], None

    @staticmethod
    def is_improvement_artifact(content: str) -> bool:
        first_line = content.replace("\r\n", "\n").splitlines()[0].strip() if content else ""
        if first_line.startswith("# Improvement:"):
            return True
        if first_line in {"# Improvement Analysis v1", "# Improvement Explorer v1"}:
            match = re.search(r"(?ms)^## Outcome\s*\n(.*?)(?=^## |\Z)", content)
            outcome = (match.group(1).strip().casefold() if match else "")
            return outcome in {"", "improvement"}
        return False

    def explorer_scope_artifact(self, relative: str) -> dict[str, object]:
        normalized = _normalize_relative_path(relative)
        try:
            self.canonical.require_improvement_path(normalized)
        except Exception as exc:
            raise HarnessError(f"explorer scope item is not an improvement artifact: {normalized}") from exc
        path = self.repository_relative_path(normalized)
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise HarnessError(f"explorer scope artifact is not readable: {normalized}") from exc
        else:
            handoff_entry = self._handoff_entry_for_path(normalized)
            content = str(handoff_entry.get("content", "")) if handoff_entry is not None else ""
            if not content:
                raise HarnessError(f"explorer scope artifact does not exist: {normalized}")
        size = len(content.encode("utf-8"))
        if size > _ANALYSIS_SCOPE_ARTIFACT_BYTES:
            raise HarnessError(f"explorer scope artifact exceeds {_ANALYSIS_SCOPE_ARTIFACT_BYTES} bytes: {normalized}")
        if not self.is_improvement_artifact(content):
            raise HarnessError(f"explorer scope item is not an improvement artifact: {normalized}")
        first_line = content.replace("\r\n", "\n").splitlines()[0].strip()
        return {
            "path": normalized,
            "checksum": checksum(content),
            "bytes": size,
            "title": first_line.lstrip("# ").strip() or normalized,
            "content": content,
        }

    def resolve(self, request: str) -> dict[str, object]:
        targets = explorer_scope_target_tokens(request)
        if not targets:
            return {
                "schema_version": 1,
                "kind": "explorer_scope",
                "input_targets": [],
                "primary_artifact": None,
                "artifacts": [],
                "limits": {
                    "max_artifacts": _ANALYSIS_SCOPE_MAX_ARTIFACTS,
                    "max_artifact_bytes": _ANALYSIS_SCOPE_ARTIFACT_BYTES,
                    "max_total_bytes": _ANALYSIS_SCOPE_TOTAL_BYTES,
                },
            }
        paths: list[str] = []
        primary: str | None = None
        for target in targets:
            resolved, target_primary = self.paths_from_analysis_target(target)
            if primary is None and target_primary is not None:
                primary = target_primary
            for relative in resolved:
                normalized = _normalize_relative_path(relative)
                if normalized not in paths:
                    paths.append(normalized)
        if primary is not None and primary in paths:
            paths.remove(primary)
            paths.insert(0, primary)
        if not paths:
            raise HarnessError("explorer scope is empty")
        if len(paths) > _ANALYSIS_SCOPE_MAX_ARTIFACTS:
            raise HarnessError(f"explorer scope exceeds {_ANALYSIS_SCOPE_MAX_ARTIFACTS} artifacts")
        artifacts: list[dict[str, object]] = []
        total_bytes = 0
        for relative in paths:
            artifact = self.explorer_scope_artifact(relative)
            total_bytes += int(artifact["bytes"])
            if total_bytes > _ANALYSIS_SCOPE_TOTAL_BYTES:
                raise HarnessError(f"explorer scope exceeds {_ANALYSIS_SCOPE_TOTAL_BYTES} total bytes")
            artifact["primary"] = primary == artifact["path"]
            artifacts.append(artifact)
        result: dict[str, object] = {
            "schema_version": 1,
            "kind": "explorer_scope",
            "input_targets": list(targets),
            "primary_artifact": primary if primary in {str(item["path"]) for item in artifacts} else None,
            "artifacts": artifacts,
            "limits": {
                "max_artifacts": _ANALYSIS_SCOPE_MAX_ARTIFACTS,
                "max_artifact_bytes": _ANALYSIS_SCOPE_ARTIFACT_BYTES,
                "max_total_bytes": _ANALYSIS_SCOPE_TOTAL_BYTES,
            },
        }
        if self._explorer_handoff is not None:
            result["explorer_handoff"] = self._explorer_handoff
        return result
