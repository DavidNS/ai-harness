from __future__ import annotations

import unittest

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.json_delta import apply_json_artifact_delta


class JsonArtifactDeltaTests(unittest.TestCase):
    def test_add_replace_and_remove_nested_values(self) -> None:
        result = apply_json_artifact_delta(
            {
                "schema_version": 1,
                "kind": "json_artifact_delta",
                "target_artifact": "tasks.json",
                "operations": [
                    {"op": "add", "path": "/tasks/0/focused_tests", "value": [["python3", "-m", "unittest"]]},
                    {"op": "replace", "path": "/tasks/0/status", "value": "pending"},
                    {"op": "remove", "path": "/tasks/0/obsolete"},
                ],
            },
            target_artifact="tasks.json",
            current_artifact={"tasks": [{"status": "draft", "obsolete": True}]},
        )

        self.assertEqual([["python3", "-m", "unittest"]], result["tasks"][0]["focused_tests"])
        self.assertEqual("pending", result["tasks"][0]["status"])
        self.assertNotIn("obsolete", result["tasks"][0])

    def test_root_add_can_create_missing_artifact(self) -> None:
        result = apply_json_artifact_delta(
            {
                "schema_version": 1,
                "kind": "json_artifact_delta",
                "target_artifact": "spec.json",
                "operations": [{"op": "add", "path": "", "value": {"schema_version": 1}}],
            },
            target_artifact="spec.json",
            current_artifact=None,
        )

        self.assertEqual({"schema_version": 1}, result)

    def test_rejects_wrong_target_and_unsupported_operation(self) -> None:
        with self.assertRaises(BundleValidationError):
            apply_json_artifact_delta(
                {"schema_version": 1, "kind": "json_artifact_delta", "target_artifact": "other.json", "operations": [{"op": "add", "path": "/x", "value": 1}]},
                target_artifact="tasks.json",
                current_artifact={},
            )
        with self.assertRaises(BundleValidationError):
            apply_json_artifact_delta(
                {"schema_version": 1, "kind": "json_artifact_delta", "target_artifact": "tasks.json", "operations": [{"op": "move", "path": "/x"}]},
                target_artifact="tasks.json",
                current_artifact={},
            )

    def test_rejects_invalid_json_pointer(self) -> None:
        with self.assertRaises(BundleValidationError):
            apply_json_artifact_delta(
                {"schema_version": 1, "kind": "json_artifact_delta", "target_artifact": "tasks.json", "operations": [{"op": "add", "path": "tasks/0", "value": 1}]},
                target_artifact="tasks.json",
                current_artifact={},
            )


if __name__ == "__main__":
    unittest.main()
