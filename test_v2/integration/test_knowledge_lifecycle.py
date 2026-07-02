from __future__ import annotations

import unittest

from test_v2.support.runtime import memory_orchestrator
from harness_v2.backend.application.contracts import GetKnowledgePatch, ListKnowledgePatches, RejectKnowledgePatch
from harness_v2.backend.domain.knowledge import parse_learning_proposal
from harness_v2.backend.domain.lifecycle import BundleName


def proposal() -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "learning",
        "proposal_manifest": {"schema_version": 1, "proposal_id": "proposal.v2.001", "summary": "Learn", "source_artifacts": ["explore/outcome_bundle.json"], "claims_file": "proposed_claims.jsonl"},
        "proposed_claims": [{"id": "claim.v2.001", "domain": "harness", "subjects": ["v2"], "files": ["harness_v2/backend/domain/lifecycle.py"], "symbols": [], "claim_type": "behavior", "text": "Bundles compose phases.", "status": "active", "evidence": [{"type": "code", "file": "harness_v2/backend/domain/lifecycle.py"}], "valid_from": None, "valid_until": None, "last_verified": None}],
        "proposed_relations": [],
    }


class KnowledgeLifecycleIntegrationTests(unittest.TestCase):
    def test_knowledge_patch_queries_and_reject_flow(self) -> None:
        service, _state, _artifacts, knowledge = memory_orchestrator()
        patch = knowledge.create_patch("run-1", BundleName.EXPLORE_BUNDLE, parse_learning_proposal(proposal()), "created")

        listed = service.query(ListKnowledgePatches(run_id="run-1"))
        fetched = service.query(GetKnowledgePatch(patch.patch_id))
        rejected = service.execute(RejectKnowledgePatch(patch.patch_id, "not useful"))

        self.assertEqual((patch.patch_id,), tuple(item.patch_id for item in listed.patches))
        self.assertEqual(patch.patch_id, fetched.patch.patch_id)
        self.assertEqual("REJECTED", rejected.patch.status)


if __name__ == "__main__":
    unittest.main()
