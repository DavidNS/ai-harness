"""Deterministic repository context for EXPLORE."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath

_IMPROVEMENTS_ROOT = Path("docs/explorer/improvements")
_OBSERVATION_LIMIT = 12
_OBSERVATION_BYTES = 12_000
_SCAN_LIMIT = 600
_FILE_BYTES = 120_000
_SUMMARY_BYTES = 80_000
_SUFFIXES = frozenset({".md", ".py", ".json", ".toml", ".yaml", ".yml", ".js", ".ts", ".tsx", ".jsx", ".ini", ".cfg"})
_SHORT_TERMS = frozenset({"ci", "cli", "ui", "ux"})
_IGNORED_PARTS = frozenset({"__pycache__", "node_modules", "dist", "build", "coverage", "htmlcov", "vendor", ".tox", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache"})
_STOP_TERMS = frozenset({
    "about", "after", "again", "analysis", "analyze", "artifact", "artifacts", "because",
    "before", "beginning", "behavior", "change", "changes", "code", "could", "create",
    "current", "does", "docs", "evidence", "explore", "explorer", "file", "from", "have",
    "implementation", "improvement", "improvements", "investigate", "line", "list",
    "repository", "should", "source", "that", "then", "there", "this", "type",
    "when", "with",
})


def related_improvements(root: Path, query: str, *, limit: int = 5) -> list[dict[str, object]]:
    terms = _terms_from_text(query)
    if not terms or limit <= 0:
        return []
    candidates: list[tuple[int, str, str, str]] = []
    for path in _improvement_paths(root):
        relative = _relative(root, path)
        if not relative:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")[:_SUMMARY_BYTES]
        except OSError:
            continue
        summary = _improvement_summary(content, relative)
        path_terms = _terms_from_text(relative)
        content_terms = _terms_from_text(content)
        score = sum(3 for term in terms if term in path_terms)
        score += sum(1 for term in terms if term in content_terms)
        if score > 0:
            candidates.append((score, relative, summary, _checksum(content)))
    return [
        {"id": f"RI{index}", "path": path, "summary": summary, "checksum": digest, "score": score}
        for index, (score, path, summary, digest) in enumerate(sorted(candidates, key=lambda item: (-item[0], item[1]))[:limit], start=1)
    ]


def repository_observations(
    root: Path,
    request: str,
    profile: Mapping[str, object],
    related: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    terms = _observation_terms(request, profile, related)
    if not terms:
        return []
    candidates: list[tuple[int, str, dict[str, object]]] = []
    for path in _candidate_paths(root):
        relative = _relative(root, path)
        if not relative:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")[:_FILE_BYTES]
        except OSError:
            continue
        path_text = relative.casefold()
        content_text = content.casefold()
        matched_terms = sorted(term for term in terms if term in path_text or term in content_text)
        if not matched_terms:
            continue
        path_terms = _path_segments(relative)
        path_hits = sorted(term for term in matched_terms if term in path_terms)
        symbols = _symbols_from_content(content)
        symbol_hits = [symbol for symbol in symbols if any(term in symbol.casefold() for term in matched_terms)]
        score = sum(3 for term in matched_terms if term in path_text)
        score += sum(1 for term in matched_terms if term in content_text)
        score += 4 * len(path_hits)
        score += 5 * len(symbol_hits)
        kind = repository_observation_kind(relative)
        if kind in {"test", "prompt", "worker", "explorer_doc"}:
            score += 1
        item: dict[str, object] = {
            "kind": kind,
            "path": relative,
            "score": score,
            "matched_terms": matched_terms[:8],
        }
        if path_hits:
            item["path_term_hits"] = path_hits[:8]
        if symbols:
            item["symbols"] = symbols
        snippets = _line_snippets(content, matched_terms)
        if snippets:
            item["snippets"] = snippets
            item["matches"] = [f"L{snippet['line_start']}: {str(snippet['excerpt'])[:180]}" for snippet in snippets[:4]]
        candidates.append((score, relative, item))
    return _bounded_observations(candidates)


def repository_observation_kind(relative: str) -> str:
    if relative.startswith("tests/") or "/tests/" in relative:
        return "test"
    if "/prompts/" in relative or relative.startswith("prompts/"):
        return "prompt"
    if "/workers/" in relative or relative.startswith("workers/"):
        return "worker"
    if relative.startswith("docs/explorer/"):
        return "explorer_doc"
    if relative.endswith(".schema.json") or "/schemas/" in relative or "/json_schemas/" in relative:
        return "schema"
    if relative.endswith((".json", ".toml", ".yaml", ".yml", ".ini", ".cfg")):
        return "config"
    if relative.endswith((".py", ".js", ".ts", ".tsx", ".jsx")):
        return "source"
    return "path"


def _improvement_paths(root: Path) -> list[Path]:
    base = root / _IMPROVEMENTS_ROOT
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("improvement.md") if _safe_file(root, path))


def _candidate_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if len(paths) >= _SCAN_LIMIT:
            break
        if _safe_file(root, path):
            paths.append(path)
    return paths


def _safe_file(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if any(part.startswith(".") for part in relative.parts):
        return False
    if path.is_symlink() or not path.is_file():
        return False
    if path.suffix.casefold() not in _SUFFIXES:
        return False
    return not any(part in _IGNORED_PARTS for part in relative.parts)


def _relative(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return ""
    raw = PurePath(relative)
    if raw.is_absolute() or ".." in raw.parts:
        return ""
    return relative


def _terms_from_text(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    text = value.casefold()
    terms = set(re.findall(r"[a-z0-9]{4,}", text))
    terms.update(term for term in _SHORT_TERMS if re.search(rf"\b{re.escape(term)}\b", text))
    return terms


def _observation_terms(request: str, profile: Mapping[str, object], related: Sequence[Mapping[str, object]]) -> set[str]:
    values: list[object] = [request, profile.get("summary")]
    values.extend(profile.get("request_parts", []) if isinstance(profile.get("request_parts"), list) else [])
    values.extend(profile.get("evidence_questions", []) if isinstance(profile.get("evidence_questions"), list) else [])
    for item in related:
        values.append(item.get("path"))
        values.append(item.get("summary"))
    terms: set[str] = set()
    for value in values:
        terms.update(_terms_from_text(value))
    return {term for term in terms if term not in _STOP_TERMS}


def _path_segments(relative: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", relative.casefold()))


def _symbols_from_content(content: str) -> list[str]:
    return re.findall(r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", content, re.MULTILINE)[:12]


def _line_snippets(content: str, matched_terms: Sequence[str]) -> list[dict[str, object]]:
    snippets: list[dict[str, object]] = []
    seen_lines: set[int] = set()
    ranked: list[tuple[int, int, str, list[str]]] = []
    lines = content.splitlines()
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.casefold()
        hits = [term for term in matched_terms if term in lowered]
        if not hits:
            continue
        score = len(hits)
        if re.match(r"(?:async\s+def|def|class)\s+[A-Za-z_][A-Za-z0-9_]*", line):
            score += 6
        if re.match(r"(?:from|import)\s+", line):
            score -= 4
        ranked.append((score, line_number, line, hits))
    for _, line_number, line, hits in sorted(ranked, key=lambda item: (-item[0], item[1])):
        context_line = None
        for context_index in range(line_number - 2, 0, -1):
            candidate = lines[context_index - 1].strip()
            if re.match(r"(?:async\s+def|def|class)\s+[A-Za-z_][A-Za-z0-9_]*", candidate):
                context_line = (context_index, candidate)
                break
        if context_line is not None and context_line[0] not in seen_lines:
            seen_lines.add(context_line[0])
            snippets.append(_snippet(context_line[0], context_line[1], matched_terms))
        if line_number not in seen_lines:
            seen_lines.add(line_number)
            snippets.append(_snippet(line_number, line, hits))
        if len(snippets) >= 4:
            break
    return snippets


def _snippet(line_number: int, excerpt: str, matched_terms: Sequence[str]) -> dict[str, object]:
    item: dict[str, object] = {
        "line_start": line_number,
        "line_end": line_number,
        "excerpt": excerpt[:220],
        "matched_terms": list(dict.fromkeys(matched_terms))[:8],
    }
    symbol = re.match(r"(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", excerpt)
    if symbol:
        item["symbol"] = symbol.group(1)
    return item


def _bounded_observations(candidates: Sequence[tuple[int, str, dict[str, object]]]) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    remaining = _OBSERVATION_BYTES
    for _, _, item in sorted(candidates, key=lambda candidate: (-candidate[0], candidate[1])):
        item = dict(item)
        item.setdefault("id", f"RO{len(observations) + 1}")
        encoded = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if len(encoded) > remaining:
            item = {key: item[key] for key in ("id", "kind", "path", "score", "matched_terms") if key in item}
            encoded = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if len(encoded) > remaining:
            continue
        observations.append(item)
        remaining -= len(encoded)
        if len(observations) >= _OBSERVATION_LIMIT:
            break
    return observations


def _improvement_summary(content: str, relative: str) -> str:
    lines = [line.strip() for line in content.replace("\r\n", "\n").splitlines() if line.strip()]
    title = lines[0].lstrip("# ").strip() if lines else relative
    sections = [_section(content, name) for name in ("Problem", "Desired Behavior", "Recommendation", "Findings")]
    return " ".join(part for part in [title, *sections] if part).strip()[:700]


def _section(text: str, name: str) -> str:
    lines = text.replace("\r\n", "\n").splitlines()
    marker = f"## {name}"
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == marker) + 1
    except StopIteration:
        return ""
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return " ".join(line.strip().strip("-*+ ") for line in lines[start:end] if line.strip())


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
