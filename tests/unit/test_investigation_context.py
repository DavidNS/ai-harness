from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.errors import HarnessError
from ai_harness.orchestrator.explorer_context import (
    ExplorerContext,
    ExplorerExtractionContext,
)


class ExplorerContextTests(unittest.TestCase):
    def test_from_discovery_copies_expected_fields(self) -> None:
        discovery = {
            "related_improvements": [{"path": "docs/explorer/improvements/example/improvement.md"}],
            "repository_observations": [{"path": "harness/ai_harness/orchestrator/explorer_flow.py"}],
            "ignored": "value",
        }

        context = ExplorerContext.from_discovery(discovery)

        self.assertEqual(discovery["related_improvements"], context.related_improvements)
        self.assertEqual(discovery["repository_observations"], context.repository_observations)
        self.assertIsNot(discovery["related_improvements"], context.related_improvements)
        self.assertIsNot(discovery["repository_observations"], context.repository_observations)

    def test_from_discovery_defaults_missing_fields_to_empty_lists(self) -> None:
        context = ExplorerContext.from_discovery({})

        self.assertEqual([], context.related_improvements)
        self.assertEqual([], context.repository_observations)

    def test_from_discovery_rejects_malformed_lists(self) -> None:
        with self.assertRaises(HarnessError) as exc:
            ExplorerContext.from_discovery({"related_improvements": {}, "repository_observations": []})

        self.assertEqual("explorer discovery context is malformed", str(exc.exception))


class ExplorerExtractionContextTests(unittest.TestCase):
    def _context(self) -> ExplorerExtractionContext:
        return ExplorerExtractionContext(
            entry_id="improvement-1",
            artifact_kind="improvement",
            learning="# Learning v2",
            entry_content="# Improvement",
            intake={"phase": "intake"},
            discovery={"phase": "discovery"},
            decision={"phase": "decision"},
            review="APPROVE",
            related_improvements=[
                {"path": "docs/explorer/improvements/example/improvement.md"}
            ],
            repository_observations=[
                {"path": "harness/ai_harness/orchestrator/explorer_flow.py"}
            ],
            evidence_sources_checked=["repository_evidence"],
        )

    def test_synthesis_context_preserves_public_keys(self) -> None:
        payload = self._context().synthesis_context()

        self.assertEqual(
            {
                "entry_id",
                "artifact_kind",
                "learning",
                "entry_content",
                "intake",
                "discovery",
                "decision",
                "review",
                "related_improvements",
                "repository_observations",
                "evidence_sources_checked",
            },
            set(payload),
        )
        self.assertEqual("improvement-1", payload["entry_id"])
        self.assertEqual(["repository_evidence"], payload["evidence_sources_checked"])

    def test_context_payloads_copy_mutable_collections(self) -> None:
        context = self._context()
        synthesis = context.synthesis_context()
        distill = context.distill_inputs("Investigate it")

        self.assertIsNot(context.related_improvements, synthesis["related_improvements"])
        self.assertIsNot(context.repository_observations, synthesis["repository_observations"])
        self.assertIsNot(context.related_improvements, distill["related_improvements"])
        self.assertIsNot(context.repository_observations, distill["repository_observations"])

    def test_distill_inputs_use_existing_prompt_shape(self) -> None:
        payload = self._context().distill_inputs("Investigate it")

        self.assertEqual(
            {
                "request",
                "artifact_candidate",
                "decision",
                "discovery",
                "review",
                "related_improvements",
                "repository_observations",
            },
            set(payload),
        )
        self.assertEqual("Investigate it", payload["request"])
        self.assertEqual("# Improvement", payload["artifact_candidate"])


if __name__ == "__main__":
    unittest.main()
