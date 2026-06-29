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
        BROAD_BUNDLE_CHILD,
        BROAD_BUNDLE_PEER,
        BROAD_CATCH_ALL_CHILD,
        COMPACT_MANIFEST,
        COMPACT_ROUTING,
        EXISTING,
        LIMITATION,
        NOT_WORTH_IT,
        UNRESOLVED_EXISTING,
        DistillExplorerProvider,
        FindingStyleObservationProvider,
        ExplorerProvider,
        RepairExplorerProvider,
        ReviewGapObservationProvider,
        ReviewRepairProvider,
        StructuredEvidenceProvider,
        bundle_output,
    )
except ImportError:
    from providers import (
        ANALYSIS,
        BROAD_BUNDLE_CHILD,
        BROAD_BUNDLE_PEER,
        BROAD_CATCH_ALL_CHILD,
        COMPACT_MANIFEST,
        COMPACT_ROUTING,
        EXISTING,
        LIMITATION,
        NOT_WORTH_IT,
        UNRESOLVED_EXISTING,
        DistillExplorerProvider,
        FindingStyleObservationProvider,
        ExplorerProvider,
        RepairExplorerProvider,
        ReviewGapObservationProvider,
        ReviewRepairProvider,
        StructuredEvidenceProvider,
        bundle_output,
    )




class TestRepairAndDistill(unittest.TestCase):
    def test_explorer_artifact_contract_failure_is_repaired_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            malformed = "# Slash Command Autocomplete\n\nUseful content in the wrong envelope.\n"
            provider = RepairExplorerProvider([malformed, COMPACT_ROUTING])

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Investigate draft-improvements/explorer-routing-and-analysis-brief.md",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(2, provider.calls.count("explorer_artifact"))
            self.assertIn('"repair"', provider.explorer_prompts[1])
            self.assertIn("explorer output must be concise", provider.explorer_prompts[1])
            self.assertIn("published/explorer.json", result.artifacts)
    def test_explorer_review_contract_failure_is_repaired_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ReviewRepairProvider()

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Investigate draft-improvements/explorer-routing-and-analysis-brief.md",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(2, provider.calls.count("explorer_review"))
            self.assertIn('"repair"', provider.review_prompts[1])
            self.assertIn("review verdict must be exactly APPROVE or REQUEST_CHANGES", provider.review_prompts[1])
            self.assertIn("published/explorer.json", result.artifacts)
    def test_compact_improvement_publication_uses_ai_distiller(self) -> None:
        noisy = """# Improvement: Slash Command Autocomplete
## Status
Proposed new improvement. Selected direction: D1.
## Problem
The interactive console needs slash-triggered command completion.
## Evidence
The request asks for `/` autocomplete.
Discovery selected D1 because it best matched the request.
Repository observation: `ai-harness` owns the console command loop.
Rejected alternatives:
- D2 was rejected because registry-only work is not enough.
Counterevidence and risks:
- Command suggestions can drift from dispatch behavior.
## Desired Behavior
Typing `/` in the TTY console opens command suggestions.
Typing more command letters narrows the suggestions.
Accepting a suggestion inserts the completed command into the input buffer.
## Implementation Notes
First inspect `ai-harness` and reuse the existing command dispatch path.
Avoid duplicate command lists that can drift from dispatch behavior.
## Acceptance Criteria
- A console-input test shows `/` renders command suggestions.
- The same test shows additional letters narrow suggestions.
- The same test shows accepting a suggestion inserts the command.
"""
        distilled = """# Improvement: Slash Command Autocomplete
## Status
Proposed.
## Problem
The interactive console needs slash-triggered command completion.
## Evidence
The request asks for `/` autocomplete, and `ai-harness` owns the console command loop.
## Desired Behavior
Typing `/` in the TTY console opens command suggestions.
Typing more command letters narrows the suggestions.
Accepting a suggestion inserts the completed command into the input buffer.
## Implementation Notes
Inspect `ai-harness` and reuse the existing command dispatch path.
Avoid duplicate command lists that can drift from dispatch behavior.
## Acceptance Criteria
- A console-input test shows `/` renders command suggestions.
- A console-input test shows additional letters narrow suggestions.
- A console-input test shows accepting a suggestion inserts the command.
"""
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = DistillExplorerProvider(noisy, distilled)

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Investigate slash command autocomplete improvement",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            artifact = repository / "docs/explorer/improvements/slash-command-autocomplete/improvement.md"
            self.assertFalse(artifact.exists())
            self.assertEqual(1, provider.calls.count("explorer_distill"))
            self.assertIn('"artifact_candidate"', provider.distill_prompts[0])
    def test_quality_gate_repairs_generic_compact_improvement_once(self) -> None:
        weak = "# Improvement: Weak Artifact\n## Status\nProposed\n## Problem\nThe artifact is weak.\n## Evidence\nExplorer identified a possible behavior.\n## Desired Behavior\nPublish a stronger artifact.\n## Implementation Notes\nKeep it focused.\n## Acceptance Criteria\n- The described behavior is implemented.\n"
        repaired = "# Improvement: Repaired Artifact\n## Status\nProposed\n## Problem\nThe artifact lacks concrete implementation evidence.\n## Evidence\ndocs/analysis/improvements/repaired-artifact/improvement.md records the repaired explorer output.\n## Desired Behavior\nPublish a concrete implementation seed.\n## Implementation Notes\nKeep the artifact focused on repairable explorer quality.\n## Acceptance Criteria\n- The repaired artifact is published with concrete evidence.\n"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = RepairExplorerProvider([weak, repaired])

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze weak compact improvement artifact quality",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(2, provider.calls.count("explorer_artifact"))
            self.assertIn('"repair"', provider.explorer_prompts[1])
            self.assertFalse((repository / "docs/explorer/improvements/repaired-artifact/improvement.md").exists())
    def test_quality_gate_rejects_generic_compact_improvement(self) -> None:
        weak = "# Improvement: Weak Artifact\n## Status\nProposed\n## Problem\nThe artifact is weak.\n## Evidence\nExplorer identified a possible behavior.\n## Desired Behavior\nPublish a stronger artifact.\n## Implementation Notes\nKeep it focused.\n## Acceptance Criteria\n- The described behavior is implemented.\n"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            with self.assertRaisesRegex(Exception, "evidence is too generic"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(weak)),
                    "Analyze weak compact improvement artifact quality",
                    "analysis",
                )


if __name__ == "__main__":
    unittest.main()
