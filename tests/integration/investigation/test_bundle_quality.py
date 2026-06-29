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




class TestBundleQuality(unittest.TestCase):
    def test_focused_broad_bundle_children_satisfy_split_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            output = bundle_output([
                {
                    "id": "knowledge-source-contracts",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Knowledge source contracts",
                    "path": "docs/analysis/improvements/explorer-bundle-quality-gate/knowledge-source-contracts/improvement.md",
                    "content": BROAD_BUNDLE_CHILD,
                },
                {
                    "id": "navigation-context-contracts",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Navigation context contracts",
                    "path": "docs/analysis/improvements/explorer-bundle-quality-gate/navigation-context-contracts/improvement.md",
                    "content": BROAD_BUNDLE_PEER,
                },
            ], "knowledge-source-contracts")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                "Analyze bundle-aware explorer broadness checks",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            self.assertFalse((repository / "docs/analysis/improvements/explorer-bundle-quality-gate/knowledge-source-contracts/improvement.md").exists())
            self.assertFalse((repository / "docs/analysis/improvements/explorer-bundle-quality-gate/navigation-context-contracts/improvement.md").exists())
    def test_standalone_broad_compact_improvement_still_requires_scope_justification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            with self.assertRaisesRegex(Exception, "broad explorer improvement"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(BROAD_BUNDLE_CHILD)),
                    "Analyze standalone broad compact improvement",
                    "analysis",
                )
    def test_unfocused_broad_bundle_child_is_rejected_with_child_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            output = bundle_output([
                {
                    "id": "knowledge-source-contracts",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Knowledge source contracts",
                    "path": "docs/analysis/improvements/explorer-bundle-quality-gate/knowledge-source-contracts/improvement.md",
                    "content": BROAD_BUNDLE_CHILD,
                },
                {
                    "id": "catch-all",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Catch-all harness cleanup",
                    "path": "docs/analysis/improvements/explorer-bundle-quality-gate/catch-all/improvement.md",
                    "content": BROAD_CATCH_ALL_CHILD,
                },
            ], "knowledge-source-contracts")

            with self.assertRaisesRegex(Exception, "explorer bundle entry catch-all: broad explorer improvement"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                    "Analyze bundle with an unfocused catch-all child",
                    "analysis",
                )
    def test_bundle_validation_failure_does_not_partially_publish_entries(self) -> None:
        weak = "# Improvement: Weak Bundle Child\n## Status\nProposed\n## Problem\nThe artifact is weak.\n## Evidence\nExplorer identified a possible behavior.\n## Desired Behavior\nPublish a stronger artifact.\n## Implementation Notes\nKeep it focused.\n## Acceptance Criteria\n- The described behavior is implemented.\n"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            first_path = "docs/analysis/improvements/routing-bundle-output/improvement.md"
            output = bundle_output([
                {
                    "id": "routing",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Routing bundle output",
                    "path": first_path,
                    "content": COMPACT_ROUTING,
                },
                {
                    "id": "weak",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Weak bundle child",
                    "path": "docs/analysis/improvements/weak-bundle-child/improvement.md",
                    "content": weak,
                },
            ], "routing")

            with self.assertRaisesRegex(Exception, "explorer bundle entry weak: compact improvement evidence is too generic"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                    "Analyze bundle with one invalid child",
                    "analysis",
                )

            self.assertFalse((repository / first_path).exists())
            self.assertFalse(StateStore(repository).artifacts.exists("published/explorer.json"))
    def test_unresolved_factual_open_questions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            with self.assertRaisesRegex(Exception, "unresolved factual open questions"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(UNRESOLVED_EXISTING)),
                    "Analyze improvement routing for existing functionality",
                    "analysis",
                )


if __name__ == "__main__":
    unittest.main()
