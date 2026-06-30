from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.canonical import checksum
from ai_harness.config import HarnessConfig
from ai_harness.orchestrator import Orchestrator
from tests.fixtures.flow import run_with_flow
from tests.fixtures.scripted_provider import ScriptedProvider


EXPLORE_CALLS = [
    "explore_request_understanding",
    "explore_clarification_gate",
    "explore_triage",
    "explore_evidence_plan",
    "explore_evidence_collection",
    "explore_ci_barrier",
    "explore_evidence_normalization",
    "explore_outcome_synthesis",
    "explore_review",
    "knowledge_synthesis",
]


class ExploreBundleDiscoveryTests(unittest.TestCase):
    def test_analysis_choice_runs_unified_explore_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ScriptedProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Investigate draft-improvements/explorer-routing-and-analysis-brief.md",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual("EXPLORE_BUNDLE", result.strategy.strategy)
            self.assertEqual(EXPLORE_CALLS, provider.calls)
            self.assertIn("explore/outcome_bundle.json", result.artifacts)
            self.assertIn("explore/exploration_map.json", result.artifacts)
            self.assertIn("published/explore-handoff.json", result.artifacts)
            self.assertNotIn("explorer/bundle.json", result.artifacts)
            self.assertNotIn("published/explorer.json", result.artifacts)

            exploration_map = json.loads((result.snapshot_path / "explore" / "exploration_map.json").read_text(encoding="utf-8"))
            outcome_bundle = json.loads((result.snapshot_path / "explore" / "outcome_bundle.json").read_text(encoding="utf-8"))
            self.assertEqual(exploration_map, outcome_bundle["exploration_map"])

    def test_related_improvements_are_supplied_to_evidence_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            existing = repository / "docs/explorer/improvements/routing-bundle-output/improvement.md"
            existing.parent.mkdir(parents=True)
            content = (
                "# Improvement: Routing Bundle Output\n"
                "## Status\nProposed\n"
                "## Problem\nRouting bundle output is missing.\n"
                "## Evidence\ndocs/explorer/improvements/routing-bundle-output/improvement.md records the fixture.\n"
                "## Desired Behavior\nPublish routing bundle output.\n"
                "## Implementation Notes\nKeep it focused.\n"
                "## Acceptance Criteria\n- Routing bundle output is published.\n"
            )
            existing.write_text(content, encoding="utf-8")
            provider = ScriptedProvider()

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze routing bundle output improvement",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            inputs = provider.phase_inputs["explore_evidence_collection"][0]
            related = inputs["related_improvements"]
            self.assertTrue(any(item["path"] == "docs/explorer/improvements/routing-bundle-output/improvement.md" for item in related))
            self.assertTrue(any(item.get("checksum") == checksum(content) for item in related))

    def test_repository_observations_are_supplied_to_evidence_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / "ui/console_input.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "def slash_command_mode():\n    return 'console input suggestions'\n",
                encoding="utf-8",
            )
            provider = ScriptedProvider()

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze slash command mode console input suggestions",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            inputs = provider.phase_inputs["explore_evidence_collection"][0]
            observations = json.dumps(inputs["repository_observations"])
            self.assertIn("ui/console_input.py", observations)
            self.assertIn("slash_command_mode", observations)

    def test_referenced_draft_is_scope_input_and_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            draft = repository / "draft-improvements" / "analysis-first-gate.md"
            draft.parent.mkdir()
            original = "# Draft\n\nDraft source material stays unchanged.\n"
            draft.write_text(original, encoding="utf-8")
            provider = ScriptedProvider()

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Investigate draft-improvements/analysis-first-gate.md",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(original, draft.read_text(encoding="utf-8"))
            self.assertIn("explore/outcome_bundle.json", result.artifacts)
            self.assertIn("published/explore-handoff.json", result.artifacts)
            self.assertFalse((repository / "docs/explorer/improvements/analysis-first-gate/improvement.md").exists())

    def test_bug_explorer_uses_normal_code_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ScriptedProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Investigate bug in api.py and add tests",
                "sdd_low",
            )

            self.assertEqual("debug_issue", result.route.intent)
            self.assertEqual("SDD", result.strategy.strategy)
            self.assertNotIn("explorer_artifact", provider.calls)
            self.assertNotIn("published/explorer.json", result.artifacts)


if __name__ == "__main__":
    unittest.main()
