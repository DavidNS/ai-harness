from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "harness"
sys.path.insert(0, str(PACKAGE))

from ai_harness.knowledge_source import (  # noqa: E402
    KnowledgeSourceError,
    apply_knowledge_review,
    parse_knowledge_review,
    parse_learning_proposal,
    reconciliation_job,
    reduce_reconciliation_decision,
    render_jsonl,
    select_candidate_cluster,
    validate_repository_evidence_policy,
)
from tests.fixtures.scripted_provider import learning_output  # noqa: E402


class KnowledgeSourceContractTests(unittest.TestCase):
    def claim(self, **overrides: object) -> dict[str, object]:
        claim = json.loads(learning_output())["proposed_claims"][0]
        claim.update(overrides)
        return claim

    def test_parse_learning_proposal_normalizes_claims_and_jsonl(self) -> None:
        bundle = parse_learning_proposal(learning_output())
        self.assertEqual("proposal.deterministic-offline-completion.001", bundle.manifest["proposal_id"])
        self.assertEqual("claim.deterministic-offline-completion.001", bundle.claims[0]["id"])
        self.assertEqual("active", bundle.claims[0]["status"])
        self.assertTrue(render_jsonl(bundle.claims).endswith("\n"))

    def test_claims_without_evidence_must_be_unverified(self) -> None:
        document = json.loads(learning_output())
        document["proposed_claims"][0]["evidence"] = []
        with self.assertRaises(KnowledgeSourceError):
            parse_learning_proposal(json.dumps(document))
        document["proposed_claims"][0]["status"] = "unverified"
        parse_learning_proposal(json.dumps(document))


    def test_active_claim_requires_repository_backed_evidence_policy(self) -> None:
        document = json.loads(learning_output())
        document["proposed_claims"][0]["evidence"] = [{"type": "run_artifact", "artifact": "implementation/T1/1.md"}]
        bundle = parse_learning_proposal(json.dumps(document))
        with self.assertRaises(KnowledgeSourceError):
            validate_repository_evidence_policy(bundle)

    def test_repository_evidence_policy_accepts_existing_repo_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "feature.py").write_text("ready\n", encoding="utf-8")
            bundle = parse_learning_proposal(learning_output())
            validate_repository_evidence_policy(bundle, root)

    def test_repository_evidence_policy_rejects_generated_paths(self) -> None:
        document = json.loads(learning_output())
        document["proposed_claims"][0]["files"] = [".ai-harness/runs/out.txt"]
        document["proposed_claims"][0]["evidence"] = [{"type": "code", "file": ".ai-harness/runs/out.txt"}]
        bundle = parse_learning_proposal(json.dumps(document))
        with self.assertRaises(KnowledgeSourceError):
            validate_repository_evidence_policy(bundle)

    def test_unverified_claim_may_omit_repository_evidence(self) -> None:
        document = json.loads(learning_output())
        claim = document["proposed_claims"][0]
        claim["status"] = "unverified"
        claim["files"] = []
        claim["evidence"] = []
        bundle = parse_learning_proposal(json.dumps(document))
        validate_repository_evidence_policy(bundle)

    def test_active_run_summary_text_is_left_to_semantic_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "feature.py").write_text("ready\n", encoding="utf-8")
            document = json.loads(learning_output())
            document["proposed_claims"][0]["text"] = "The run completed offline using deterministic gates."
            bundle = parse_learning_proposal(json.dumps(document))
            validate_repository_evidence_policy(bundle, root)

    def test_ai_review_downgrades_active_run_claims_to_unverified(self) -> None:
        document = json.loads(learning_output())
        document["proposed_claims"][0]["text"] = "The run completed offline using deterministic gates."
        bundle = parse_learning_proposal(json.dumps(document))
        review = parse_knowledge_review(json.dumps({
            "schema_version": 1,
            "phase": "knowledge_review",
            "proposal_id": bundle.manifest["proposal_id"],
            "claim_reviews": [{
                "claim_id": bundle.claims[0]["id"],
                "decision": "downgrade",
                "reason": "process narration is not durable repository knowledge",
            }],
            "relation_reviews": [],
        }))
        claims, changed = apply_knowledge_review(bundle, review)
        self.assertEqual(1, len(changed))
        self.assertEqual("downgrade", changed[0]["decision"])
        self.assertEqual("unverified", claims[0]["status"])
        self.assertEqual("process narration is not durable repository knowledge", claims[0]["metadata"]["unverified_reason"])
        self.assertEqual("ai_knowledge_review", claims[0]["metadata"]["quality_gate"])

    def test_ai_review_reject_for_repair_requires_suggested_text(self) -> None:
        document = json.loads(learning_output())
        bundle = parse_learning_proposal(json.dumps(document))
        with self.assertRaises(KnowledgeSourceError):
            parse_knowledge_review(json.dumps({
                "schema_version": 1,
                "phase": "knowledge_review",
                "proposal_id": bundle.manifest["proposal_id"],
                "claim_reviews": [{
                    "claim_id": bundle.claims[0]["id"],
                    "decision": "reject_for_repair",
                    "reason": "claim text is not reviewable without context",
                }],
                "relation_reviews": [],
            }))

    def test_ai_review_flags_evidence_type_conflict(self) -> None:
        document = json.loads(learning_output())
        document["proposed_claims"][0]["evidence"] = [{"type": "documentation", "file": "ai-harness"}]
        bundle = parse_learning_proposal(json.dumps(document))
        review = parse_knowledge_review(json.dumps({
            "schema_version": 1,
            "phase": "knowledge_review",
            "proposal_id": bundle.manifest["proposal_id"],
            "claim_reviews": [{
                "claim_id": bundle.claims[0]["id"],
                "decision": "downgrade",
                "reason": "evidence_type_conflict",
            }],
            "relation_reviews": [],
        }))
        claims, changed = apply_knowledge_review(bundle, review)
        self.assertEqual(1, len(changed))
        self.assertEqual("unverified", claims[0]["status"])
        self.assertEqual("evidence_type_conflict", claims[0]["metadata"]["unverified_reason"])

    def test_active_repository_fact_text_with_repo_evidence_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "feature.py").write_text("ready\n", encoding="utf-8")
            bundle = parse_learning_proposal(learning_output(text="feature.py defines the deterministic fixture behavior."))
            validate_repository_evidence_policy(bundle, root)

    def test_candidate_cluster_is_bounded_and_explained(self) -> None:
        new_claim = self.claim(id="claim.harness.new")
        accepted = [
            self.claim(id="claim.harness.match", subjects=["DeterministicOfflineCompletion"]),
            self.claim(id="claim.other", domain="other", subjects=["Other"], files=["other.py"]),
        ]
        cluster = select_candidate_cluster(new_claim, accepted, limit=1)
        self.assertEqual(1, len(cluster))
        self.assertEqual("claim.harness.match", cluster[0]["claim"]["id"])
        self.assertIn("domain", cluster[0]["reasons"])

    def test_reconciliation_job_and_reducer_are_deterministic(self) -> None:
        new_claim = self.claim(id="claim.harness.new")
        job = reconciliation_job("job.harness.001", "Harness domain summary.", new_claim, [])
        self.assertEqual("job.harness.001", job["job_id"])
        patch = reduce_reconciliation_decision("supersedes", new_claim, ["claim.harness.old"], rationale="newer evidence")
        self.assertEqual(["add", "supersede"], [item["operation"] for item in patch["operations"]])
        review = reduce_reconciliation_decision("needs_human", new_claim, ["claim.harness.old"])
        self.assertEqual([], review["operations"])
        self.assertEqual("claim.harness.new", review["review_tasks"][0]["claim_id"])


if __name__ == "__main__":
    unittest.main()
