#!/usr/bin/env python3
"""Rebuild .ai-harness/knowledge.db from canonical docs/knowledge-db files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "harness"
sys.path.insert(0, str(SCRIPTS))

from ai_harness.models import KnowledgeEntry  # noqa: E402
from ai_harness.orchestrator.learning_parser import parse_learning_sections  # noqa: E402
from ai_harness.stores.knowledge import SQLiteKnowledgeStore  # noqa: E402


def refresh(repository: Path) -> int:
    repository = repository.resolve()
    db = repository / ".ai-harness" / "knowledge.db"
    if db.exists():
        db.unlink()
    entries = 0
    with SQLiteKnowledgeStore(db) as store:
        for path in sorted((repository / "docs" / "knowledge-db").glob("*/learning.md")):
            relative = str(path.relative_to(repository))
            content = path.read_text(encoding="utf-8")
            sections = parse_learning_sections(content)
            keywords = tuple(sections.get("keywords", ()))
            store.add_entry(KnowledgeEntry(
                relative,
                "canonical",
                str(sections["summary"]),
                decisions=tuple(sections["decisions"]),
                patterns=tuple(sections["patterns"]),
                errors=tuple(sections["errors"]),
                solutions=tuple(sections["solutions"]),
                tags=keywords,
                created_at="1970-01-01T00:00:00+00:00",
            ))
            entries += 1
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", nargs="?", default=".", help="target repository, default: current directory")
    args = parser.parse_args()
    count = refresh(Path(args.repository))
    print(f"refreshed .ai-harness/knowledge.db from {count} canonical learning file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
