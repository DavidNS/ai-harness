"""Worker invocation and request-context helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Mapping, Sequence

from ..canonical import slugify
from ..ci_support import ci_observations_from_artifact
from ..phases import get_phase
from ..repository_policy import load_repository_policy
from ..text.markdown import markdown_section as _markdown_section_fn
from .classification import explorer_kind as _explorer_kind_fn
from .classification import repository_observation_kind as _repository_observation_kind_fn
from .context import RunContext

_REPOSITORY_OBSERVATION_LIMIT = 12
_REPOSITORY_OBSERVATION_BYTES = 12_000
_REPOSITORY_OBSERVATION_SCAN_LIMIT = 600
_REPOSITORY_OBSERVATION_FILE_BYTES = 120_000
_REPOSITORY_OBSERVATION_SUFFIXES = frozenset({".md", ".py", ".json", ".toml", ".yaml", ".yml"})
_SHORT_REPOSITORY_TERMS = frozenset({"ci", "cli", "ui", "ux"})
_REPOSITORY_OBSERVATION_STOP_TERMS = frozenset({
    "about", "after", "again", "analysis", "analyze", "artifact", "artifacts", "because",
    "before", "beginning", "change", "changes", "code", "could", "create", "current",
    "does", "docs", "evidence", "file", "from", "have", "implementation", "improvement",
    "improvements", "investigate", "line", "list", "repository", "should", "source",
    "that", "then", "there", "this", "type", "when", "with",
})


class WorkerExchange:
    """Build worker inputs and request context without depending on Orchestrator."""

    def __init__(
        self,
        context: RunContext,
        invoke_with_repair: Callable[..., str],
        explorer_scope: Callable[[], dict[str, object]],
    ) -> None:
        self._ctx = context
        self._invoke_with_repair = invoke_with_repair
        self._explorer_scope = explorer_scope

    def _worker(self, name: str, inputs: Mapping[str, object]) -> str:
        output = self._invoke_with_repair(name, inputs)
        artifact = get_phase(name).artifact
        self._ctx.artifacts.write(artifact, output)
        self._ctx.state.record_artifact(artifact, name.upper())
        return output

    def _inputs(self, *names: str) -> dict[str, object]:
        inputs: dict[str, object] = {}
        for name in names:
            inputs[name] = self._ctx.artifacts.read_json(name) if name.endswith(".json") else self._ctx.artifacts.read(name)
        return inputs

    def _full_sdd_inputs(self, *names: str) -> dict[str, object]:
        inputs = self._inputs(*names)
        inputs["explorer_scope"] = self._explorer_scope()
        return inputs

    @staticmethod
    def _markdown_section(candidate: str, section: str) -> str:
        return _markdown_section_fn(candidate, section)

    def _explorer_slug(self, candidate: str) -> str:
        request = self._ctx.state.load().user_input
        draft = re.search(r"draft-improvements/([\w./-]+)\.md", request)
        if draft is not None:
            return slugify(Path(draft.group(1)).name, fallback="analysis")
        first_line = candidate.replace("\r\n", "\n").splitlines()[0].strip() if candidate else ""
        if first_line.startswith("# Improvement:"):
            return slugify(first_line.removeprefix("# Improvement:"), fallback="analysis")
        problem = self._markdown_section(candidate, "Problem")
        return slugify(problem or request, fallback="analysis")

    def _explorer_kind(self, candidate: str) -> str:
        return _explorer_kind_fn(candidate)

    def _explorer_artifact_path(self, candidate: str) -> str:
        kind = self._explorer_kind(candidate)
        slug = self._explorer_slug(candidate)
        if kind == "existing-functionality":
            return self._ctx.canonical.knowledge_path(slug)
        return self._ctx.canonical.analysis_path(kind, slug)

    def _related_improvements(self) -> list[dict[str, str | int]]:
        query_parts = [self._ctx.state.load().user_input]
        query_parts.extend(entry.summary for entry in self._ctx.knowledge_context)
        try:
            return self._ctx.canonical.related_improvements("\n".join(query_parts), limit=5)
        except Exception:
            self._ctx.warnings.append("Related improvement discovery failed; explorer continued without it")
            return []

    @staticmethod
    def _repository_observation_kind(relative: str) -> str:
        return _repository_observation_kind_fn(relative)

    @staticmethod
    def _repository_observation_terms_from_text(value: object) -> set[str]:
        if not isinstance(value, str):
            return set()
        text = value.casefold()
        terms = set(re.findall(r"[a-z0-9]{4,}", text))
        terms.update(term for term in _SHORT_REPOSITORY_TERMS if re.search(rf"\b{re.escape(term)}\b", text))
        return terms

    def _repository_observation_terms(
        self,
        related_improvements: Sequence[Mapping[str, object]],
        intake: Mapping[str, object] | None = None,
    ) -> tuple[set[str], set[str], set[str]]:
        values = [self._ctx.state.load().user_input]
        values.extend(entry.summary for entry in self._ctx.knowledge_context)
        for item in related_improvements:
            values.append(str(item.get("path", "")))
            values.append(str(item.get("summary", "")))
        terms: set[str] = set()
        for value in values:
            terms.update(self._repository_observation_terms_from_text(value))
        source_terms: set[str] = set()
        test_terms: set[str] = set()
        if isinstance(intake, Mapping):
            claims = intake.get("claims", [])
            if isinstance(claims, list):
                for claim in claims:
                    if not isinstance(claim, Mapping):
                        continue
                    claim_terms = self._repository_observation_terms_from_text(claim.get("text"))
                    terms.update(claim_terms)
                    targets = claim.get("evidence_targets", [])
                    if not isinstance(targets, list):
                        continue
                    if "source" in targets:
                        source_terms.update(claim_terms)
                    if "tests" in targets:
                        test_terms.update(claim_terms)
        normalized = {term for term in terms if term not in _REPOSITORY_OBSERVATION_STOP_TERMS}
        return normalized, normalized & source_terms, normalized & test_terms

    def _candidate_observation_paths(self) -> list[Path]:
        paths: list[Path] = []
        policy = load_repository_policy(self._ctx.target)
        for path in self._ctx.target.rglob("*"):
            if len(paths) >= _REPOSITORY_OBSERVATION_SCAN_LIMIT:
                break
            try:
                relative = path.relative_to(self._ctx.target)
            except ValueError:
                continue
            parts = relative.parts
            if any(part.startswith(".") for part in parts) or policy.ignores(relative.as_posix()):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.casefold() not in _REPOSITORY_OBSERVATION_SUFFIXES:
                continue
            paths.append(path)
        return paths

    @staticmethod
    def _path_segments(relative: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", relative.casefold()))

    @staticmethod
    def _symbols_from_content(content: str) -> list[str]:
        return re.findall(r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", content, re.MULTILINE)[:12]

    @staticmethod
    def _line_matches(content: str, matched_terms: Sequence[str]) -> list[str]:
        matches: list[str] = []
        seen_lines: set[int] = set()
        lines = content.splitlines()
        ranked_lines: list[tuple[int, int, str]] = []
        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.casefold()
            line_terms = [term for term in matched_terms if term in lowered]
            if not line_terms:
                continue
            score = len(line_terms)
            if re.match(r"(?:async\s+def|def|class)\s+[A-Za-z_][A-Za-z0-9_]*", line):
                score += 6
            if re.match(r"(?:from|import)\s+", line):
                score -= 4
            ranked_lines.append((score, line_number, line))
        for _, line_number, line in sorted(ranked_lines, key=lambda item: (-item[0], item[1])):
            context_line = None
            for context_index in range(line_number - 2, 0, -1):
                candidate = lines[context_index - 1].strip()
                if re.match(r"(?:async\s+def|def|class)\s+[A-Za-z_][A-Za-z0-9_]*", candidate):
                    context_line = (context_index, candidate)
                    break
            if context_line is not None and context_line[0] not in seen_lines:
                seen_lines.add(context_line[0])
                matches.append(f"L{context_line[0]}: {context_line[1][:180]}")
            if line_number not in seen_lines:
                seen_lines.add(line_number)
                matches.append(f"L{line_number}: {line[:180]}")
            if len(matches) >= 4:
                break
        return matches

    def _gather_repository_observations(
        self,
        related_improvements: Sequence[Mapping[str, object]],
        intake: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        terms, source_terms, test_terms = self._repository_observation_terms(related_improvements, intake)
        if not terms:
            return []
        candidates: list[tuple[int, str, dict[str, object]]] = []
        for path in self._candidate_observation_paths():
            relative = str(path.relative_to(self._ctx.target))
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")[:_REPOSITORY_OBSERVATION_FILE_BYTES]
            except OSError:
                continue
            path_text = relative.casefold()
            content_text = content.casefold()
            matched_terms = sorted(term for term in terms if term in path_text or term in content_text)
            if not matched_terms:
                continue
            score = sum(3 for term in matched_terms if term in path_text)
            score += sum(1 for term in matched_terms if term in content_text)
            path_terms = self._path_segments(relative)
            path_term_hits = sorted(term for term in matched_terms if term in path_terms)
            score += 4 * len(path_term_hits)
            kind = self._repository_observation_kind(relative)
            if kind in {"test", "prompt", "worker", "analysis_doc"}:
                score += 1
            if kind == "source":
                score += sum(3 for term in matched_terms if term in source_terms)
            if kind == "test":
                score += sum(3 for term in matched_terms if term in test_terms)
            symbols = self._symbols_from_content(content)
            symbol_hits = [
                symbol for symbol in symbols
                if any(term in symbol.casefold() for term in matched_terms)
            ]
            score += 5 * len(symbol_hits)
            matches = self._line_matches(content, matched_terms)
            item: dict[str, object] = {
                "kind": kind,
                "path": relative,
                "score": score,
                "matched_terms": matched_terms[:8],
            }
            if path_term_hits:
                item["path_term_hits"] = path_term_hits[:8]
            if symbols:
                item["symbols"] = symbols
            if matches:
                item["matches"] = matches
            candidates.append((score, relative, item))
        observations: list[dict[str, object]] = []
        remaining = _REPOSITORY_OBSERVATION_BYTES
        for _, _, item in sorted(candidates, key=lambda candidate: (-candidate[0], candidate[1])):
            encoded = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if len(encoded) > remaining:
                compact = {key: item[key] for key in ("kind", "path", "score", "matched_terms")}
                encoded = json.dumps(compact, ensure_ascii=False, sort_keys=True)
                item = compact
            if len(encoded) > remaining:
                continue
            observations.append(item)
            remaining -= len(encoded)
            if len(observations) >= _REPOSITORY_OBSERVATION_LIMIT:
                break
        return observations

    def _repository_observations(
        self,
        related_improvements: Sequence[Mapping[str, object]],
        intake: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        ci_observations = ci_observations_from_artifact(self._ctx.artifacts)
        try:
            return [*ci_observations, *self._gather_repository_observations(related_improvements, intake)]
        except Exception:
            self._ctx.warnings.append("Repository observation gathering failed; explorer continued without it")
            return ci_observations

    def _referenced_markdown_documents(self, request: str) -> dict[str, str]:
        documents: dict[str, str] = {}
        for match in re.finditer(r"(?<![\w/.-])([\w./-]+\.md)(?![\w.-])", request):
            relative = match.group(1)
            candidate = (self._ctx.target / relative).resolve()
            if not candidate.is_relative_to(self._ctx.target) or not candidate.is_file():
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            documents[relative] = content[:50_000]
        return documents

    def _request_brief(self) -> str:
        request = self._ctx.state.load().user_input
        documents = self._referenced_markdown_documents(request)
        if not documents:
            return request
        parts = ["# User Request", request, "# Referenced Markdown Documents"]
        for relative, content in documents.items():
            parts.extend((f"## {relative}", content))
        return "\n\n".join(parts)
