from __future__ import annotations

import unittest

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.json_schema import validate_json_schema


def _knowledge_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "learning",
        "proposal_manifest": {
            "schema_version": 1,
            "proposal_id": "proposal.v2.test.001",
            "summary": "Learn from the run.",
            "source_artifacts": ["explore/outcome_bundle.json"],
            "claims_file": "proposed_claims.jsonl",
        },
        "proposed_claims": [{
            "id": "claim.v2.test.001",
            "domain": "harness",
            "subjects": ["V2Harness"],
            "files": ["harness_v2/backend/domain/lifecycle.py"],
            "symbols": [],
            "claim_type": "behavior",
            "text": "The v2 harness composes bundles from phases.",
            "status": "active",
            "evidence": [{"type": "code", "file": "harness_v2/backend/domain/lifecycle.py"}],
            "valid_from": None,
            "valid_until": None,
            "last_verified": None,
        }],
        "proposed_relations": [],
    }


class OutputSchemaTests(unittest.TestCase):
    def test_knowledge_synthesis_schema_accepts_learning_proposal_shape(self) -> None:
        validate_json_schema(_knowledge_payload(), "knowledge_synthesis")

    def test_knowledge_synthesis_schema_rejects_empty_claims(self) -> None:
        payload = _knowledge_payload()
        payload["proposed_claims"] = []

        with self.assertRaises(BundleValidationError):
            validate_json_schema(payload, "knowledge_synthesis")

    def test_json_artifact_delta_schema_accepts_repair_delta(self) -> None:
        validate_json_schema(
            {
                "schema_version": 1,
                "kind": "json_artifact_delta",
                "target_artifact": "tasks.json",
                "operations": [{"op": "add", "path": "/tasks/0/focused_tests", "value": [["python3", "-m", "unittest"]]}],
            },
            "json_artifact_delta",
        )

    def test_json_artifact_delta_schema_requires_values_for_add_and_replace(self) -> None:
        with self.assertRaises(BundleValidationError):
            validate_json_schema(
                {
                    "schema_version": 1,
                    "kind": "json_artifact_delta",
                    "target_artifact": "tasks.json",
                    "operations": [{"op": "add", "path": "/tasks/0/focused_tests"}],
                },
                "json_artifact_delta",
            )



if __name__ == "__main__":
    unittest.main()
