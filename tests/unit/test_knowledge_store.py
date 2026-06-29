from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.models import KnowledgeEntry
from ai_harness.orchestrator import Orchestrator
from ai_harness.stores.knowledge import KnowledgeStore, SQLiteKnowledgeStore


class KnowledgeStoreTests(unittest.TestCase):
    def test_protocol_round_trip_recent_and_escaped_like(self):
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteKnowledgeStore(Path(directory) / "knowledge.db", enable_fts=False) as store:
                self.assertIsInstance(store, KnowledgeStore)
                store.add_entry(KnowledgeEntry("old", "r1", "100% coverage", tags=("python",), created_at="2024-01-01T00:00:00+00:00"))
                store.add_entry(KnowledgeEntry("new", "r2", "new result", created_at="2025-01-01T00:00:00+00:00"))
                self.assertEqual(store.search("100%")[0].id, "old")
                self.assertEqual([entry.id for entry in store.list_recent()], ["new", "old"])

    def test_fts_search_when_available(self):
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteKnowledgeStore(Path(directory) / "knowledge.db") as store:
                if not store.fts_enabled: self.skipTest("SQLite lacks FTS5")
                store.add_entry(KnowledgeEntry("1", "r", "authentication", solutions=("rotate tokens",)))
                self.assertEqual(store.search("tokens")[0].id, "1")

    def test_learning_sections_parse_to_structured_fields(self):
        learning = """# Learning v2
## Title
Offline completion
## Summary
Completed offline.
## Decisions
- Use deterministic gates.
Keep controller ownership.
## Patterns
1. Artifact-driven work.
2. Bounded repair.
## Errors
None.
## Solutions
- Controller validation.
- Structured persistence.
## Keywords
offline, persistence
"""
        sections = Orchestrator.parse_learning_sections(learning)
        self.assertEqual("Offline completion", sections["title"])
        self.assertEqual("Completed offline.", sections["summary"])
        self.assertEqual(("Use deterministic gates.", "Keep controller ownership."), sections["decisions"])
        self.assertEqual(("Artifact-driven work.", "Bounded repair."), sections["patterns"])
        self.assertEqual(("None.",), sections["errors"])
        self.assertEqual(("Controller validation.", "Structured persistence."), sections["solutions"])
        self.assertEqual(("offline, persistence",), sections["keywords"])
    def test_refresh_script_rebuilds_database_from_canonical_learning(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            learning = repository / "docs" / "knowledge-db" / "offline-completion" / "learning.md"
            learning.parent.mkdir(parents=True)
            learning.write_text(
                "# Learning v2\n"
                "## Title\nOffline completion\n"
                "## Summary\nCompleted offline.\n"
                "## Decisions\nUse deterministic gates.\n"
                "## Patterns\nArtifact-driven work.\n"
                "## Errors\nNone.\n"
                "## Solutions\nController validation.\n"
                "## Keywords\noffline, controller\n",
                encoding="utf-8",
            )
            db = repository / ".ai-harness" / "knowledge.db"
            with SQLiteKnowledgeStore(db) as store:
                store.add_entry(KnowledgeEntry("stale", "r", "stale"))

            subprocess.run([sys.executable, str(ROOT / "scripts" / "refresh_knowledge.py"), str(repository)], check=True, capture_output=True, text=True)

            entries = SQLiteKnowledgeStore(db).list_recent()
            self.assertEqual(1, len(entries))
            self.assertEqual("docs/knowledge-db/offline-completion/learning.md", entries[0].id)
            self.assertEqual("canonical", entries[0].run_id)
            self.assertEqual("Completed offline.", entries[0].summary)
