from __future__ import annotations

import unittest

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.json_schema import validate_json_schema


class JsonSchemaValidationTests(unittest.TestCase):
    def test_request_profile_schema_accepts_valid_document(self) -> None:
        validate_json_schema(
            {
                "schema_version": 1,
                "phase": "explore_request_profile",
                "summary": "Fix tests",
                "request_type": "feature",
                "complexity": "local_change",
                "ambiguity": "clear",
                "risk": "low",
                "evidence_depth": "standard",
                "request_parts": ["Fix tests"],
                "constraints": [],
                "evidence_questions": ["What fails?"],
                "gatherers": ["code"],
                "clarification_questions": [],
            },
            "request_profile",
        )

    def test_request_profile_schema_rejects_missing_required_field(self) -> None:
        with self.assertRaises(BundleValidationError):
            validate_json_schema(
                {
                    "schema_version": 1,
                    "phase": "explore_request_profile",
                    "summary": "Fix tests",
                },
                "request_profile",
            )

    def test_schema_ref_rejects_invalid_nested_document(self) -> None:
        with self.assertRaises(BundleValidationError):
            validate_json_schema(
                {
                    "schema_version": 1,
                    "kind": "explore_context_pack",
                    "request": "Fix tests",
                    "profile": {"schema_version": 1, "phase": "explore_request_profile"},
                    "request_profile": {"schema_version": 1, "phase": "explore_request_profile"},
                    "decision_history": [],
                    "knowledge": [],
                    "related_improvements": [],
                    "repository_observations": [],
                    "git": {},
                    "ci_status": {},
                    "ci_digest": {},
                    "explorer_scope": {},
                },
                "context_pack",
            )


if __name__ == "__main__":
    unittest.main()
