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




class TestPublicationManifest(unittest.TestCase):
    def test_viable_improvement_analysis_is_recorded_and_snapshotted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ExplorerProvider(ANALYSIS)
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Investigate draft-improvements/explorer-routing-and-analysis-brief.md",
                "analysis",
            )

            artifact = "docs/explorer/improvements/explorer-routing-and-analysis-brief/improvement.md"
            self.assertEqual(["explorer_intake", "explorer_discovery", "explorer_decision", "explorer_artifact", "explorer_review", "explorer_distill", "knowledge_synthesis", "knowledge_review"], provider.calls)
            self.assertEqual("success", result.outcome)
            self.assertEqual("EXPLORER", result.strategy.strategy)
            self.assertIn("published/explorer.json", result.artifacts)
            self.assertNotIn("published/learning-learning.json", result.artifacts)
            self.assertFalse((repository / "docs" / "knowledge-db").exists())
            self.assertFalse((repository / artifact).exists())
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["manifest_version"])
            self.assertEqual(artifact, manifest["primary_artifact"])
            self.assertEqual("recorded", manifest["artifacts"][0]["action"])
            self.assertEqual("improvement", manifest["artifacts"][0]["kind"])
            state = json.loads((result.snapshot_path / "state.json").read_text(encoding="utf-8"))
            self.assertEqual("EXPLORER_REVIEW", state["artifacts"]["published/explorer.json"]["phase"])
    def test_limitation_analysis_uses_limitations_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(LIMITATION)),
                "Analyze improvement routing for product fit",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            self.assertIn("published/explorer.json", result.artifacts)
            self.assertFalse((repository / "docs/explorer/limitations/investigate-routing/limitation.md").exists())
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            self.assertEqual("limitation", manifest["kind"])
            self.assertEqual("recorded", manifest["artifacts"][0]["action"])
    def test_not_worth_it_analysis_uses_requested_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(NOT_WORTH_IT)),
                "Research improvement routing cost",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            self.assertIn("published/explorer.json", result.artifacts)
            self.assertFalse((repository / "docs/explorer/probably-a-bullshit/investigate-routing/bullshit.md").exists())
    def test_existing_functionality_uses_existing_functionality_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ExplorerProvider(EXISTING)
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze improvement routing for existing functionality",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(["explorer_intake", "explorer_discovery", "explorer_decision", "explorer_artifact", "explorer_review", "knowledge_synthesis", "knowledge_review"], provider.calls)
            self.assertIn("published/explorer-proposals.json", result.artifacts)
            self.assertIn("published/explorer.json", result.artifacts)
            self.assertFalse((repository / "docs/knowledge-db/investigate-routing/learning.md").is_file())
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            self.assertEqual("knowledge-source", proposal_path.parts[0])
            self.assertEqual("patches", proposal_path.parts[1])
            self.assertEqual("pending", proposal_path.parts[2])
            self.assertEqual(result.run_id, proposal_path.parts[3])

            self.assertTrue((repository / proposal_path / "proposal_manifest.json").is_file())
            claim = json.loads((repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("unverified", claim["status"])
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            self.assertEqual("skipped_no_repo_evidence", telemetry["records"][0]["outcome"])
            self.assertFalse((repository / "docs/analysis/existing-functionality").exists())
    def test_limitation_and_bullshit_bundle_entries_publish_knowledge_proposals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            output = bundle_output([
                {
                    "id": "routing-limit",
                    "action": "create",
                    "artifact_kind": "limitation",
                    "title": "Routing constraint",
                    "content": LIMITATION,
                },
                {
                    "id": "routing-bullshit",
                    "action": "create",
                    "artifact_kind": "bullshit",
                    "title": "Routing direction should not be pursued",
                    "content": NOT_WORTH_IT,
                },
            ], "routing-limit")
            provider = ExplorerProvider(output)
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze routing constraint and low-value direction",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            self.assertIn("published/explorer.json", result.artifacts)
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            self.assertEqual(2, len(manifest["artifacts"]))
            kinds = [item["kind"] for item in manifest["artifacts"]]
            self.assertEqual(["limitation", "bullshit"], kinds)
            for entry in manifest["artifacts"]:
                self.assertEqual("recorded", entry["action"])
                proposal_path = Path(entry["knowledge_proposal"])
                self.assertTrue(proposal_path.parts[:4] == ("knowledge-source", "patches", "pending", result.run_id))
                self.assertTrue((repository / proposal_path / "proposal_manifest.json").is_file())
                self.assertTrue((repository / proposal_path / "proposed_claims.jsonl").is_file())
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            self.assertEqual(["skipped_no_repo_evidence", "skipped_no_repo_evidence"], [item["outcome"] for item in telemetry["records"]])
    def test_explorer_bundle_creates_multiple_improvements_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            output = bundle_output([
                {
                    "id": "routing",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Routing bundle output",
                    "content": COMPACT_ROUTING,
                },
                {
                    "id": "manifest",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Manifest bundle output",
                    "content": COMPACT_MANIFEST,
                },
            ], "routing")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                "Analyze routing and manifest bundle improvements",
                "analysis",
            )

            routing = "docs/explorer/improvements/routing-bundle-output/improvement.md"
            manifest_path = "docs/explorer/improvements/manifest-bundle-output/improvement.md"
            self.assertEqual("success", result.outcome)
            self.assertFalse((repository / routing).exists())
            self.assertFalse((repository / manifest_path).exists())
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            self.assertEqual(routing, manifest["primary_artifact"])
            self.assertEqual(["routing", "manifest"], [item["entry_id"] for item in manifest["artifacts"]])
            self.assertEqual(["recorded", "recorded"], [item["action"] for item in manifest["artifacts"]])
    def test_explorer_bundle_creates_nested_initiative_improvements_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            layered = "# Improvement: Layered Canonical Improvements\n## Status\nProposed\n## Problem\nNested canonical improvements are not discovered.\n## Evidence\ndocs/analysis/improvements/improvement-generation-quality/layered-canonical-improvements/improvement.md records the requested child improvement.\n## Desired Behavior\nDiscover nested canonical improvement paths.\n## Implementation Notes\nKeep discovery recursive and deterministic.\n## Acceptance Criteria\n- Nested canonical improvement paths are discovered.\n"
            scope = "# Improvement: Explorer Scope Planning\n## Status\nProposed\n## Problem\nBroad explorer requests are not split.\n## Evidence\ndocs/analysis/improvements/improvement-generation-quality/explorer-scope-planning/improvement.md records the requested child improvement.\n## Desired Behavior\nSplit broad explorer requests into focused entries.\n## Implementation Notes\nUse initiative child paths under the shared quality initiative.\n## Acceptance Criteria\n- Broad explorer requests produce grouped bundle entries.\n"
            output = bundle_output([
                {
                    "id": "layered",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Layered canonical improvements",
                    "path": "docs/analysis/improvements/improvement-generation-quality/layered-canonical-improvements/improvement.md",
                    "content": layered,
                },
                {
                    "id": "scope",
                    "action": "create",
                    "artifact_kind": "improvement",
                    "title": "Explorer scope planning",
                    "path": "docs/analysis/improvements/improvement-generation-quality/explorer-scope-planning/improvement.md",
                    "content": scope,
                },
            ], "layered")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                "Analyze improvement generation quality across canonical discovery and scope planning",
                "analysis",
            )

            layered_path = "docs/analysis/improvements/improvement-generation-quality/layered-canonical-improvements/improvement.md"
            scope_path = "docs/analysis/improvements/improvement-generation-quality/explorer-scope-planning/improvement.md"
            self.assertEqual("success", result.outcome)
            self.assertFalse((repository / layered_path).exists())
            self.assertFalse((repository / scope_path).exists())
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            self.assertEqual(layered_path, manifest["primary_artifact"])
            self.assertEqual([layered_path, scope_path], [item["suggested_path"] for item in manifest["artifacts"]])
    def test_explorer_bundle_updates_existing_improvement_with_checksum_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs/analysis/improvements/routing-bundle-output/improvement.md"
            artifact.parent.mkdir(parents=True)
            original = "# Improvement: Routing Bundle Output\n## Status\nProposed\n## Problem\nOld problem.\n## Evidence\nOld evidence.\n## Desired Behavior\nOld behavior.\n## Implementation Notes\nOld notes.\n## Acceptance Criteria\n- Old.\n"
            artifact.write_text(original, encoding="utf-8")
            output = bundle_output([{
                "id": "update-routing",
                "action": "update",
                "artifact_kind": "improvement",
                "title": "Routing bundle output",
                "path": "docs/analysis/improvements/routing-bundle-output/improvement.md",
                "expected_checksum": checksum(original),
                "content": COMPACT_ROUTING,
            }], "update-routing")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                "Analyze routing bundle output update",
                "analysis",
            )

            self.assertEqual(original, artifact.read_text(encoding="utf-8"))
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            record = manifest["artifacts"][0]
            self.assertEqual("recorded", record["action"])
            self.assertEqual("update", record["bundle_action"])
            self.assertEqual("docs/analysis/improvements/routing-bundle-output/improvement.md", record["suggested_path"])
    def test_explorer_bundle_rejects_stale_or_unsafe_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs/analysis/improvements/routing-bundle-output/improvement.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(COMPACT_ROUTING, encoding="utf-8")
            stale = bundle_output([{
                "id": "update-routing",
                "action": "update",
                "artifact_kind": "improvement",
                "title": "Routing bundle output",
                "path": "docs/analysis/improvements/routing-bundle-output/improvement.md",
                "expected_checksum": "stale",
                "content": COMPACT_MANIFEST,
            }], "update-routing")

            with self.assertRaisesRegex(Exception, "checksum mismatch"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(stale)),
                    "Analyze routing bundle output update",
                    "analysis",
                )

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            unsafe = bundle_output([{
                "id": "unsafe-update",
                "action": "update",
                "artifact_kind": "improvement",
                "title": "Unsafe update",
                "path": "docs/analysis/limitations/routing/limitation.md",
                "expected_checksum": checksum(COMPACT_ROUTING),
                "content": COMPACT_ROUTING,
            }], "unsafe-update")

            with self.assertRaisesRegex(Exception, "update intent must target"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(unsafe)),
                    "Analyze unsafe routing bundle update",
                    "analysis",
                )


if __name__ == "__main__":
    unittest.main()
