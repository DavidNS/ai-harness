from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "harness"
sys.path.insert(0, str(SCRIPTS))

from ai_harness.explorer_gate import classify_explorer_gate


class ExplorerGateTests(unittest.TestCase):
    def test_mixed_improvement_explorer_asks_user_with_analysis_scores(self) -> None:
        decision = classify_explorer_gate(
            "investigate this repo and create an improvement that allows safer routing"
        )
        self.assertEqual("ask_user", decision.path)
        self.assertIn("explorer_language", decision.matched_signals)
        self.assertGreater(decision.scores["explore_bundle"], 0)

    def test_analysis_implementation_conflict_asks_user_and_exposes_scores(self) -> None:
        decision = classify_explorer_gate(
            "investigate and create an improvement artifact about deciding improvement limitation or failure"
        )

        self.assertEqual("ask_user", decision.path)
        self.assertGreater(decision.scores["explore_bundle"], 0)
        self.assertGreater(decision.scores["sdd"], 0)
        payload = decision.to_dict()
        self.assertIn("scores", payload)
        self.assertIn("score_signals", payload)
        self.assertIn("ranked_paths", payload)

    def test_bugfix_and_trivial_edits_ask_user_with_easy_scores(self) -> None:
        bug = classify_explorer_gate("Fix traceback in api.py with this reproduction")
        typo = classify_explorer_gate("Fix a typo in README.md")

        self.assertEqual("ask_user", bug.path)
        self.assertEqual("ask_user", typo.path)
        self.assertGreater(bug.scores["sdd"], 0)
        self.assertGreater(typo.scores["sdd"], 0)

    def test_workflow_change_requires_full_implementation_artifact(self) -> None:
        decision = classify_explorer_gate("Update orchestrator routing and persisted artifact state handling")
        self.assertEqual("ask_user", decision.path)
        self.assertFalse(decision.explorer_artifact_required)
        self.assertGreater(decision.scores["sdd"], 0)
        self.assertIsNone(decision.required_artifact)

    def test_existing_analysis_artifact_allows_full_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs" / "explorer" / "improvements" / "analysis-first-gate" / "improvement.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("# Improvement Explorer v1\n", encoding="utf-8")

            decision = classify_explorer_gate(
                "Implement docs/explorer/improvements/analysis-first-gate/improvement.md",
                repository=repository,
            )

            self.assertEqual("ask_user", decision.path)
            self.assertFalse(decision.explorer_artifact_required)
            self.assertGreater(decision.scores["sdd"], 0)
            self.assertEqual("docs/explorer/improvements/analysis-first-gate/improvement.md", decision.supplied_artifact)


    def test_compact_analysis_artifact_allows_full_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs" / "explorer" / "improvements" / "compact-routing" / "improvement.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("# Improvement: Compact Routing\n## Status\nProposed\n", encoding="utf-8")

            decision = classify_explorer_gate(
                "Implement docs/explorer/improvements/compact-routing/improvement.md",
                repository=repository,
            )

            self.assertEqual("ask_user", decision.path)
            self.assertFalse(decision.explorer_artifact_required)
            self.assertEqual("docs/explorer/improvements/compact-routing/improvement.md", decision.supplied_artifact)


    def test_nested_analysis_artifact_allows_full_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs" / "explorer" / "improvements" / "quality" / "layered-routing" / "improvement.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("# Improvement: Layered Routing\n## Status\nProposed\n", encoding="utf-8")

            decision = classify_explorer_gate(
                "Implement docs/explorer/improvements/quality/layered-routing/improvement.md",
                repository=repository,
            )

            self.assertEqual("ask_user", decision.path)
            self.assertEqual("docs/explorer/improvements/quality/layered-routing/improvement.md", decision.supplied_artifact)

    def test_analysis_artifact_takes_precedence_over_bug_terms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs" / "explorer" / "improvements" / "fix-crash" / "improvement.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("# Improvement Explorer v1\n## Problem\nP\n", encoding="utf-8")

            decision = classify_explorer_gate(
                "Implement docs/explorer/improvements/fix-crash/improvement.md",
                repository=repository,
            )

            self.assertEqual("ask_user", decision.path)
            self.assertEqual("docs/explorer/improvements/fix-crash/improvement.md", decision.supplied_artifact)

    def test_invalid_analysis_artifact_path_does_not_authorize_full_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            limitation = repository / "docs" / "explorer" / "limitations" / "bad" / "limitation.md"
            limitation.parent.mkdir(parents=True)
            limitation.write_text("# Improvement Explorer v1\n", encoding="utf-8")
            malformed = repository / "docs" / "explorer" / "improvements" / "bad" / "improvement.md"
            malformed.parent.mkdir(parents=True, exist_ok=True)
            malformed.write_text("# Limitation v1\n", encoding="utf-8")

            traversal = classify_explorer_gate(
                "Implement docs/explorer/improvements/../limitations/bad/improvement.md",
                repository=repository,
            )
            bad_markdown = classify_explorer_gate(
                "Implement docs/explorer/improvements/bad/improvement.md",
                repository=repository,
            )

            self.assertNotEqual(("ask_user", "docs/explorer/improvements/../limitations/bad/improvement.md"), (traversal.path, traversal.supplied_artifact))
            self.assertIsNone(traversal.supplied_artifact)
            self.assertNotEqual(("ask_user", "docs/explorer/improvements/bad/improvement.md"), (bad_markdown.path, bad_markdown.supplied_artifact))
            self.assertIsNone(bad_markdown.supplied_artifact)

    def test_draft_improvement_is_analysis_input_not_entry_artifact(self) -> None:
        decision = classify_explorer_gate("Implement draft-improvements/analysis-first-gate.md")
        self.assertEqual("ask_user", decision.path)
        self.assertIsNone(decision.supplied_artifact)
        self.assertGreater(decision.scores["explore_bundle"], 0)


if __name__ == "__main__":
    unittest.main()
