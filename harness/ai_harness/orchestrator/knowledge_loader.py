"""KnowledgeLoader — git-backed knowledge cache maintenance.

Single responsibility: check cache staleness against the upstream branch, rebuild
from canonical docs under docs/knowledge-db/, and return the top-N entries for
the current run's user input.

Previously the knowledge-cache cluster on AnalysisQualityMixin.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..models import KnowledgeEntry
from ..stores.knowledge import KnowledgeStore, SQLiteKnowledgeStore
from ..stores.state import StateStore
from .learning_parser import parse_learning_sections as _parse_learning_sections


class KnowledgeLoader:
    """Manages knowledge cache freshness and returns entries for a run.

    Injected deps keep this class free of RunContext coupling; warnings are
    mutated in-place (same contract as LearningService).
    """

    def __init__(
        self,
        target: Path,
        knowledge: KnowledgeStore,
        warnings: list[str],
        state: StateStore,
    ) -> None:
        self._target = target
        self._knowledge = knowledge
        self._warnings = warnings
        self._state = state

    def load(self) -> list[KnowledgeEntry]:
        """Check staleness, rebuild canonical cache, return top entries."""
        self._warn_if_knowledge_cache_stale()
        self._refresh_knowledge_cache_from_canonical()
        try:
            return self._knowledge.search(self._state.load().user_input, 5)
        except Exception:
            self._warnings.append("Knowledge loading failed; prior context was omitted")
            return []

    def _git_command(self, args: list[str], *, context: str) -> str | None:
        try:
            completed = subprocess.run(
                ["git", "-C", str(self._target), *args],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self._warnings.append(f"Knowledge freshness check skipped; git is unavailable during {context}.")
            return None
        except Exception as exc:
            self._warnings.append(f"Knowledge freshness check skipped during {context}: {exc}")
            return None
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout).strip()
            self._warnings.append(
                f"Knowledge freshness check skipped during {context}: "
                f"{details or 'repository state could not be determined'}"
            )
            return None
        return completed.stdout.strip()

    def _knowledge_default_remote_branch(self) -> str | None:
        output = self._git_command(["remote", "show", "origin"], context="default-branch detection")
        if not output:
            return None
        match = re.search(r"^\s*HEAD branch:\s*([^\s]+)$", output, re.MULTILINE)
        if not match:
            return None
        branch = match.group(1).strip()
        return f"origin/{branch}" if branch else None

    def _warn_if_knowledge_cache_stale(self) -> None:
        if not (self._target / ".git").is_dir():
            return
        current = self._git_command(["rev-parse", "--abbrev-ref", "HEAD"], context="current-branch lookup")
        if not current:
            return
        if current == "HEAD":
            self._warnings.append("Knowledge freshness is unknown for detached HEAD; staleness check skipped.")
            return

        upstream = self._git_command(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            context="upstream branch lookup",
        )
        if not upstream:
            upstream = self._knowledge_default_remote_branch()

        if not upstream:
            self._warnings.append(
                "Knowledge freshness could not be verified because no upstream or default branch is available."
            )
            return

        counts = self._git_command(
            ["rev-list", "--left-right", "--count", f"{upstream}...{current}"],
            context="branch staleness comparison",
        )
        if not counts:
            return
        parts = counts.split()
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            self._warnings.append("Knowledge freshness check returned an unparseable branch comparison result.")
            return
        behind, ahead = map(int, parts[:2])
        if behind > 0:
            self._warnings.append(
                f"Knowledge cache may be stale; current branch {current} is behind {upstream} by {behind} commit(s)."
            )

    def _refresh_knowledge_cache_from_canonical(self) -> None:
        if not isinstance(self._knowledge, SQLiteKnowledgeStore):
            self._warnings.append(
                "Knowledge cache refresh skipped; this knowledge store does not support rebuild from canonical docs."
            )
            return

        root = self._target / "docs" / "knowledge-db"
        entries_path = sorted(root.glob("*/learning.md")) if root.exists() else []
        try:
            self._knowledge.clear()
        except Exception as exc:
            self._warnings.append(f"Knowledge cache refresh failed; prior context was omitted: {exc}")
            return

        for candidate in entries_path:
            try:
                if not candidate.is_file():
                    continue
                relative = str(candidate.relative_to(self._target))
                sections = _parse_learning_sections(candidate.read_text(encoding="utf-8"))
                if not sections:
                    continue
                self._knowledge.add_entry(KnowledgeEntry(
                    relative,
                    "canonical",
                    str(sections["summary"]),
                    decisions=tuple(sections["decisions"]),
                    patterns=tuple(sections["patterns"]),
                    errors=tuple(sections["errors"]),
                    solutions=tuple(sections["solutions"]),
                    tags=tuple(sections["keywords"]),
                    created_at="1970-01-01T00:00:00+00:00",
                ))
            except Exception as exc:
                self._warnings.append(
                    f"Knowledge cache refresh skipped malformed canonical entry {candidate.name}: {exc}"
                )
