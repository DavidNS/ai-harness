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




class TestSimpleKnowledgeLoading(unittest.TestCase):
    def test_loading_phase_refreshes_knowledge_from_canonical_learning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            database = repository / ".ai-harness" / "knowledge.db"

            with SQLiteKnowledgeStore(database) as knowledge:
                knowledge.add_entry(
                    KnowledgeEntry(
                        "docs/knowledge-db/stale-feature/learning.md",
                        "stale-run",
                        "Old knowledge should be replaced by canonical refresh.",
                    )
                )

            stale = repository / "docs" / "knowledge-db" / "known-feature" / "learning.md"
            stale.parent.mkdir(parents=True)
            stale.write_text(
                "# Learning v2\n"
                "## Title\nKnown feature\n"
                "## Summary\nKnown behavior exists and is stable.\n"
                "## Decisions\nUse deterministic gates.\n"
                "## Patterns\nKnowledge-first implementation.\n"
                "## Errors\nNone.\n"
                "## Solutions\nCanonical refresh updates the cache.\n"
                "## Keywords\nknown, refresh\n",
                encoding="utf-8",
            )

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ScriptedProvider()),
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("success", result.outcome)
            entries = SQLiteKnowledgeStore(database).list_recent()
            self.assertEqual(1, len(entries))
            self.assertEqual("canonical", entries[0].run_id)
            self.assertEqual("docs/knowledge-db/known-feature/learning.md", entries[0].id)
            self.assertEqual("Known behavior exists and is stable.", entries[0].summary)
    def test_loading_knowledge_warns_when_remote_freshness_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            (repository / "seed.txt").write_text("seed\n", encoding="utf-8")
            subprocess.run(["git", "-C", repository, "config", "user.name", "Test User"], check=True)
            subprocess.run(["git", "-C", repository, "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", repository, "add", "seed.txt"], check=True)
            subprocess.run(["git", "-C", repository, "commit", "-m", "seed"], check=True)

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ScriptedProvider()),
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("success", result.outcome)
            self.assertTrue(any(
                "Knowledge freshness could not be verified because no upstream or default branch is available." in warning
                for warning in result.warnings
            ))
    def test_loading_knowledge_warns_when_local_branch_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            remote = Path(directory) / "origin.git"
            collaborator = Path(directory) / "collaborator"
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(["git", "-C", repository, "config", "user.name", "Test User"], check=True)
            subprocess.run(["git", "-C", repository, "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", repository, "branch", "-M", "main"], check=True)
            (repository / "seed.txt").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "-C", repository, "add", "seed.txt"], check=True)
            subprocess.run(["git", "-C", repository, "commit", "-m", "seed"], check=True)
            subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
            subprocess.run(["git", "-C", repository, "remote", "add", "origin", str(remote)], check=True)
            subprocess.run(["git", "-C", repository, "push", "-u", "origin", "main"], check=True)
            subprocess.run(["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)

            subprocess.run(["git", "clone", "-q", str(remote), str(collaborator)], check=True)
            subprocess.run(["git", "-C", collaborator, "config", "user.name", "Test User"], check=True)
            subprocess.run(["git", "-C", collaborator, "config", "user.email", "test@example.com"], check=True)
            (collaborator / "remote-only.txt").write_text("advanced\n", encoding="utf-8")
            subprocess.run(["git", "-C", collaborator, "checkout", "-b", "stale"], check=True)
            subprocess.run(["git", "-C", collaborator, "add", "remote-only.txt"], check=True)
            subprocess.run(["git", "-C", collaborator, "commit", "-m", "advance"], check=True)
            subprocess.run(["git", "-C", collaborator, "push", "origin", "stale:main"], check=True)
            subprocess.run(["git", "-C", repository, "fetch", "origin"], check=True)

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ScriptedProvider()),
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("success", result.outcome)
            self.assertTrue(any(
                "Knowledge cache may be stale; current branch main is behind origin/main" in warning
                for warning in result.warnings
            ))
    def test_duplicate_learning_creates_reorganization_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            existing = repository / "docs" / "knowledge-db" / "offline-controller" / "learning.md"
            existing.parent.mkdir(parents=True)
            existing.write_text(
                "# Learning v2\n"
                "## Title\nOffline controller behavior\n"
                "## Summary\nCompleted offline.\n"
                "## Decisions\nUse deterministic gates.\n"
                "## Patterns\nArtifact-driven work.\n"
                "## Errors\nNone.\n"
                "## Solutions\nController validation.\n"
                "## Keywords\noffline, controller\n",
                encoding="utf-8",
            )

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), ScriptedProvider()),
                "Fix typo in README.md",
                "sdd_low",
            )

            self.assertEqual("success", result.outcome)
            self.assertFalse(any("Possible duplicate knowledge" in warning for warning in result.warnings))
            self.assertFalse((repository / "docs/knowledge-db/deterministic-offline-completion/learning.md").exists())
            self.assertFalse((repository / "docs/analysis/improvements/reorganize-knowledge-db/improvement.md").exists())
            self.assertTrue((repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposed_claims.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
