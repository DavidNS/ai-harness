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
from ai_harness.errors import HarnessError
from ai_harness.orchestrator import Orchestrator
from ai_harness.stores.state import StateStore
from tests.fixtures.flow import run_with_flow
from tests.fixtures.scripted_provider import ScriptedProvider

try:
    from .providers import (
        ANALYSIS,
        COMPACT_ROUTING,
        DiscoveryRepairProvider,
        FindingStyleObservationProvider,
        IntakeDrivenObservationProvider,
        ExplorerProvider,
        bundle_output,
    )
except ImportError:
    from providers import (
        ANALYSIS,
        COMPACT_ROUTING,
        DiscoveryRepairProvider,
        FindingStyleObservationProvider,
        IntakeDrivenObservationProvider,
        ExplorerProvider,
        bundle_output,
    )


class ExplorerDiscoveryTests(unittest.TestCase):
    def test_explorer_discovery_contract_failure_is_repaired_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = DiscoveryRepairProvider()

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Investigate draft-improvements/explorer-routing-and-analysis-brief.md",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(2, provider.calls.count("explorer_discovery"))
            self.assertIn('"repair"', provider.discovery_prompts[1])
            self.assertIn("critic_findings severity is invalid", provider.discovery_prompts[1])
            self.assertIn("explorer/bundle.json", result.artifacts)

    def test_repository_observations_are_supplied_to_explorer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / "harness/ai_harness/orchestrator.py"
            source.parent.mkdir(parents=True)
            source.write_text("def explorer_quality_gate():\n    return 'quality gate'\n", encoding="utf-8")
            provider = ExplorerProvider(bundle_output([{
                "id": "observed",
                "action": "no-op",
                "artifact_kind": "improvement",
                "title": "Observed quality gate",
                "reason": "This test only verifies prompt observations.",
            }], "observed"))

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze explorer quality gate observations",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            prompt = provider.explorer_prompts[0]
            self.assertIn('"repository_observations"', prompt)
            self.assertIn("harness/ai_harness/orchestrator.py", prompt)
            self.assertIn("explorer_quality_gate", prompt)


    def test_runtime_context_is_supplied_to_explorer_workers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = IntakeDrivenObservationProvider(bundle_output([{
                "id": "runtime",
                "action": "no-op",
                "artifact_kind": "improvement",
                "title": "Runtime context",
                "reason": "This test only verifies prompt runtime context.",
            }], "runtime"))

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze runtime context evidence",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            prompt = provider.discovery_prompts[0]
            self.assertIn('"runtime_context"', prompt)
            self.assertIn('"git"', prompt)
            self.assertIn('"ci_signals"', prompt)

    def test_repository_observations_use_intake_claim_terms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / "ui/console_input.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "from console_helpers import shared\n\n"
                "def slash_command_mode():\n"
                "    return 'console input suggestions'\n",
                encoding="utf-8",
            )
            test_path = repository / "tests/test_console_input.py"
            test_path.parent.mkdir(parents=True)
            test_path.write_text("def test_slash_command_mode():\n    assert True\n", encoding="utf-8")
            distractor = repository / "docs/notes/console-input-suggestions.md"
            distractor.parent.mkdir(parents=True)
            distractor.write_text(
                "# Console Input Suggestions\n\n"
                "This note repeats console input command suggestions terms but is not source or test evidence.\n",
                encoding="utf-8",
            )
            provider = IntakeDrivenObservationProvider(bundle_output([{
                "id": "observed",
                "action": "no-op",
                "artifact_kind": "improvement",
                "title": "Observed quality gate",
                "reason": "This test only verifies prompt observations.",
            }], "observed"))

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze command UX",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            prompt = provider.discovery_prompts[0]
            self.assertIn("ui/console_input.py", prompt)
            self.assertIn("tests/test_console_input.py", prompt)
            self.assertIn("docs/notes/console-input-suggestions.md", prompt)
            self.assertLess(prompt.index("ui/console_input.py"), prompt.index("docs/notes/console-input-suggestions.md"))
            self.assertLess(prompt.index("tests/test_console_input.py"), prompt.index("docs/notes/console-input-suggestions.md"))
            self.assertIn('"symbols"', prompt)
            self.assertIn("slash_command_mode", prompt)
            self.assertIn("L3: def slash_command_mode():", prompt)

    def test_repository_observations_with_finding_shape_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / "harness/ai_harness/orchestrator.py"
            source.parent.mkdir(parents=True)
            source.write_text("def explorer_quality_gate():\n    return 'quality gate'\n", encoding="utf-8")
            provider = FindingStyleObservationProvider(COMPACT_ROUTING, [{
                "finding": {
                    "path": "docs/explorer/improvements/routing-bundle-output/improvement.md",
                    "evidence": ["Existing quality gate helper supports compact improvement checks."],
                },
                "symbols": ["explorer_quality_gate"],
            }])

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze routing bundle output with mixed-format observations",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            artifact = Path(manifest["artifacts"][0]["suggested_path"])
            self.assertFalse((repository / artifact).exists())
            self.assertIn("explorer_distill", provider.calls)
            self.assertIn("knowledge_proposal", manifest["artifacts"][0])

    def test_related_nested_existing_improvements_are_supplied_to_explorer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            existing = repository / "docs/explorer/improvements/improvement-generation-quality/layered-canonical-improvements/improvement.md"
            existing.parent.mkdir(parents=True)
            content = "# Improvement: Layered Canonical Improvements\n## Status\nProposed\n## Problem\nNested improvements are not discovered.\n## Evidence\ndocs/explorer/improvements/improvement-generation-quality/layered-canonical-improvements/improvement.md records the fixture.\n## Desired Behavior\nDiscover nested improvements.\n## Implementation Notes\nUse recursive canonical discovery.\n## Acceptance Criteria\n- Nested improvements are discovered.\n"
            existing.write_text(content, encoding="utf-8")
            provider = ExplorerProvider(bundle_output([{
                "id": "duplicate",
                "action": "no-op",
                "artifact_kind": "improvement",
                "title": "Layered canonical improvements already exists",
                "path": "docs/explorer/improvements/improvement-generation-quality/layered-canonical-improvements/improvement.md",
                "reason": "Existing related improvement covers this request.",
            }], "duplicate"))

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze layered canonical improvements",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            prompt = provider.explorer_prompts[0]
            self.assertIn("docs/explorer/improvements/improvement-generation-quality/layered-canonical-improvements/improvement.md", prompt)
            self.assertIn(checksum(content), prompt)

    def test_related_existing_improvements_are_supplied_to_explorer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            existing = repository / "docs/explorer/improvements/routing-bundle-output/improvement.md"
            existing.parent.mkdir(parents=True)
            existing.write_text(COMPACT_ROUTING, encoding="utf-8")
            provider = ExplorerProvider(bundle_output([{
                "id": "duplicate",
                "action": "no-op",
                "artifact_kind": "improvement",
                "title": "Routing bundle output already exists",
                "path": "docs/explorer/improvements/routing-bundle-output/improvement.md",
                "reason": "Existing related improvement covers this request.",
            }], "duplicate"))

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze routing bundle output improvement",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            self.assertTrue(provider.explorer_prompts)
            prompt = provider.explorer_prompts[0]
            self.assertIn('"related_improvements"', prompt)
            self.assertIn("docs/explorer/improvements/routing-bundle-output/improvement.md", prompt)
            self.assertIn(checksum(COMPACT_ROUTING), prompt)
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            self.assertEqual("no-op", manifest["artifacts"][0]["action"])

    def test_referenced_draft_is_explorer_input_and_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            draft = repository / "draft-improvements" / "analysis-first-gate.md"
            draft.parent.mkdir()
            original = "# Draft\n\nDraft source material stays unchanged.\n"
            draft.write_text(original, encoding="utf-8")
            provider = ExplorerProvider(ANALYSIS)

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Investigate draft-improvements/analysis-first-gate.md",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(original, draft.read_text(encoding="utf-8"))
            self.assertTrue(provider.explorer_prompts)
            self.assertIn("Draft source material stays unchanged.", provider.explorer_prompts[0])
            self.assertIn("explorer/bundle.json", result.artifacts)
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
            self.assertNotEqual("EXPLORER", result.strategy.strategy)
            self.assertNotIn("explorer", provider.calls)
            self.assertFalse(any(name.startswith("published/explorer") for name in result.artifacts))


if __name__ == "__main__":
    unittest.main()
