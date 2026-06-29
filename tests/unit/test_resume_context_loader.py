from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_harness.models import Complexity, Mode, RunState, Strategy
from ai_harness.orchestrator.resume_context_loader import ResumeContextLoader
from ai_harness.stores.artifact import ArtifactStore


def active_state(strategy: Strategy = Strategy.SDD, complexity: Complexity = Complexity.MEDIUM) -> RunState:
    return RunState(
        "run-1",
        "Implement a resumable decision flow",
        "SELECTING_STRATEGY",
        strategy,
        Mode.CODE,
        "modify_code",
        complexity,
        "local",
    )


class ResumeContextLoaderTests(unittest.TestCase):
    def test_loads_pending_strategy_from_route_when_strategy_artifact_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifacts = ArtifactStore(Path(directory))
            artifacts.write_json(
                "route.json",
                {
                    "mode": "code",
                    "intent": "modify_code",
                    "confidence": 0.82,
                    "source": "needs_user",
                    "matched_signals": ["ambiguous"],
                    "pending_strategy": {
                        "strategy": "SDD",
                        "complexity": "MEDIUM",
                        "score": 7,
                        "reason": "Needs a full workflow",
                        "matched_signals": ["workflow_contract"],
                        "recommended_strategy": "SDD",
                        "recommended_complexity": "MEDIUM",
                        "confirmation_required": True,
                        "prompted": True,
                        "overridden": False,
                        "selection_source": "prompt_accept",
                        "override_text": "full",
                    },
                },
            )

            context = ResumeContextLoader(artifacts).load(active_state())

            self.assertEqual("code", context.route.mode)
            self.assertEqual("modify_code", context.route.intent)
            self.assertEqual(0.82, context.route.confidence)
            self.assertEqual(("ambiguous",), context.route.matched_signals)
            self.assertEqual("SDD", context.strategy.strategy)
            self.assertEqual("MEDIUM", context.strategy.complexity)
            self.assertEqual(7, context.strategy.score)
            self.assertEqual(("workflow_contract",), context.strategy.matched_signals)
            self.assertEqual("SDD", context.strategy.recommended_strategy)
            self.assertEqual("MEDIUM", context.strategy.recommended_complexity)
            self.assertTrue(context.strategy.confirmation_required)
            self.assertTrue(context.strategy.prompted)
            self.assertFalse(context.strategy.overridden)
            self.assertEqual("prompt_accept", context.strategy.selection_source)
            self.assertEqual("full", context.strategy.override_text)

    def test_loads_explorer_gate_with_typed_scores_and_signal_tuples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifacts = ArtifactStore(Path(directory))
            artifacts.write_json(
                "explorer_gate.json",
                {
                    "path": "sdd_high",
                    "reason": "Persisted gate",
                    "matched_signals": ["artifact"],
                    "required_artifact": "docs/explorer/improvements/item/improvement.md",
                    "supplied_artifact": "docs/explorer/improvements/item/improvement.md",
                    "source": "user",
                    "classifier_version": 2,
                    "scores": {"explorer": "5", "sdd_high": 9},
                    "score_signals": {
                        "explorer": ["explorer_language+4"],
                        "sdd_high": ["artifact_supplied+5"],
                    },
                },
            )

            context = ResumeContextLoader(artifacts).load(active_state(Strategy.SDD, Complexity.HIGH))

            assert context.explorer_gate is not None
            self.assertEqual("sdd_high", context.explorer_gate.path)
            self.assertEqual("Persisted gate", context.explorer_gate.reason)
            self.assertEqual(("artifact",), context.explorer_gate.matched_signals)
            self.assertEqual("user", context.explorer_gate.source)
            self.assertEqual(2, context.explorer_gate.classifier_version)
            self.assertEqual({"explorer": 5, "sdd_high": 9}, context.explorer_gate.scores)
            self.assertEqual(
                {
                    "explorer": ("explorer_language+4",),
                    "sdd_high": ("artifact_supplied+5",),
                },
                context.explorer_gate.score_signals,
            )


if __name__ == "__main__":
    unittest.main()
