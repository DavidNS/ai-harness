from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "harness"
sys.path.insert(0, str(PACKAGE))

from ai_harness.capabilities import CapabilityError, CapabilityManifest, CapabilityPolicy, load_manifest


class CapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]
        self.capabilities = self.root / "harness" / "capabilities"

    def test_all_phase_manifests_are_valid_and_only_implement_can_write(self) -> None:
        expected = {"explore", "purpose", "spec", "design", "tasks", "explore_request_understanding", "explore_clarification_gate", "explore_triage", "explore_evidence_plan", "explore_evidence_collection", "explore_ci_barrier", "explore_evidence_normalization", "explore_outcome_synthesis", "explore_review", "explore_request_profile", "explore_evidence_digest", "explore_delta", "explorer", "explorer_intake", "explorer_discovery", "explorer_decision", "explorer_artifact", "explorer_distill", "explorer_review", "implement", "test", "review", "learning", "knowledge_synthesis", "knowledge_review"}
        loaded = {path.stem: load_manifest(path) for path in self.capabilities.glob("*.json")}
        self.assertEqual(expected, set(loaded))
        writers = {name for name, manifest in loaded.items() if any(path.mode == "write" for path in manifest.paths)}
        self.assertEqual({"implement"}, writers)

    def test_unknown_fields_and_unsafe_paths_fail_closed(self) -> None:
        data = json.loads((self.capabilities / "explore.json").read_text())
        data["unexpected"] = True
        with self.assertRaises(CapabilityError):
            CapabilityManifest.from_mapping(data)
        data.pop("unexpected")
        data["paths"] = [{"pattern": "../secret", "mode": "read"}]
        with self.assertRaises(CapabilityError):
            CapabilityManifest.from_mapping(data)

    def test_policy_denies_undeclared_operations_and_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = CapabilityPolicy(load_manifest(self.capabilities / "explore.json"), Path(directory))
            policy.authorize_path("README.md", "read")
            with self.assertRaises(CapabilityError):
                policy.authorize_path("README.md", "write")
            with self.assertRaises(CapabilityError):
                policy.authorize_command(["git", "status"], "worker")
            with self.assertRaises(CapabilityError):
                policy.authorize_tool("jira", "create", "mutate", {})
            with self.assertRaises(CapabilityError):
                policy.reject_escalation({"filesystem": "write"})

    def test_worker_projection_excludes_mutating_tools(self) -> None:
        data = json.loads((self.capabilities / "explore.json").read_text())
        data["mcp_tools"] = [
            {"server": "docs", "name": "search", "access": "read", "arguments": ["query"]},
            {"server": "jira", "name": "create", "access": "mutate", "arguments": ["title"]},
        ]
        permissions = CapabilityPolicy(CapabilityManifest.from_mapping(data), self.root).worker_permissions()
        self.assertEqual([{"server": "docs", "name": "search", "access": "read"}], permissions["mcp_tools"])


if __name__ == "__main__":
    unittest.main()
