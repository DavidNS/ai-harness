from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.config import HarnessConfig
from ai_harness.orchestrator import Orchestrator
from ai_harness.providers.base import ProviderResult
from ai_harness.stores.knowledge import SQLiteKnowledgeStore
from ai_harness.models import KnowledgeEntry
from tests.fixtures.flow import run_with_flow
from tests.fixtures.scripted_provider import ScriptedProvider, learning_output


class InvalidLearningProvider(ScriptedProvider):
    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Knowledge Synthesis Worker v1" in prompt:
            self.calls.append("knowledge_synthesis")
            if "rejected_candidate_excerpt" in prompt:
                return ProviderResult(
                    learning_output(
                        proposal_id="proposal.repaired-learning.001",
                        claim_id="claim.repaired-learning.001",
                        summary="Repaired learning.",
                        text="The learning worker repaired an initially malformed proposal.",
                    ),
                    "",
                    0,
                    0.001,
                )
            return ProviderResult("Learning summary without the required heading", "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class AlwaysInvalidLearningProvider(ScriptedProvider):
    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Knowledge Synthesis Worker v1" in prompt:
            self.calls.append("knowledge_synthesis")
            return ProviderResult("Learning summary without the required heading", "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class ContractDriftKnowledgeSynthesisProvider(ScriptedProvider):
    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Knowledge Synthesis Worker v1" in prompt:
            self.calls.append("knowledge_synthesis")
            if "rejected_candidate_excerpt" not in prompt:
                return ProviderResult(json.dumps({
                    "schema_version": 1,
                    "phase": "learning",
                    "proposal_manifest": {
                        "schema_version": 1,
                        "proposal_id": "proposal.contract-drift.001",
                        "summary": "Invalid initial shape that mirrors provider drift.",
                        "source_artifacts": ["implementation/T1/1.md"],
                    },
                    "proposed_claims": [{
                        "id": "C1",
                        "status": "active",
                        "claim": "feature.py records deterministic fixture behavior.",
                        "evidence": [{"file": "feature.py"}],
                    }],
                }), "", 0, 0.001)
            return ProviderResult(json.dumps({
                "schema_version": 1,
                "phase": "learning",
                "proposal_manifest": {
                    "schema_version": 1,
                    "proposal_id": "proposal.contract-drift.001",
                    "summary": "Repaired strict learning proposal shape.",
                    "source_artifacts": ["implementation/T1/1.md"],
                    "claims_file": "proposed_claims.jsonl",
                    "relations_file": "proposed_relations.jsonl",
                },
                "proposed_claims": [
                    {
                        "id": "claim.contract-drift.001",
                        "domain": "harness",
                        "subjects": ["Feature fixture"],
                        "files": ["feature.py"],
                        "symbols": [],
                        "claim_type": "responsibility",
                        "text": "feature.py records deterministic fixture behavior.",
                        "status": "active",
                        "evidence": [{"type": "code", "file": "feature.py"}],
                        "valid_from": None,
                        "valid_until": None,
                        "last_verified": None,
                    },
                    {
                        "id": "claim.contract-drift.002",
                        "domain": "tests",
                        "subjects": ["Feature fixture tests"],
                        "files": ["feature.py"],
                        "symbols": [],
                        "claim_type": "test_coverage",
                        "text": "feature.py is the repository-backed evidence for the repaired knowledge proposal.",
                        "status": "active",
                        "evidence": [{"type": "code", "file": "feature.py"}],
                        "valid_from": None,
                        "valid_until": None,
                        "last_verified": None,
                    },
                ],
                "proposed_relations": [{
                    "id": "relation.contract-drift.001",
                    "domain": "harness",
                    "source": "claim.contract-drift.002",
                    "target": "claim.contract-drift.001",
                    "relation_type": "supports",
                    "status": "active",
                    "evidence": [{"type": "code", "file": "feature.py"}],
                }],
            }), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class ConflictingEvidenceLearningProvider(ScriptedProvider):
    def __init__(self) -> None:
        super().__init__()
        base = json.loads(learning_output())
        base["proposed_claims"][0]["evidence"] = [{"type": "documentation", "file": "ai-harness"}]
        self.learning_output = json.dumps(base, ensure_ascii=False, sort_keys=True) + "\n"

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Knowledge Synthesis Worker v1" in prompt:
            self.calls.append("knowledge_synthesis")
            return ProviderResult(self.learning_output, "", 0, 0.001)
        if "# Knowledge Review Worker v1" in prompt:
            self.calls.append("knowledge_review")
            proposal = json.loads(prompt.split("Controller inputs:\n", 1)[1])["proposal"]
            claim_id = proposal["proposed_claims"][0]["id"]
            proposal_id = proposal["proposal_manifest"]["proposal_id"]
            return ProviderResult(json.dumps({
                "schema_version": 1,
                "phase": "knowledge_review",
                "proposal_id": proposal_id,
                "claim_reviews": [{
                    "claim_id": claim_id,
                    "decision": "downgrade",
                    "reason": "evidence_type_conflict",
                }],
                "relation_reviews": [],
            }), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)



class RepairingKnowledgeLearningProvider(ScriptedProvider):
    def __init__(self) -> None:
        super().__init__()
        self.review_calls = 0

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Knowledge Synthesis Worker v1" in prompt:
            self.calls.append("knowledge_synthesis")
            if "rejected_candidate_excerpt" in prompt:
                return ProviderResult(
                    learning_output(
                        proposal_id="proposal.repaired-learning.002",
                        claim_id="claim.repaired-learning.002",
                        summary="Knowledge repaired with review guidance.",
                        text="feature.py defines the deterministic offline completion fixture behavior.",
                    ),
                    "",
                    0,
                    0.001,
                )
            return ProviderResult(
                learning_output(
                    proposal_id="proposal.repaired-learning.001",
                    claim_id="claim.repaired-learning.001",
                    summary="Knowledge requires repair.",
                    text="The run completed offline using deterministic gates.",
                ),
                "",
                0,
                0.001,
            )

        if "# Knowledge Review Worker v1" in prompt:
            self.calls.append("knowledge_review")
            proposal = json.loads(prompt.split("Controller inputs:\n", 1)[1])["proposal"]
            claim_id = proposal["proposed_claims"][0]["id"]
            proposal_id = proposal["proposal_manifest"]["proposal_id"]
            self.review_calls += 1
            if self.review_calls == 1:
                return ProviderResult(json.dumps({
                    "schema_version": 1,
                    "phase": "knowledge_review",
                    "proposal_id": proposal_id,
                    "claim_reviews": [{
                        "claim_id": claim_id,
                        "decision": "reject_for_repair",
                        "reason": "claim text is process-oriented and not a durable repository fact",
                        "suggested_text": "feature.py defines the deterministic offline completion fixture behavior.",
                    }],
                    "relation_reviews": [],
                }), "", 0, 0.001)
            return ProviderResult(json.dumps({
                "schema_version": 1,
                "phase": "knowledge_review",
                "proposal_id": proposal_id,
                "claim_reviews": [{
                    "claim_id": claim_id,
                    "decision": "accept",
                    "reason": "active claim is repository-grounded and file-backed",
                }],
                "relation_reviews": [],
            }), "", 0, 0.001)

        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)

class FailingKnowledgeStore:
    def add_entry(self, entry: object) -> None:
        raise RuntimeError("database unavailable")

    def search(self, query: str, limit: int = 5) -> list[object]:
        return []

    def list_recent(self, limit: int = 10) -> list[object]:
        return []


class FailingCanonicalDocs:
    def write(self, relative: str, content: str) -> dict[str, str]:
        raise OSError("learning artifact unavailable")

    def write_knowledge_index(self, knowledge_entries=None) -> None:
        raise OSError("learning artifact unavailable")

    def knowledge_path(self, slug: str) -> str:
        return f"docs/knowledge-db/{slug}/learning.md"

    def similar_knowledge(self, sections, *, exclude=None):
        return []




class TestSimpleLearningRepair(unittest.TestCase):
    def test_invalid_learning_output_is_repaired_to_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            provider = InvalidLearningProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(["implement", "review", "knowledge_synthesis", "knowledge_synthesis", "knowledge_review"], provider.calls)
            self.assertFalse(any("Learning failed" in warning for warning in result.warnings))
            self.assertIn("learning.json", result.artifacts)
            self.assertIn("published/learning-proposals.json", result.artifacts)
            manifest = repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposal_manifest.json"
            claims = repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposed_claims.jsonl"
            self.assertTrue(manifest.is_file())
            self.assertTrue(claims.is_file())
            self.assertFalse((repository / "docs/knowledge-db/repaired-learning/learning.md").exists())
            entries = SQLiteKnowledgeStore(repository / ".ai-harness/knowledge.db").list_recent()
            self.assertEqual([], entries)
            self.assertEqual("claim.repaired-learning.001", json.loads(claims.read_text(encoding="utf-8").splitlines()[0])["id"])
            self.assertTrue(result.snapshot_path.is_dir())
            state = json.loads((result.snapshot_path / "state.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", state["status"])
            result_json = json.loads((result.snapshot_path / "result.json").read_text(encoding="utf-8"))
            self.assertEqual("success", result_json["status"])
    def test_knowledge_synthesis_contract_drift_repairs_to_strict_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            (repository / "feature.py").write_text("ready\n", encoding="utf-8")
            provider = ContractDriftKnowledgeSynthesisProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(["implement", "review", "knowledge_synthesis", "knowledge_synthesis", "knowledge_review"], provider.calls)
            claims = repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposed_claims.jsonl"
            relations = repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposed_relations.jsonl"
            self.assertTrue(claims.is_file())
            self.assertTrue(relations.is_file())
            claim_ids = [json.loads(line)["id"] for line in claims.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["claim.contract-drift.001", "claim.contract-drift.002"], claim_ids)
            relation = json.loads(relations.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("claim.contract-drift.002", relation["source"])
            self.assertEqual("claim.contract-drift.001", relation["target"])
    def test_learning_quality_gate_can_repair_with_review_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            (repository / "feature.py").write_text("ready\n", encoding="utf-8")
            provider = RepairingKnowledgeLearningProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(
                ["implement", "review", "knowledge_synthesis", "knowledge_review", "knowledge_synthesis", "knowledge_review"],
                provider.calls,
            )
            manifest = repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposal_manifest.json"
            claims = repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposed_claims.jsonl"
            self.assertTrue(manifest.is_file())
            self.assertTrue(claims.is_file())
            claim = json.loads(claims.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("active", claim["status"])
            self.assertIn("deterministic offline completion fixture behavior", claim["text"])
    def test_learning_quality_gate_can_downgrade_conflicting_claims(self) -> None:

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            (repository / "ai-harness").write_text("#!/usr/bin/env python3\nprint('console loop')\n", encoding="utf-8")
            provider = ConflictingEvidenceLearningProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("success", result.outcome)
            self.assertIn("knowledge_synthesis", provider.calls)
            self.assertIn("knowledge_review", provider.calls)
            manifest = repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposal_manifest.json"
            claims = repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposed_claims.jsonl"
            self.assertTrue(manifest.is_file())
            self.assertTrue(claims.is_file())
            record = json.loads(claims.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual("unverified", record["status"])
            self.assertEqual("evidence_type_conflict", record["metadata"]["unverified_reason"])
            self.assertEqual("ai_knowledge_review", record["metadata"]["quality_gate"])
            self.assertIn("Knowledge proposal AI review downgraded", "".join(result.warnings))
    def test_exhausted_learning_repair_finishes_as_partial_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            provider = AlwaysInvalidLearningProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("partial success", result.outcome)
            self.assertEqual(["implement", "review", "knowledge_synthesis", "knowledge_synthesis"], provider.calls)
            self.assertTrue(any("Learning failed" in warning for warning in result.warnings))
            self.assertNotIn("published/learning-proposals.json", result.artifacts)
            entries = SQLiteKnowledgeStore(repository / ".ai-harness/knowledge.db").list_recent()
            self.assertEqual([], entries)
    def test_database_failure_after_valid_learning_finishes_as_partial_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            provider = ScriptedProvider()
            result = run_with_flow(
                Orchestrator(
                    repository,
                    HarnessConfig(provider="local"),
                    provider,
                    knowledge=FailingKnowledgeStore(),
                ),
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("success", result.outcome)
            self.assertIn("published/learning-proposals.json", result.artifacts)
            self.assertFalse(any("Knowledge persistence failed" in warning for warning in result.warnings))
            result_json = json.loads((result.snapshot_path / "result.json").read_text(encoding="utf-8"))
            self.assertEqual("success", result_json["status"])
    def test_learning_artifact_write_failure_skips_knowledge_and_is_partial_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            orchestrator = Orchestrator(repository, HarnessConfig(provider="local"), ScriptedProvider())
            orchestrator.canonical = FailingCanonicalDocs()
            result = run_with_flow(
                orchestrator,
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("partial success", result.outcome)
            self.assertTrue(any("Learning failed; knowledge proposal skipped" in warning for warning in result.warnings))
            self.assertNotIn("published/learning-proposals.json", result.artifacts)
            entries = SQLiteKnowledgeStore(repository / ".ai-harness/knowledge.db").list_recent()
            self.assertEqual([], entries)


if __name__ == "__main__":
    unittest.main()
