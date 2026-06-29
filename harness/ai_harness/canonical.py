"""Canonical, git-visible project knowledge documents."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path, PurePath
from typing import Mapping

from .errors import ArtifactError

_EXPLORER_DOCS = {
    "improvement": ("docs/explorer/improvements", "improvement.md"),
    "limitation": ("docs/explorer/limitations", "limitation.md"),
    "bullshit": ("docs/explorer/probably-a-bullshit", "bullshit.md"),
}
_KNOWLEDGE_ROOT = "docs/knowledge-db"
_IMPROVEMENTS_ROOT = "docs/explorer/improvements"
_REORGANIZE_KNOWLEDGE_PATH = "docs/explorer/improvements/reorganize-knowledge-db/improvement.md"


def slugify(value: str, *, fallback: str = "knowledge") -> str:
    text = value.casefold().replace(".md", "")
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug[:80].strip("-") or fallback


def checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class CanonicalDocs:
    def __init__(self, target_repository: Path) -> None:
        self.root = Path(target_repository).resolve()

    def _path(self, relative: str) -> Path:
        raw = PurePath(relative)
        if not relative or raw.is_absolute() or ".." in raw.parts:
            raise ArtifactError("canonical document path must be relative and contained")
        candidate = self.root.joinpath(*raw.parts)
        parent = candidate.parent.resolve()
        if not parent.is_relative_to(self.root):
            raise ArtifactError("canonical document path escapes repository")
        if candidate.exists() and not candidate.resolve().is_relative_to(self.root):
            raise ArtifactError("canonical document symlink escapes repository")
        return candidate

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    def write(self, relative: str, content: str) -> dict[str, str]:
        path = self._path(relative)
        self._atomic_write(path, content)
        return {"path": relative, "checksum": checksum(content)}

    def read(self, relative: str) -> str:
        return self._path(relative).read_text(encoding="utf-8")

    def exists(self, relative: str) -> bool:
        return self._path(relative).is_file()

    def analysis_path(self, kind: str, slug: str) -> str:
        base, filename = _EXPLORER_DOCS[kind]
        return f"{base}/{slug}/{filename}"

    def knowledge_path(self, slug: str) -> str:
        return f"{_KNOWLEDGE_ROOT}/{slug}/learning.md"

    def list_knowledge(self) -> list[str]:
        root = self._path(_KNOWLEDGE_ROOT)
        if not root.exists():
            return []
        return sorted(str(path.relative_to(self.root)) for path in root.glob("*/learning.md") if path.is_file())

    def list_improvements(self) -> list[str]:
        root = self._path(_IMPROVEMENTS_ROOT)
        if not root.exists():
            return []
        return sorted(
            str(path.relative_to(self.root))
            for path in root.rglob("improvement.md")
            if path.is_file() and path.parent != root
        )

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]{4,}", text.casefold()))

    def improvement_summary(self, relative: str) -> str:
        content = self.read(relative)
        lines = [line.strip() for line in content.replace("\r\n", "\n").splitlines() if line.strip()]
        title = lines[0].lstrip("# ").strip() if lines else relative
        details = [
            self._section(content, "Problem"),
            self._section(content, "Desired Behavior"),
            self._section(content, "Recommendation"),
            self._section(content, "Findings"),
        ]
        summary = " ".join(part for part in [title, *details] if part).strip()
        return summary[:700]

    def related_improvements(self, query: str, *, limit: int = 5) -> list[dict[str, str | int]]:
        query_terms = self._tokens(query)
        if not query_terms or limit <= 0:
            return []
        candidates: list[tuple[int, str, str, str]] = []
        for path in self.list_improvements():
            content = self.read(path)
            summary = self.improvement_summary(path)
            path_terms = self._tokens(path)
            content_terms = self._tokens(content)
            score = sum(3 for term in query_terms if term in path_terms)
            score += sum(1 for term in query_terms if term in content_terms)
            if score > 0:
                candidates.append((score, path, summary, checksum(content)))
        ranked = sorted(candidates, key=lambda item: (-item[0], item[1]))[:limit]
        return [
            {"path": path, "summary": summary, "checksum": digest, "score": score}
            for score, path, summary, digest in ranked
        ]

    def require_improvement_path(self, relative: str) -> None:
        raw = PurePath(relative)
        if raw.is_absolute() or ".." in raw.parts:
            raise ArtifactError("improvement path must be relative and contained")
        allowed_roots = (("docs", "explorer", "improvements"),)
        if len(raw.parts) < 5 or raw.parts[-1] != "improvement.md" or raw.parts[:3] not in allowed_roots:
            raise ArtifactError("updates must target docs/explorer/improvements/<slug>/.../improvement.md")
        path = self._path(relative)
        roots = [self._path("/".join(root)).resolve() for root in allowed_roots]
        if not any(path.parent.resolve().is_relative_to(root) for root in roots):
            raise ArtifactError("improvement path escapes improvement roots")

    def update_improvement(self, relative: str, content: str, *, expected_checksum: str) -> dict[str, str]:
        self.require_improvement_path(relative)
        if not self.exists(relative):
            raise ArtifactError("cannot update missing improvement artifact")
        old_content = self.read(relative)
        old_checksum = checksum(old_content)
        if old_checksum != expected_checksum:
            raise ArtifactError("canonical update checksum mismatch")
        published = self.write(relative, content)
        return {"path": relative, "old_checksum": old_checksum, "checksum": published["checksum"]}

    @staticmethod
    def _section(text: str, name: str) -> str:
        lines = text.replace("\r\n", "\n").splitlines()
        marker = f"## {name}"
        try:
            start = next(index for index, line in enumerate(lines) if line.strip() == marker) + 1
        except StopIteration:
            return ""
        end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
        return " ".join(line.strip().strip("-*+ ") for line in lines[start:end] if line.strip())

    def write_knowledge_index(self, knowledge_entries: Mapping[str, Mapping[str, object]] | None = None) -> None:
        entries: dict[str, Mapping[str, object]] = {}
        for path in self.list_knowledge():
            content = self.read(path)
            entries[path] = {
                "title": self._section(content, "Title"),
                "keywords": tuple(item.strip() for item in self._section(content, "Keywords").split(",") if item.strip()),
                "summary": self._section(content, "Summary"),
            }
        entries.update(knowledge_entries or {})
        knowledge_lines = [
            "# Knowledge DB",
            "",
            "| Path | Title | Keywords | Summary |",
            "| --- | --- | --- | --- |",
        ]
        for path, entry in sorted(entries.items()):
            title = str(entry.get("title", ""))
            keywords = ", ".join(str(item) for item in entry.get("keywords", ()))
            summary = str(entry.get("summary", "")).replace("\n", " ")
            knowledge_lines.append(f"| `{path}` | {title} | {keywords} | {summary} |")
        self.write(f"{_KNOWLEDGE_ROOT}/README.md", "\n".join(knowledge_lines) + "\n")

    def write_analysis_index(self) -> None:
        return None

    def write_indexes(self, knowledge_entries: Mapping[str, Mapping[str, object]] | None = None) -> None:
        self.write_knowledge_index(knowledge_entries)

    def similar_knowledge(self, sections: Mapping[str, object], *, exclude: str | None = None) -> list[str]:
        terms = set()
        for key in ("title", "summary"):
            value = str(sections.get(key, "")).strip()
            terms.update(token for token in re.findall(r"[a-z0-9]{4,}", value.casefold()))
        for key in ("keywords", "decisions", "patterns", "solutions"):
            for item in sections.get(key, ()) or ():
                terms.update(token for token in re.findall(r"[a-z0-9]{4,}", str(item).casefold()))
        candidates: list[tuple[int, str]] = []
        for path in self.list_knowledge():
            if path == exclude:
                continue
            text = self.read(path).casefold()
            score = sum(1 for term in terms if term in text)
            if score >= 3:
                candidates.append((score, path))
        return [path for _, path in sorted(candidates, key=lambda item: (-item[0], item[1]))[:5]]

    def ensure_reorganization_improvement(self, duplicates: list[str], new_path: str) -> dict[str, str]:
        if self.exists(_REORGANIZE_KNOWLEDGE_PATH):
            return {"path": _REORGANIZE_KNOWLEDGE_PATH, "checksum": checksum(self.read(_REORGANIZE_KNOWLEDGE_PATH))}
        duplicate_lines = "\n".join(f"- `{path}`" for path in duplicates) or "- None recorded."
        content = (
            "# Improvement: Reorganize Knowledge DB\n"
            "## Status\n"
            "Proposed\n"
            "## Problem\n"
            "Knowledge entries may contain overlapping or duplicate concepts.\n"
            "## Evidence\n"
            f"The harness detected possible duplicate knowledge while publishing `{new_path}`.\n"
            f"{duplicate_lines}\n"
            "## Desired Behavior\n"
            "A future curation workflow can merge, split, supersede, or relink knowledge entries explicitly.\n"
            "## Implementation Notes\n"
            "Do not merge entries automatically; require an explicit review mechanism before rewriting canonical knowledge files.\n"
            "## Acceptance Criteria\n"
            "- Duplicate candidates are listed before any merge.\n"
            "- A human-approved workflow controls canonical knowledge rewrites.\n"
        )
        return self.write(_REORGANIZE_KNOWLEDGE_PATH, content)
