from __future__ import annotations

import unittest

from harness_v2.adapters.storage import InMemoryKnowledgePatchStore
from harness_v2.backend.domain.errors import DomainValidationError
from harness_v2.backend.domain.knowledge import KnowledgePatchStatus, parse_learning_proposal
from harness_v2.backend.domain.lifecycle import PhaseName
from harness_v2.backend.ports.knowledge_patch_store import KnowledgePatchNotFoundError


TIMESTAMP = "2026-07-01T00:00:00+00:00"


def proposal(**overrides: object) -> object:
    value = {
        "schema_version": 1,
        "phase": "learning",
        "proposal_manifest": {
            "schema_version": 1,
            "proposal_id": "proposal.v2.explore.001",
            "summary": "Candidate knowledge.",
            "source_artifacts": ["explore/outcome_bundle.json"],
            "claims_file": "proposed_claims.jsonl",
        },
        "proposed_claims": [{
            "id": "claim.v2.explore.001",
            "domain": "harness",
            "subjects": ["KnowledgeLifecycle"],
            "files": ["harness_v2/backend/domain/lifecycle.py"],
            "symbols": [],
            "claim_type": "behavior",
            "text": "The v2 lifecycle supports candidate knowledge patches.",
            "status": "active",
            "evidence": [{"type": "code", "file": "harness_v2/backend/domain/lifecycle.py"}],
            "valid_from": None,
            "valid_until": None,
            "last_verified": None,
        }],
        "proposed_relations": [],
    }
    value.update(overrides)
    return value


class KnowledgePatchDomainTests(unittest.TestCase):
    def test_learning_proposal_validation_normalizes_candidate_claims(self) -> None:
        bundle = parse_learning_proposal(proposal())

        self.assertEqual("proposal.v2.explore.001", bundle.manifest["proposal_id"])
        self.assertEqual("claim.v2.explore.001", bundle.claims[0]["id"])

    def test_malformed_or_unsupported_proposals_fail_closed(self) -> None:
        cases = (
            {"schema_version": 2},
            {"phase": "knowledge_review"},
            {"proposed_claims": []},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(DomainValidationError):
                    parse_learning_proposal(proposal(**overrides))

    def test_active_claims_require_evidence(self) -> None:
        value = proposal()
        value["proposed_claims"][0]["evidence"] = []

        with self.assertRaises(DomainValidationError):
            parse_learning_proposal(value)

        value["proposed_claims"][0]["status"] = "unverified"
        value["proposed_claims"][0]["files"] = []
        parse_learning_proposal(value)


class InMemoryKnowledgePatchStoreTests(unittest.TestCase):
    def test_create_list_read_and_reject_candidate_patches(self) -> None:
        store = InMemoryKnowledgePatchStore()
        bundle = parse_learning_proposal(proposal())

        first = store.create_patch("run-1", PhaseName.EXPLORE_BUNDLE, bundle, TIMESTAMP)
        second = store.create_patch("run-1", PhaseName.EXPLORE_BUNDLE, bundle, TIMESTAMP)
        rejected = store.reject_patch(first.patch_id, "not durable", TIMESTAMP)

        self.assertEqual("patch.run-1.explore_bundle.v0001", first.patch_id)
        self.assertEqual("patch.run-1.explore_bundle.v0002", second.patch_id)
        self.assertEqual(KnowledgePatchStatus.REJECTED, rejected.status)
        self.assertEqual((second,), store.list_patches(run_id="run-1", status=KnowledgePatchStatus.CANDIDATE))
        self.assertEqual(rejected, store.get_patch(first.patch_id))

    def test_missing_patch_fails_closed(self) -> None:
        with self.assertRaises(KnowledgePatchNotFoundError):
            InMemoryKnowledgePatchStore().get_patch("patch.missing")


if __name__ == "__main__":
    unittest.main()
