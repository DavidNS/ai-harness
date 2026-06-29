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




class TestKnowledgeExtraction(unittest.TestCase):
    def test_improvement_entry_publishes_pending_knowledge_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ExplorerProvider(COMPACT_ROUTING)
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze routing bundle output",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            self.assertEqual("improvement", manifest["kind"])
            entry = manifest["artifacts"][0]
            self.assertEqual("improvement", entry["kind"])
            self.assertNotIn("path", entry)
            proposal_path = Path(entry["knowledge_proposal"])
            self.assertEqual(("knowledge-source", "patches", "pending", result.run_id), proposal_path.parts[:4])
            self.assertTrue((repository / proposal_path / "proposal_manifest.json").is_file())
            claims_path = repository / proposal_path / "proposed_claims.jsonl"
            self.assertTrue(claims_path.is_file())
            claim = json.loads(claims_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("unverified", claim["status"])
            self.assertEqual([], claim["files"])
            metadata = claim["metadata"]
            self.assertEqual("repository_evidence_rejected", metadata["unverified_reason"])
            self.assertIn("rejection_reasons", metadata)
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            record = telemetry["records"][0]
            self.assertEqual("skipped_no_repo_evidence", record["outcome"])
            self.assertEqual("unverified", record["claim_status"])
            self.assertIn("entry_text", record["evidence_sources_checked"])
            self.assertIn("mapped_claim_type", record)
            self.assertTrue(any("explorer-knowledge-extraction.json" in warning for warning in result.warnings))
            self.assertFalse((repository / "docs" / "knowledge-db").exists())
    def test_no_repository_candidates_keep_missing_evidence_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            output = bundle_output([{
                "id": "routing",
                "action": "create",
                "artifact_kind": "improvement",
                "title": "Routing missing evidence",
                "content": "# Improvement: Routing Missing Evidence\n## Status\nProposed\n## Problem\nMissing evidence should stay unverified.\n## Evidence\n`not-repo-token` records request context.\n## Desired Behavior\nPublish missing evidence behavior.\n## Implementation Notes\nKeep the change focused.\n## Acceptance Criteria\n- Claims record missing evidence.\n",
            }], "routing")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                "Analyze routing missing evidence",
                "analysis",
            )

            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            claim = json.loads((repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("unverified", claim["status"])
            self.assertEqual("missing_repository_evidence", claim["metadata"]["unverified_reason"])
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            self.assertEqual("missing_repository_evidence", telemetry["records"][0]["failure_code"])
    def test_explorer_repository_evidence_creates_active_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / "src/routing.py"
            source.parent.mkdir(parents=True)
            source.write_text("def route_request():\n    return 'ok'\n", encoding="utf-8")
            output = bundle_output([{
                "id": "routing",
                "action": "create",
                "artifact_kind": "improvement",
                "title": "Routing bundle output",
                "content": "# Improvement: Routing Bundle Output\n## Status\nProposed\n## Problem\nRouting bundle output is missing.\n## Evidence\nsrc/routing.py defines route_request for the focused routing behavior.\n## Desired Behavior\nPublish a routing improvement.\n## Implementation Notes\nKeep the change focused.\n## Acceptance Criteria\n- Routing bundle output is published.\n",
                "repository_evidence": [{
                    "path": "src/routing.py",
                    "kind": "code",
                    "symbol": "route_request",
                    "line_start": 1,
                    "line_end": 2,
                    "excerpt": "def route_request():",
                }],
            }], "routing")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                "Analyze routing bundle output",
                "analysis",
            )

            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            claim = json.loads((repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("active", claim["status"])
            self.assertEqual(["src/routing.py"], claim["files"])
            self.assertEqual("responsibility", claim["claim_type"])
            self.assertEqual("src/routing.py defines source behavior for route_request.", claim["text"])
            self.assertNotIn("Routing bundle output", claim["text"])
            self.assertEqual("code", claim["evidence"][0]["type"])
            self.assertEqual(["repository_evidence"], claim["metadata"]["evidence_sources_checked"])
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            record = telemetry["records"][0]
            self.assertEqual("proposal_created", record["outcome"])
            self.assertEqual("active", record["claim_status"])
            self.assertEqual("improvement", record["requested_claim_type"])
            self.assertEqual("decision", record["mapped_claim_type"])
            self.assertIn("repository_evidence", record["evidence_sources_checked"])
    def test_explorer_repository_evidence_creates_per_fact_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / "src/routing.py"
            source.parent.mkdir(parents=True)
            source.write_text("def route_request():\n    return 'ok'\n", encoding="utf-8")
            test_path = repository / "tests/test_routing.py"
            test_path.parent.mkdir(parents=True)
            test_path.write_text("def test_route_request():\n    assert True\n", encoding="utf-8")
            output = bundle_output([{
                "id": "routing",
                "action": "create",
                "artifact_kind": "improvement",
                "title": "Routing bundle output",
                "content": "# Improvement: Routing Bundle Output\n## Status\nProposed\n## Problem\nRouting bundle output is missing.\n## Evidence\nsrc/routing.py defines route_request and tests/test_routing.py covers it.\n## Desired Behavior\nPublish a routing improvement.\n## Implementation Notes\nKeep the change focused.\n## Acceptance Criteria\n- Routing bundle output is published.\n",
                "repository_evidence": [
                    {
                        "path": "src/routing.py",
                        "kind": "code",
                        "symbol": "route_request",
                        "line_start": 1,
                        "line_end": 2,
                        "excerpt": "def route_request():",
                    },
                    {
                        "path": "tests/test_routing.py",
                        "kind": "test",
                        "symbol": "test_route_request",
                        "line_start": 1,
                        "line_end": 1,
                        "excerpt": "def test_route_request():",
                    },
                ],
            }], "routing")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                "Analyze routing bundle output",
                "analysis",
            )

            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            proposal_manifest = json.loads((repository / proposal_path / "proposal_manifest.json").read_text(encoding="utf-8"))
            claims = [
                json.loads(line)
                for line in (repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(2, proposal_manifest["claims_count"])
            self.assertEqual(2, len(claims))
            self.assertEqual(["src/routing.py"], claims[0]["files"])
            self.assertEqual(["tests/test_routing.py"], claims[1]["files"])
            self.assertEqual("src/routing.py defines source behavior for route_request.", claims[0]["text"])
            self.assertEqual("tests/test_routing.py covers test behavior for test_route_request.", claims[1]["text"])
            self.assertEqual("responsibility", claims[0]["claim_type"])
            self.assertEqual("test_coverage", claims[1]["claim_type"])
            self.assertTrue(all(claim["status"] == "active" for claim in claims))
            self.assertTrue(all("Routing bundle output" not in claim["text"] for claim in claims))
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            self.assertEqual(2, len(telemetry["records"][0]["evidence_accepted"]))
    def test_extensionless_launcher_repository_observation_is_code_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            launcher = repository / "ai-harness"
            launcher.write_text("#!/usr/bin/env python3\nprint('console loop')\n", encoding="utf-8")
            provider = FindingStyleObservationProvider(COMPACT_ROUTING, [{
                "kind": "source",
                "path": "ai-harness",
                "matches": ["L1: #!/usr/bin/env python3"],
            }])

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze console slash completion",
                "analysis",
            )

            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            claim = json.loads((repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("active", claim["status"])
            self.assertIn("ai-harness", claim["files"])
            self.assertEqual("ai-harness contains source behavior evidenced by: #!/usr/bin/env python3", claim["text"])
            evidence = [item for item in claim["evidence"] if item.get("file") == "ai-harness"]
            self.assertTrue(evidence)
            self.assertEqual("code", evidence[0]["type"])
    def test_extensionless_launcher_entry_text_is_code_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            launcher = repository / "ai-harness"
            launcher.write_text("#!/usr/bin/env python3\nprint('console loop')\n", encoding="utf-8")
            output = bundle_output([{
                "id": "launcher",
                "action": "create",
                "artifact_kind": "improvement",
                "title": "Launcher console entrypoint",
                "content": "# Improvement: Launcher Console Entrypoint\n## Status\nProposed\n## Problem\nLauncher evidence should be extracted.\n## Evidence\n`ai-harness` records the launcher behavior.\n## Desired Behavior\nPublish launcher evidence.\n## Implementation Notes\nKeep the change focused.\n## Acceptance Criteria\n- Claims include launcher evidence.\n",
            }], "launcher")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                "Analyze launcher console entrypoint",
                "analysis",
            )

            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            claim = json.loads((repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("active", claim["status"])
            self.assertEqual(["ai-harness"], claim["files"])
            self.assertEqual("code", claim["evidence"][0]["type"])
            self.assertIn("entry_text", claim["metadata"]["evidence_sources_checked"])
    def test_structured_discovery_evidence_creates_active_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / "src/routing.py"
            source.parent.mkdir(parents=True)
            source.write_text("def route_request():\n    return 'ok'\n", encoding="utf-8")
            output = bundle_output([{
                "id": "routing",
                "action": "create",
                "artifact_kind": "improvement",
                "title": "Routing structured evidence",
                "content": "# Improvement: Routing Structured Evidence\n## Status\nProposed\n## Problem\nStructured evidence should be mined.\n## Evidence\n`not-repo-token` records request context.\n## Desired Behavior\nPublish structured evidence.\n## Implementation Notes\nKeep the change focused.\n## Acceptance Criteria\n- Claims include structured evidence.\n",
            }], "routing")
            provider = StructuredEvidenceProvider(output, "src/routing.py defines route_request for routing.")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze routing structured evidence",
                "analysis",
            )

            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            claim = json.loads((repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("active", claim["status"])
            self.assertEqual(["src/routing.py"], claim["files"])
            self.assertIn("discovery_claim", claim["metadata"]["evidence_sources_checked"])
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            self.assertIn("candidate_direction", telemetry["records"][0]["evidence_sources_checked"])
    def test_explorer_rejects_mismatched_repository_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / "src/routing.py"
            source.parent.mkdir(parents=True)
            source.write_text("def route_request():\n    return 'ok'\n", encoding="utf-8")
            output = bundle_output([{
                "id": "routing",
                "action": "create",
                "artifact_kind": "improvement",
                "title": "Routing bundle output",
                "content": "# Improvement: Routing Bundle Output\n## Status\nProposed\n## Problem\nRouting bundle output is missing.\n## Evidence\nsrc/routing.py defines route_request for the focused routing behavior.\n## Desired Behavior\nPublish a routing improvement.\n## Implementation Notes\nKeep the change focused.\n## Acceptance Criteria\n- Routing bundle output is published.\n",
                "repository_evidence": [{
                    "path": "src/routing.py",
                    "kind": "code",
                    "line_start": 1,
                    "line_end": 1,
                    "excerpt": "def missing_route():",
                }],
            }], "routing")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                "Analyze routing bundle output",
                "analysis",
            )

            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            claim = json.loads((repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("unverified", claim["status"])
            metadata = claim["metadata"]
            self.assertEqual("repository_evidence_rejected", metadata["unverified_reason"])
            self.assertIn("excerpt_not_found", [item["reason"] for item in metadata["rejection_reasons"]])
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            record = telemetry["records"][0]
            self.assertEqual("skipped_no_repo_evidence", record["outcome"])
            self.assertEqual("repository_evidence_rejected", record["failure_code"])
            self.assertEqual("excerpt_not_found", record["evidence_rejected"][0]["reason"])
    def test_rejected_explicit_evidence_does_not_fall_back_to_structured_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / "src/routing.py"
            source.parent.mkdir(parents=True)
            source.write_text("def route_request():\n    return 'ok'\n", encoding="utf-8")
            output = bundle_output([{
                "id": "routing",
                "action": "create",
                "artifact_kind": "improvement",
                "title": "Routing explicit evidence",
                "content": "# Improvement: Routing Explicit Evidence\n## Status\nProposed\n## Problem\nExplicit evidence should remain authoritative.\n## Evidence\n`not-repo-token` records request context.\n## Desired Behavior\nPublish explicit evidence behavior.\n## Implementation Notes\nKeep the change focused.\n## Acceptance Criteria\n- Claims preserve explicit evidence authority.\n",
                "repository_evidence": [{
                    "path": "src/routing.py",
                    "kind": "code",
                    "line_start": 1,
                    "line_end": 1,
                    "excerpt": "def missing_route():",
                }],
            }], "routing")
            provider = StructuredEvidenceProvider(output, "src/routing.py defines route_request for routing.")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze routing explicit evidence",
                "analysis",
            )

            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            claim = json.loads((repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("unverified", claim["status"])
            metadata = claim["metadata"]
            self.assertEqual("repository_evidence_rejected", metadata["unverified_reason"])
            self.assertEqual(["repository_evidence"], metadata["evidence_sources_checked"])
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            record = telemetry["records"][0]
            self.assertEqual(["repository_evidence"], record["evidence_sources_checked"])
            self.assertEqual("repository_evidence_rejected", record["failure_code"])
    def test_explorer_rejects_mismatched_repository_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / "src/routing.py"
            source.parent.mkdir(parents=True)
            source.write_text("def route_request():\n    return 'ok'\n", encoding="utf-8")
            output = bundle_output([{
                "id": "routing",
                "action": "create",
                "artifact_kind": "improvement",
                "title": "Routing bundle output",
                "content": "# Improvement: Routing Bundle Output\n## Status\nProposed\n## Problem\nRouting bundle output is missing.\n## Evidence\nsrc/routing.py defines route_request for the focused routing behavior.\n## Desired Behavior\nPublish a routing improvement.\n## Implementation Notes\nKeep the change focused.\n## Acceptance Criteria\n- Routing bundle output is published.\n",
                "repository_evidence": [{
                    "path": "src/routing.py",
                    "kind": "code",
                    "symbol": "missing_route",
                    "line_start": 1,
                    "line_end": 2,
                    "excerpt": "def route_request():",
                }],
            }], "routing")

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ExplorerProvider(output)),
                "Analyze routing bundle output",
                "analysis",
            )

            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            claim = json.loads((repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("unverified", claim["status"])
            metadata = claim["metadata"]
            self.assertEqual("repository_evidence_rejected", metadata["unverified_reason"])
            self.assertIn("symbol_not_found", [item["reason"] for item in metadata["rejection_reasons"]])
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            record = telemetry["records"][0]
            self.assertEqual("skipped_no_repo_evidence", record["outcome"])
            self.assertEqual("symbol_not_found", record["evidence_rejected"][0]["reason"])
    def test_missing_repository_observation_citation_falls_back_to_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ReviewGapObservationProvider(COMPACT_ROUTING)

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Analyze routing bundle output",
                "analysis",
            )

            self.assertEqual("success", result.outcome)
            manifest = json.loads((result.snapshot_path / "published" / "explorer.json").read_text(encoding="utf-8"))
            proposal_path = Path(manifest["artifacts"][0]["knowledge_proposal"])
            claim = json.loads((repository / proposal_path / "proposed_claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("unverified", claim["status"])
            metadata = claim["metadata"]
            self.assertEqual("repository_evidence_rejected", metadata["unverified_reason"])
            self.assertIn("observation_gap", [item["reason"] for item in metadata["rejection_reasons"]])
            telemetry = json.loads((result.snapshot_path / "published" / "explorer-knowledge-extraction.json").read_text(encoding="utf-8"))
            record = telemetry["records"][0]
            self.assertEqual("skipped_no_repo_evidence", record["outcome"])
            self.assertEqual("unverified", record["claim_status"])


if __name__ == "__main__":
    unittest.main()
