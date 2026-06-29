from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "harness"
sys.path.insert(0, str(PACKAGE))

from ai_harness.actions import ActionMediator, ActionRequest
from ai_harness.capabilities import CapabilityError, CapabilityManifest, CapabilityPolicy


def manifest() -> CapabilityManifest:
    return CapabilityManifest.from_mapping({
        "schema_version": 1,
        "phase": "proposal",
        "paths": [{"pattern": "**", "mode": "read"}],
        "commands": [],
        "skills": ["proposal-playbook"],
        "mcp_tools": [{"server": "jira", "name": "create", "access": "mutate", "arguments": ["title"]}],
        "required_evidence": ["phase_output"],
        "postconditions": ["record_exists"],
        "limits": {"timeout_seconds": 10, "output_bytes": 1000, "retries": 1},
    })


class ActionTests(unittest.TestCase):
    def test_action_is_verified_persisted_and_replayed_once(self) -> None:
        calls = []

        def execute(server, tool, arguments):
            calls.append((server, tool, arguments))
            return {"id": "REQ-1", "title": arguments["title"]}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mediator = ActionMediator(
                CapabilityPolicy(manifest(), root), root / "evidence", execute,
                lambda condition, arguments, result: condition == "record_exists" and bool(result.get("id")),
            )
            request = ActionRequest("jira", "create", {"title": "Requirement"}, "run-1:create", ("record_exists",))
            first = mediator.execute(request)
            second = mediator.execute(request)
            self.assertFalse(first.replayed)
            self.assertTrue(second.replayed)
            self.assertEqual(1, len(calls))

    def test_duplicate_key_with_different_arguments_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mediator = ActionMediator(CapabilityPolicy(manifest(), root), root / "evidence", lambda *_: {"id": "1"}, lambda *_: True)
            mediator.execute(ActionRequest("jira", "create", {"title": "A"}, "same", ("record_exists",)))
            with self.assertRaises(CapabilityError):
                mediator.execute(ActionRequest("jira", "create", {"title": "B"}, "same", ("record_exists",)))

    def test_failed_postcondition_is_not_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mediator = ActionMediator(CapabilityPolicy(manifest(), root), root / "evidence", lambda *_: {"id": "1"}, lambda *_: False)
            with self.assertRaises(CapabilityError):
                mediator.execute(ActionRequest("jira", "create", {"title": "A"}, "failure", ("record_exists",)))
            self.assertEqual([], list((root / "evidence").glob("*.json")))


if __name__ == "__main__":
    unittest.main()
