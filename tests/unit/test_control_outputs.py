from __future__ import annotations

import json
import unittest

from ai_harness.control_outputs import parse_control_output, parse_decision_answer
from ai_harness.errors import ValidationError


GRAPH = (
    "EXPLORE_BUNDLE", "PROPOSAL_BUNDLE", "SPEC_BUNDLE",
    "DESIGN_BUNDLE", "TASKS_BUNDLE", "TDD_BUNDLE",
)


class ControlOutputTests(unittest.TestCase):
    def test_decision_request_parses_and_normal_json_is_ignored(self) -> None:
        normal = json.dumps({"schema_version": 1, "phase": "tasks", "tasks": []})
        self.assertIsNone(parse_control_output(normal, expected_origin="TASKS", active_graph_phase="TASKS_BUNDLE", graph=GRAPH))

        request = parse_control_output(json.dumps({
            "schema_version": 1,
            "kind": "decision_request",
            "origin_phase": "DESIGN",
            "reason": "Two compatible designs exist.",
            "question": "Should compatibility be preserved?",
            "context": ["Preserving compatibility is lower risk."],
            "options": [{"id": "yes", "label": "Preserve", "consequence": "Adapter code is required."}],
            "allows_freeform": True,
            "scores": {"explore_bundle": 8, "sdd": 3},
            "score_signals": {"explorer": ["explorer_language+4"]},
            "ranked_paths": ["explore_bundle", "sdd"],
            "option_details": {"yes": "Preserves existing behavior for callers."},
        }), expected_origin="DESIGN", active_graph_phase="DESIGN_BUNDLE", graph=GRAPH)

        self.assertEqual("decision_request", request.kind)
        self.assertEqual("DESIGN", request.origin_phase)
        self.assertEqual("yes", request.options[0].id)
        self.assertEqual({"explore_bundle": 8, "sdd": 3}, request.scores)
        self.assertEqual(("explorer_language+4",), request.score_signals["explorer"])
        self.assertEqual(("explore_bundle", "sdd"), request.ranked_paths)
        self.assertEqual("Preserves existing behavior for callers.", request.option_details["yes"])
        self.assertEqual({"explore_bundle": 8, "sdd": 3}, request.to_dict()["scores"])
        self.assertEqual({"yes": "Preserves existing behavior for callers."}, request.to_dict()["option_details"])

    def test_rejects_mismatched_decision_origin(self) -> None:
        with self.assertRaises(ValidationError):
            parse_control_output(json.dumps({
                "schema_version": 1,
                "kind": "decision_request",
                "origin_phase": "SPEC",
                "reason": "A decision is needed.",
                "question": "Which behavior should be used?",
                "context": ["The active phase is design."],
            }), expected_origin="DESIGN", active_graph_phase="DESIGN_BUNDLE", graph=GRAPH)

    def test_escalation_must_target_earlier_graph_phase(self) -> None:
        valid = parse_control_output(json.dumps({
            "schema_version": 1,
            "kind": "phase_escalation",
            "origin_phase": "DESIGN",
            "target_phase": "SPEC_BUNDLE",
            "reason": "The answer changes acceptance criteria.",
        }), expected_origin="DESIGN", active_graph_phase="DESIGN_BUNDLE", graph=GRAPH)
        self.assertEqual("SPEC_BUNDLE", valid.target_phase)

        with self.assertRaises(ValidationError):
            parse_control_output(json.dumps({
                "schema_version": 1,
                "kind": "phase_escalation",
                "origin_phase": "DESIGN",
                "target_phase": "DESIGN",
                "reason": "Not a backward escalation.",
            }), expected_origin="DESIGN", active_graph_phase="DESIGN_BUNDLE", graph=GRAPH)

    def test_impossible_requires_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            parse_control_output(json.dumps({
                "schema_version": 1,
                "kind": "impossible",
                "origin_phase": "IMPLEMENT",
                "reason": "Cannot be done.",
                "evidence": [],
            }), expected_origin="IMPLEMENT", active_graph_phase="TDD_LOOP", graph=GRAPH)

    def test_explorer_decision_origin_is_validated(self) -> None:
        graph = ("INITIALIZING", "ROUTING", "SELECTING_STRATEGY", "EXPLORER_INTAKE", "EXPLORER_DISCOVERY", "EXPLORER_DECISION", "EXPLORER_ARTIFACT", "EXPLORER_REVIEW", "COMPLETED")
        request = parse_control_output(json.dumps({
            "schema_version": 1,
            "kind": "decision_request",
            "origin_phase": "EXPLORER",
            "reason": "A product decision is needed.",
            "question": "Should compatibility be preserved?",
            "context": ["This changes the implementation path."],
            "options": [],
        }), expected_origin="EXPLORER", active_graph_phase="EXPLORER_REVIEW", graph=graph)
        self.assertEqual("EXPLORER", request.origin_phase)

    def test_explorer_bundle_parses_entries(self) -> None:
        graph = ("INITIALIZING", "ROUTING", "SELECTING_STRATEGY", "EXPLORER_INTAKE", "EXPLORER_DISCOVERY", "EXPLORER_DECISION", "EXPLORER_ARTIFACT", "EXPLORER_REVIEW", "COMPLETED")
        bundle = parse_control_output(json.dumps({
            "schema_version": 1,
            "kind": "explorer_bundle",
            "origin_phase": "EXPLORER",
            "primary_entry": "create-routing",
            "entries": [{
                "id": "create-routing",
                "action": "create",
                "artifact_kind": "improvement",
                "title": "Improve routing",
                "content": "# Improvement: Improve Routing\n## Status\nProposed\n## Problem\nP\n## Evidence\nE\n## Desired Behavior\nD\n## Implementation Notes\nN\n## Acceptance Criteria\n- A\n",
            }, {
                "id": "skip-duplicate",
                "action": "no-op",
                "title": "Existing artifact",
                "path": "docs/explorer/improvements/existing/improvement.md",
                "reason": "Related artifact already covers the behavior.",
            }],
        }), expected_origin="EXPLORER", active_graph_phase="EXPLORER_ARTIFACT", graph=graph)

        self.assertEqual("explorer_bundle", bundle.kind)
        self.assertEqual("create-routing", bundle.primary_entry)
        self.assertEqual("create", bundle.entries[0].action)
        self.assertEqual("no-op", bundle.entries[1].action)
        self.assertEqual("docs/explorer/improvements/existing/improvement.md", bundle.entries[1].path)

    def test_explorer_bundle_rejects_invalid_entries(self) -> None:
        graph = ("INITIALIZING", "ROUTING", "SELECTING_STRATEGY", "EXPLORER_INTAKE", "EXPLORER_DISCOVERY", "EXPLORER_DECISION", "EXPLORER_ARTIFACT", "EXPLORER_REVIEW", "COMPLETED")
        with self.assertRaises(ValidationError):
            parse_control_output(json.dumps({
                "schema_version": 1,
                "kind": "explorer_bundle",
                "origin_phase": "DESIGN",
                "entries": [],
            }), expected_origin="DESIGN", active_graph_phase="DESIGN_BUNDLE", graph=GRAPH)
        with self.assertRaises(ValidationError):
            parse_control_output(json.dumps({
                "schema_version": 1,
                "kind": "explorer_bundle",
                "origin_phase": "EXPLORER",
                "entries": [{
                    "id": "bad-update",
                    "action": "update",
                    "title": "Bad update",
                    "path": "docs/explorer/improvements/a/improvement.md",
                    "content": "# Improvement: A\n",
                }],
            }), expected_origin="EXPLORER", active_graph_phase="EXPLORER_ARTIFACT", graph=graph)

    def test_decision_answer_accepts_text_or_matching_json(self) -> None:
        freeform = parse_decision_answer("Preserve compatibility.", pending_decision_id="D1")
        self.assertEqual("D1", freeform.decision_id)
        self.assertEqual("Preserve compatibility.", freeform.answer)

        structured = parse_decision_answer(json.dumps({
            "schema_version": 1,
            "kind": "decision_answer",
            "decision_id": "D1",
            "answer": "Preserve compatibility.",
            "selected_option": "yes",
        }), pending_decision_id="D1")
        self.assertEqual("yes", structured.selected_option)

        with self.assertRaises(ValidationError):
            parse_decision_answer(json.dumps({
                "schema_version": 1,
                "kind": "decision_answer",
                "decision_id": "D2",
                "answer": "Wrong decision.",
            }), pending_decision_id="D1")


if __name__ == "__main__":
    unittest.main()
