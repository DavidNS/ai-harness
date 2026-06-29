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




class TestSimpleTaskPipeline(unittest.TestCase):
    def test_typo_uses_one_task_without_empty_sdd_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            provider = ScriptedProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Fix typo in README.md",
                "sdd_low",
            )
            self.assertEqual(["implement", "review", "knowledge_synthesis", "knowledge_review"], provider.calls)
            self.assertEqual("success", result.outcome)
            snapshot = provider.phase_inputs["knowledge_synthesis"][0]["repository_snapshot"]
            self.assertIn("feature.py", [item["path"] for item in snapshot["entries"]])
            self.assertIn("tasks.json", result.artifacts)
            self.assertNotIn("explore.md", result.artifacts)
            self.assertNotIn("purpose.md", result.artifacts)
            self.assertNotIn("spec.md", result.artifacts)
            self.assertNotIn("design.md", result.artifacts)


if __name__ == "__main__":
    unittest.main()
