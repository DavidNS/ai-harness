"""EvidenceExtractor — validate and normalize explorer repository evidence.

Single responsibility: given an explorer bundle entry, extract, validate,
and deduplicate the repository evidence items it references. Pure read-only
operation over the repository filesystem and artifact store.

Previously the private _extract_explorer_repository_evidence cluster on
ExplorerFlowMixin.
"""
from __future__ import annotations

import re
from pathlib import Path, PurePath
from typing import Callable, Mapping, Sequence

from ..control_outputs import ExplorerBundleEntry
from ..repository_policy import load_repository_policy
from ..text.markdown import markdown_section as _markdown_section
from .classification import repository_observation_kind as _repository_observation_kind


class EvidenceExtractor:
    """Extract and normalize repository evidence for an explorer bundle entry.

    Cheap to instantiate — one instance per bundle entry via _make_evidence_extractor().
    ``stage_json_fn`` is injected to keep this class free of artifact-store coupling.
    """

    def __init__(
        self,
        target: Path,
        repository_observations: list[dict[str, object]],
        *,
        stage_json_fn: Callable[[str], dict[str, object]],
    ) -> None:
        self._target = target
        self._repository_observations = repository_observations
        self._stage_json = stage_json_fn

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def extract(
        self, entry: ExplorerBundleEntry
    ) -> tuple[list[dict[str, object]], list[dict[str, object]], list[str]]:
        """Return (accepted, rejected, sources_checked) for *entry*."""
        raw_candidates: list[tuple[str, Mapping[str, object]]] = []
        sources_checked: list[str] = []

        def add_candidate(source: str, item: Mapping[str, object]) -> None:
            raw_candidates.append((source, item))
            if source not in sources_checked:
                sources_checked.append(source)

        for repo_ev in entry.repository_evidence:
            add_candidate("repository_evidence", repo_ev)
        if not entry.repository_evidence and entry.content is not None:
            evidence_text = (
                _markdown_section(entry.content, "Evidence")
                or _markdown_section(entry.content, "Context")
                or entry.content
            )
            for text_ev in self._repository_evidence_from_text(evidence_text):
                add_candidate("entry_text", text_ev)
        if not entry.repository_evidence:
            for struct_src, struct_ev in self._explorer_structured_evidence_candidates():
                add_candidate(struct_src, struct_ev)
            for observation in self._repository_observations:
                if isinstance(observation, Mapping):
                    for obs_ev in self._repository_evidence_from_observation(observation):
                        add_candidate("repository_observation", obs_ev)

        accepted: list[dict[str, object]] = []
        rejected: list[dict[str, object]] = []
        seen: set[tuple[object, object, object, object]] = set()
        for raw_src, raw_ev in raw_candidates:
            evidence, rejection = self._normalize_repository_evidence_item(raw_ev, source=raw_src)
            if rejection is not None:
                rejected.append(rejection)
                continue
            assert evidence is not None
            key = (
                evidence.get("type"),
                evidence.get("file"),
                evidence.get("line_start"),
                evidence.get("symbol"),
            )
            if key in seen:
                continue
            seen.add(key)
            accepted.append(evidence)
        return accepted, rejected, sources_checked

    # ------------------------------------------------------------------
    # Structured evidence candidates from artifact store
    # ------------------------------------------------------------------

    def _explorer_structured_evidence_candidates(
        self,
    ) -> list[tuple[str, Mapping[str, object]]]:
        candidates: list[tuple[str, Mapping[str, object]]] = []
        try:
            discovery = self._stage_json("explorer_discovery")
        except Exception:
            discovery = {}
        if isinstance(discovery, Mapping):
            claims = discovery.get("claims", [])
            if isinstance(claims, list):
                for claim in claims:
                    if isinstance(claim, Mapping):
                        candidates.extend(
                            self._text_evidence_candidates("discovery_claim", claim.get("evidence", []))
                        )
            directions = discovery.get("candidate_directions", [])
            if isinstance(directions, list):
                for direction in directions:
                    if not isinstance(direction, Mapping):
                        continue
                    candidates.extend(
                        self._text_evidence_candidates("candidate_direction", direction.get("evidence", []))
                    )
                    candidates.extend(
                        self._text_evidence_candidates("candidate_direction", direction.get("mechanism"))
                    )
                    candidates.extend(
                        self._text_evidence_candidates("candidate_direction", direction.get("behavioral_delta"))
                    )
        try:
            decision = self._stage_json("explorer_decision")
        except Exception:
            decision = {}
        if isinstance(decision, Mapping):
            for field in (
                "evidence",
                "value_hypothesis",
                "behavioral_delta",
                "minimum_verification",
                "counterevidence",
                "falsifying_conditions",
            ):
                candidates.extend(
                    self._text_evidence_candidates("explorer_decision", decision.get(field, []))
                )
        return candidates

    # ------------------------------------------------------------------
    # Text-based evidence mining
    # ------------------------------------------------------------------

    def _text_evidence_candidates(
        self, source: str, value: object
    ) -> list[tuple[str, Mapping[str, object]]]:
        if isinstance(value, str) and value.strip():
            return [(source, item) for item in self._repository_evidence_from_text(value)]
        if isinstance(value, list):
            candidates: list[tuple[str, Mapping[str, object]]] = []
            for item in value:
                candidates.extend(self._text_evidence_candidates(source, item))
            return candidates
        return []

    def _repository_evidence_from_text(self, text: str) -> Sequence[Mapping[str, object]]:
        candidates: list[dict[str, object]] = []
        seen: set[str] = set()

        def add_path(raw: str) -> None:
            relative = raw.strip("`.,:;)]}>").lstrip("`([{<")
            if not relative or relative in seen:
                return
            seen.add(relative)
            candidates.append({"path": relative, "kind": _repository_observation_kind(relative)})

        extension_pattern = r"(?<![\w/.-])([A-Za-z0-9_./-]+\.(?:py|md|json|toml|yaml|yml))(?![\w.-])"
        for match in re.finditer(extension_pattern, text):
            add_path(match.group(1))

        token_pattern = r"(?<![\w/.-])([A-Za-z0-9_][A-Za-z0-9_./-]{1,})(?![\w.-])"
        for match in re.finditer(token_pattern, text):
            candidate = match.group(1).strip("`.,:;)]}>").lstrip("`([{<")
            if not candidate or "." in PurePath(candidate).name:
                continue
            if "/" not in candidate and "-" not in candidate:
                continue
            path = PurePath(candidate)
            if path.is_absolute() or any(
                part in {"", ".", ".."} or part.startswith(".") for part in path.parts
            ):
                continue
            try:
                resolved = (self._target / candidate).resolve()
                resolved.relative_to(self._target)
            except (OSError, ValueError):
                continue
            if resolved.is_file():
                add_path(candidate)
        return candidates

    def _repository_evidence_from_observation(
        self, observation: Mapping[str, object]
    ) -> list[Mapping[str, object]]:
        candidates: list[Mapping[str, object]] = [observation]
        finding = observation.get("finding")
        if isinstance(finding, Mapping):
            merged = dict(finding)
            if "kind" not in merged and "kind" in observation:
                merged["kind"] = observation["kind"]
            candidates.append(merged)
        expanded: list[Mapping[str, object]] = []
        for candidate in candidates:
            item = dict(candidate)
            matches = item.get("matches")
            if isinstance(matches, list):
                for match in matches:
                    if not isinstance(match, str):
                        continue
                    line_match = re.match(r"L(\d+):\s*(.*)", match.strip())
                    if line_match:
                        clone = dict(item)
                        clone["line_start"] = int(line_match.group(1))
                        clone["line_end"] = int(line_match.group(1))
                        clone["excerpt"] = line_match.group(2).strip()
                        expanded.append(clone)
                if expanded:
                    continue
            expanded.append(item)
        return expanded

    # ------------------------------------------------------------------
    # Normalization and validation
    # ------------------------------------------------------------------

    def _normalize_repository_evidence_item(
        self, item: Mapping[str, object], *, source: str
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        raw_kind = item.get("kind")
        if isinstance(raw_kind, str) and raw_kind.strip().casefold() == "observation_gap":
            raw_path = (
                item.get("path") or item.get("file") or item.get("filepath") or item.get("location")
            )
            rejection: dict[str, object] = {
                "source": source,
                "reason": "observation_gap",
                "item": dict(item),
            }
            if isinstance(raw_path, str) and raw_path.strip():
                rejection["path"] = raw_path.strip().replace("\\", "/")
            return None, rejection
        raw_path = (
            item.get("path") or item.get("file") or item.get("filepath") or item.get("location")
        )
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None, {"source": source, "reason": "missing_path", "item": dict(item)}
        relative = raw_path.strip().replace("\\", "/")
        parts = PurePath(relative).parts
        if PurePath(relative).is_absolute() or any(part in {"", ".", ".."} for part in parts):
            return None, {"source": source, "path": relative, "reason": "unsafe_path"}
        if any(part.startswith(".") for part in parts) or load_repository_policy(self._target).ignores(relative):
            return None, {"source": source, "path": relative, "reason": "generated_or_hidden_path"}
        if parts[:3] == ("knowledge-source", "patches", "pending"):
            return None, {"source": source, "path": relative, "reason": "pending_patch_path"}
        if parts[:3] in {
            ("docs", "analysis", "improvements"),
            ("docs", "analysis", "limitations"),
            ("docs", "analysis", "probably-a-bullshit"),
        }:
            return None, {"source": source, "path": relative, "reason": "analysis_publication_artifact"}
        candidate = (self._target / relative).resolve()
        try:
            candidate.relative_to(self._target)
        except ValueError:
            return None, {"source": source, "path": relative, "reason": "path_escapes_repository"}
        if not candidate.is_file():
            return None, {"source": source, "path": relative, "reason": "path_missing"}
        kind = self._knowledge_evidence_type(str(item.get("kind", "")), relative, candidate)
        evidence: dict[str, object] = {"type": kind, "file": relative}
        for key in ("symbol", "excerpt", "commit"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                evidence[key] = value.strip()
        for key in ("line_start", "line_end"):
            value = item.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                evidence[key] = value
        line_end_val = evidence.get("line_end")
        line_start_val = evidence.get("line_start")
        if (
            isinstance(line_end_val, int)
            and isinstance(line_start_val, int)
            and line_end_val < line_start_val
        ):
            return None, {"source": source, "path": relative, "reason": "invalid_line_range"}
        content_rejection = self._validate_evidence_content(candidate, evidence, source=source)
        if content_rejection is not None:
            return None, content_rejection
        return evidence, None

    def _validate_evidence_content(
        self, path: Path, evidence: Mapping[str, object], *, source: str
    ) -> dict[str, object] | None:
        excerpt = evidence.get("excerpt")
        symbol = evidence.get("symbol")
        if not isinstance(excerpt, str) and not isinstance(symbol, str):
            return None
        scope, failure = self._evidence_file_scope(path, evidence)
        if failure is not None:
            return {"source": source, "path": str(evidence.get("file", "")), "reason": failure}
        assert scope is not None
        normalized_scope = self._normalized_evidence_text(scope)
        if isinstance(excerpt, str) and excerpt.strip():
            if self._normalized_evidence_text(excerpt) not in normalized_scope:
                return {
                    "source": source,
                    "path": str(evidence.get("file", "")),
                    "reason": "excerpt_not_found",
                }
        if isinstance(symbol, str) and symbol.strip():
            if self._normalized_evidence_text(symbol) not in normalized_scope:
                return {
                    "source": source,
                    "path": str(evidence.get("file", "")),
                    "reason": "symbol_not_found",
                }
        return None

    def _evidence_file_scope(
        self, path: Path, evidence: Mapping[str, object]
    ) -> tuple[str | None, str | None]:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return None, "file_read_failed"
        start = evidence.get("line_start")
        end = evidence.get("line_end")
        if isinstance(start, int) and not isinstance(start, bool):
            if start > len(lines):
                return None, "line_range_out_of_bounds"
            end_line = end if isinstance(end, int) and not isinstance(end, bool) else start
            if end_line > len(lines):
                return None, "line_range_out_of_bounds"
            return "\n".join(lines[start - 1 : end_line]), None
        return "\n".join(lines), None

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalized_evidence_text(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _knowledge_evidence_type(kind: str, path: str, candidate: Path | None = None) -> str:
        normalized = kind.replace("_", "-").casefold()
        if normalized == "test" or path.startswith("tests/") or "/tests/" in path:
            return "test"
        if normalized in {"code", "source"}:
            return "code"
        if normalized in {"worker", "prompt"}:
            return (
                "code"
                if path.endswith(".py") or EvidenceExtractor._extensionless_python_source(path, candidate)
                else "documentation"
            )
        if normalized in {"documentation", "analysis-doc", "analysis_doc", "doc"} or path.endswith(".md"):
            return "documentation"
        if normalized == "decision":
            return "decision"
        return (
            "code"
            if path.endswith(".py") or EvidenceExtractor._extensionless_python_source(path, candidate)
            else "documentation"
        )

    @staticmethod
    def _extensionless_python_source(path: str, candidate: Path | None = None) -> bool:
        if Path(path).suffix:
            return False
        if PurePath(path).name == "ai-harness":
            return True
        if candidate is None:
            return False
        try:
            first_line = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
        except (IndexError, OSError):
            return False
        return first_line.startswith("#!") and "python" in first_line.casefold()
