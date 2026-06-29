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
        ANALYSIS_IMPOSSIBLE,
        COMPACT_ROUTING,
        EXISTING,
        INFRA_IMPOSSIBLE,
        DecisionExplorerProvider,
        ExplorerProvider,
        LowValueDecisionProvider,
        NoneOfAboveExplorerProvider,
        SplitBundleProvider,
        bundle_output,
    )
except ImportError:
    from providers import (
        ANALYSIS,
        ANALYSIS_IMPOSSIBLE,
        COMPACT_ROUTING,
        EXISTING,
        INFRA_IMPOSSIBLE,
        DecisionExplorerProvider,
        ExplorerProvider,
        LowValueDecisionProvider,
        NoneOfAboveExplorerProvider,
        SplitBundleProvider,
        bundle_output,
    )


class ExplorerDecisionTests(unittest.TestCase):
    def test_split_bundle_decision_rejects_single_entry_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = SplitBundleProvider(ANALYSIS, decision="split_bundle")
            with self.assertRaisesRegex(Exception, "split_bundle outcome requires a bundle with at least 2 entries"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), provider),
                    "Analyze split-bundle decision with insufficient entries",
                    "explorer",
                )

    def test_split_bundle_decision_accepts_multi_entry_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            output = bundle_output([
                {
                    "id": "existing-routing",
                    "action": "existing_functionality",
                    "artifact_kind": "existing-functionality",
                    "title": "Existing routing behavior",
                    "content": EXISTING,
                },
                {
                    "id": "routing-impl",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Routing bundle output",
                    "path": "docs/explorer/improvements/routing-bundle-output/improvement.md",
                    "content": COMPACT_ROUTING,
                },
            ], "existing-routing")
            provider = SplitBundleProvider(output, decision="split_bundle")
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze routing and manifest behavior for split bundle",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            self.assertIn("explorer/bundle.json", result.artifacts)
            bundle = json.loads((result.snapshot_path / "explorer" / "bundle.json").read_text(encoding="utf-8"))
            self.assertEqual(2, len(bundle["entries"]))
            kinds = [item["artifact_kind"] for item in bundle["entries"]]
            self.assertEqual(["existing-functionality", "improvement"], kinds)
            self.assertIn("split_bundle_rationale", bundle)
            self.assertEqual("The requested artifact spans two separate implementation surfaces.", bundle["split_bundle_rationale"])

    def test_contested_explorer_gate_asks_user_with_scores_then_honors_analysis_choice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ExplorerProvider(ANALYSIS)
            request = (
                "Investigate and create an improvement artifact about deciding "
                "improvement limitation or failure during analysis"
            )
            waiting = Orchestrator(repository, HarnessConfig(provider="local"), provider).run(request)

            self.assertEqual("waiting_for_user", waiting.outcome)
            decision = waiting.control["request"]
            self.assertEqual("SELECTING_STRATEGY", decision["origin_phase"])
            self.assertEqual(8, decision["scores"]["explorer"])
            self.assertGreater(decision["scores"]["sdd_low"], 0)
            self.assertIn("explorer_language+4", decision["score_signals"]["explorer"])
            self.assertIn("explorer", decision["ranked_paths"])
            self.assertEqual([], provider.calls)
            option_ids = {option["id"] for option in decision["options"]}
            self.assertIn("explorer", option_ids)
            self.assertIn("sdd_low", option_ids)
            gate = (repository / ".ai-harness" / "artifacts" / "current" / "explorer_gate.json").read_text(encoding="utf-8")
            self.assertIn('"scores"', gate)

            completed = Orchestrator(repository, HarnessConfig(provider="local"), provider).run(
                request,
                resume_run_id=waiting.run_id,
                decision_answer=json.dumps({
                    "schema_version": 1,
                    "kind": "decision_answer",
                    "decision_id": waiting.control["decision_id"],
                    "answer": "Create the analysis artifact.",
                    "selected_option": "explorer",
                }),
            )

            self.assertEqual("success", completed.outcome)
            self.assertEqual("EXPLORER", completed.strategy.strategy)
            self.assertIn("explorer_artifact", provider.calls)
            self.assertIn("explorer/bundle.json", completed.artifacts)

    def test_explorer_decision_waits_then_resume_completes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = DecisionExplorerProvider(ANALYSIS)
            request = "Investigate draft-improvements/explorer-routing-and-analysis-brief.md"
            route_waiting = Orchestrator(repository, HarnessConfig(provider="local"), provider).run(request)

            self.assertEqual("waiting_for_user", route_waiting.outcome)
            self.assertIn("decisions/D1/request.json", route_waiting.artifacts)
            state = StateStore(repository).load()
            self.assertEqual("SELECTING_STRATEGY", state.current_phase)

            waiting = Orchestrator(repository, HarnessConfig(provider="local"), provider).run(
                request,
                resume_run_id=route_waiting.run_id,
                decision_answer=json.dumps({
                    "schema_version": 1,
                    "kind": "decision_answer",
                    "decision_id": "D1",
                    "answer": "Create the analysis artifact.",
                    "selected_option": "explorer",
                }),
            )

            self.assertEqual("waiting_for_user", waiting.outcome)
            self.assertIn("decisions/D2/request.json", waiting.artifacts)
            state = StateStore(repository).load()
            self.assertEqual("EXPLORER_DECISION", state.current_phase)

            completed = Orchestrator(repository, HarnessConfig(provider="local"), provider).run(
                request,
                resume_run_id=waiting.run_id,
                decision_answer=json.dumps({
                    "schema_version": 1,
                    "kind": "decision_answer",
                    "decision_id": "D2",
                    "answer": "Preserve compatibility.",
                    "selected_option": "preserve",
                }),
            )

            self.assertEqual("success", completed.outcome)
            self.assertIn("explorer/bundle.json", completed.artifacts)
            self.assertGreaterEqual(provider.calls.count("explorer_artifact"), 1)

    def test_value_gate_blocks_low_value_new_improvement_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = LowValueDecisionProvider(ANALYSIS)
            with self.assertRaisesRegex(HarnessError, "explorer value gate requires selected_direction"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), provider),
                    "Analyze strategic explorer value routing",
                    "explorer",
                )

    def test_none_of_above_reruns_discovery_then_publishes_not_worth_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = NoneOfAboveExplorerProvider()
            request = "Analyze strategic explorer directions"
            waiting = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                request,
                "explorer",
            )

            self.assertEqual("waiting_for_user", waiting.outcome)
            assert waiting.control is not None
            completed = Orchestrator(repository, HarnessConfig(provider="local"), provider).run(
                request,
                resume_run_id=waiting.run_id,
                decision_answer=json.dumps({
                    "schema_version": 1,
                    "kind": "decision_answer",
                    "decision_id": waiting.control["decision_id"],
                    "answer": "None of these options target the real value problem.",
                    "selected_option": "none_of_above",
                }),
            )

            self.assertEqual("success", completed.outcome)
            self.assertGreaterEqual(provider.calls.count("explorer_discovery"), 2)
            self.assertGreaterEqual(provider.calls.count("explorer_decision"), 2)
            self.assertTrue(any("none_of_above" in prompt for prompt in provider.discovery_prompts[1:]))
            self.assertIn("explorer/bundle.json", completed.artifacts)

    def test_analysis_impossible_from_explorer_becomes_limitation_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(ANALYSIS_IMPOSSIBLE)),
                "Analyze impossible improvement outcome",
                "explorer",
            )

            self.assertEqual("success", result.outcome)
            self.assertIn("explorer/bundle.json", result.artifacts)
            self.assertNotIn("impossible.json", result.artifacts)
            state = json.loads((result.snapshot_path / "state.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", state["status"])
            bundle = json.loads((result.snapshot_path / "explorer" / "bundle.json").read_text(encoding="utf-8"))
            content = bundle["entries"][0]["content"]
            self.assertIn("# Limitation v1", content)
            self.assertIn("contradicts a repository invariant", content)

    def test_infrastructure_impossible_from_explorer_is_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            with self.assertRaisesRegex(Exception, "infrastructure"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(INFRA_IMPOSSIBLE)),
                    "Analyze improvement when worker cannot inspect repository",
                    "explorer",
                )

            state = StateStore(repository).load()
            self.assertEqual("failed", state.status.value)
            self.assertEqual("FAILED", state.current_phase)
            self.assertNotIn("impossible.json", state.artifacts)


if __name__ == "__main__":
    unittest.main()
