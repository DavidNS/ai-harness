from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "harness"
sys.path.insert(0, str(PACKAGE))

from ai_harness.phases import PHASE_DEFINITIONS, PhaseValidationError, get_phase
from tests.fixtures.scripted_provider import explore_outcome_bundle, learning_output


class PhaseContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = Path(__file__).resolve().parents[2] / "harness"

    def test_every_phase_has_resources_and_matching_manifest(self) -> None:
        self.assertEqual(22, len(PHASE_DEFINITIONS))
        for phase in PHASE_DEFINITIONS.values():
            self.assertTrue((self.harness / "workers" / phase.playbook).is_file())
            self.assertTrue((self.harness / "prompts" / phase.prompt).is_file())
            self.assertEqual(phase.name, phase.load_manifest(self.harness).phase)

    def test_exact_inputs_are_required(self) -> None:
        phase = get_phase("purpose")
        supplied = {"request": "r", "explore_bundle_view": {"kind": "explore_bundle_view"}, "explorer_scope": {"artifacts": []}}
        self.assertEqual(supplied, phase.build_input(supplied))
        with self.assertRaises(PhaseValidationError):
            phase.build_input({"request": "r", "explore_bundle_view": {"kind": "explore_bundle_view"}})
        with self.assertRaises(PhaseValidationError):
            phase.build_input({"request": "r", "explore_bundle_view": {"kind": "explore_bundle_view"}, "explorer_scope": {}, "state": {}})

    def test_explore_outcome_bundle_accepts_exploration_map(self) -> None:
        document = json.loads(explore_outcome_bundle())

        validated = get_phase("explore_outcome_synthesis").validate(json.dumps(document))

        self.assertEqual("exploration_map", validated["exploration_map"]["kind"])
        self.assertEqual("direct_change", validated["exploration_map"]["candidate_work_shapes"][0]["shape"])

    def test_explore_outcome_bundle_rejects_invalid_exploration_map(self) -> None:
        invalid_shape = json.loads(explore_outcome_bundle())
        invalid_shape["exploration_map"]["candidate_work_shapes"][0]["shape"] = "refactor_required"
        with self.assertRaises(PhaseValidationError):
            get_phase("explore_outcome_synthesis").validate(json.dumps(invalid_shape))

        invalid_ref = json.loads(explore_outcome_bundle())
        invalid_ref["exploration_map"]["behaviors"][0]["evidence_refs"] = ["missing"]
        with self.assertRaises(PhaseValidationError):
            get_phase("explore_outcome_synthesis").validate(json.dumps(invalid_ref))

    def test_explore_prompts_name_allowed_source_types(self) -> None:
        for name in ("explore_evidence_digest.md", "explore_delta.md"):
            prompt = (self.harness / "prompts" / name).read_text(encoding="utf-8")
            self.assertIn("Allowed source type: file, artifact, git, gitlab, web, knowledge, ci", prompt)
            self.assertIn("Do not invent source types", prompt)
            self.assertIn("use source type artifact", prompt)

    def test_implement_prompt_names_required_markdown_contract(self) -> None:
        prompt = (self.harness / "prompts" / "implement.md").read_text(encoding="utf-8")
        for heading in ("# Implementation v1", "## Changes", "## Evidence"):
            self.assertIn(heading, prompt)

    def test_review_prompt_names_required_markdown_contract(self) -> None:
        prompt = (self.harness / "prompts" / "review.md").read_text(encoding="utf-8")
        for value in ("# Review v1", "## Verdict", "APPROVE", "REQUEST_CHANGES", "## Findings"):
            self.assertIn(value, prompt)

    def test_learning_prompt_names_required_json_contract(self) -> None:
        prompt = (self.harness / "prompts" / "learning.md").read_text(encoding="utf-8")
        for value in ("learning.json", "proposal_manifest", "proposed_claims", "claim_type", "evidence", "active", "unverified"):
            self.assertIn(value, prompt)

    def test_knowledge_synthesis_prompt_names_learning_contract_details(self) -> None:
        prompt = (self.harness / "prompts" / "knowledge_synthesis.md").read_text(encoding="utf-8")
        worker = (self.harness / "workers" / "knowledge_synthesis.md").read_text(encoding="utf-8")
        combined = prompt + "\n" + worker
        for value in (
            "claim.cli-ui.001",
            "do not use discovery IDs like `C1`",
            "claim_type",
            "valid_from",
            "Evidence objects must include `type`",
            "relation_type",
            "source",
            "target",
        ):
            self.assertIn(value, combined)

    def test_test_prompt_names_required_markdown_contract(self) -> None:
        prompt = (self.harness / "prompts" / "test.md").read_text(encoding="utf-8")
        for heading in ("# Tests v1", "## Commands", "## Results", "repair"):
            self.assertIn(heading, prompt)

    def test_explorer_distill_defaults_to_natural_acceptance_bullets(self) -> None:
        prompt = (self.harness / "prompts" / "explorer_distill.md").read_text(encoding="utf-8")
        worker = (self.harness / "workers" / "explorer_distill.md").read_text(encoding="utf-8")
        combined = prompt + "\n" + worker

        self.assertIn("natural-language Markdown bullets", combined)
        self.assertIn("Structured JSON is allowed", worker)
        self.assertNotIn("Return exactly this section", combined)
        self.assertNotIn("must be structured as a JSON array", combined)
        self.assertNotIn("<expected outcome>", combined)

    def test_explorer_contract_accepts_analysis_limitation_existing_and_compact_improvement(self) -> None:
        analysis = "# Improvement Analysis v1\n## Problem\nP\n## Context\nC\n## Findings\nF\n## Options\nO\n## Risks\nR\n## Recommendation\nGo.\n## Outcome\nimprovement\n## Open Questions\nNone.\n"
        limitation = "# Limitation v1\n## Problem\nP\n## Context\nC\n## Reasoning\nR\n## Outcome\nlimitation\n## Next Step\nStop.\n"
        existing = "# Existing Functionality v1\n## Problem\nP\n## Evidence\nE\n## Outcome\nexisting-functionality\n## Open Questions\nNone.\n"
        compact = "# Improvement: Compact Artifact\n## Status\nProposed\n## Problem\nP\n## Evidence\nE\n## Desired Behavior\nD\n## Implementation Notes\nN\n## Acceptance Criteria\n- A\n"
        self.assertEqual(analysis, get_phase("explorer").validate(analysis))
        self.assertEqual(limitation, get_phase("explorer").validate(limitation))
        self.assertEqual(existing, get_phase("explorer").validate(existing))
        self.assertEqual(compact, get_phase("explorer").validate(compact))
        with self.assertRaises(PhaseValidationError):
            get_phase("explorer").validate(analysis.replace("## Risks\nR\n", ""))

    def test_explorer_rejects_unresolved_factual_open_questions(self) -> None:
        analysis = "# Improvement Analysis v1\n## Problem\nP\n## Context\nC\n## Findings\nF\n## Options\nO\n## Risks\nR\n## Recommendation\nGo.\n## Outcome\nimprovement\n## Open Questions\nDoes the repository already support this?\n"
        existing = "# Existing Functionality v1\n## Problem\nP\n## Evidence\nE\n## Outcome\nexisting-functionality\n## Open Questions\nDocumentation may be missing.\n"
        compact = "# Improvement: Compact Artifact\n## Status\nProposed\n## Problem\nP\n## Evidence\nE\n## Desired Behavior\nD\n## Implementation Notes\nN\n## Acceptance Criteria\n- A\n## Open Questions\nNone.\n"
        for candidate in (analysis, existing, compact):
            with self.assertRaises(PhaseValidationError):
                get_phase("explorer").validate(candidate)


    def test_explorer_discovery_normalizes_info_critic_severity(self) -> None:
        discovery = {"schema_version": 1, "phase": "explorer_discovery", "claims": [{"id": "C1", "status": "resolved", "evidence": ["tests/test_a.py covers it."]}], "evidence_trace": [{"id": "T1", "claim_id": "C1", "source": "test", "path": "tests/test_a.py", "line_start": 1, "line_end": 1, "excerpt": "def test_a(): pass", "confidence": "high"}], "duplicate_search": {"searched_terms": ["gate"], "searched_surfaces": ["tests"], "matches": [], "no_match_claims": [{"claim_id": "C1", "searched_for": "duplicate gate", "confidence": "medium"}]}, "candidate_directions": [{"id": "D1", "title": "Gate decision value", "mechanism": "Validate decision fields before artifact synthesis.", "impact": "High", "confidence": "Medium", "cost": "Medium", "reversibility": "High", "evidence_strength": "Strong", "behavioral_delta": "Low-value decisions stop before artifact synthesis.", "evidence": ["harness/ai_harness/explorer_contracts.py"]}], "critic_findings": [{"direction_id": "D1", "severity": "info", "finding": "This is advisory.", "recommendation": "Treat it as a note."}], "related_improvements": [], "repository_observations": []}

        validated = get_phase("explorer_discovery").validate(json.dumps(discovery))

        self.assertEqual("note", validated["critic_findings"][0]["severity"])

    def test_explorer_discovery_requires_trace_and_preserved_observations(self) -> None:
        discovery = {"schema_version": 1, "phase": "explorer_discovery", "claims": [{"id": "C1", "status": "resolved", "evidence": ["Repository observations show tests/test_a.py covers it."]}], "evidence_trace": [{"id": "T1", "claim_id": "C1", "source": "test", "path": "tests/test_a.py", "excerpt": "def test_a(): pass", "confidence": "high"}], "duplicate_search": {"searched_terms": ["gate"], "searched_surfaces": ["tests"], "matches": [], "no_match_claims": [{"claim_id": "C1", "searched_for": "duplicate gate", "confidence": "medium"}]}, "candidate_directions": [], "critic_findings": [], "related_improvements": [], "repository_observations": []}
        with self.assertRaises(PhaseValidationError):
            get_phase("explorer_discovery").validate(json.dumps(discovery))

        discovery["repository_observations"] = [{"path": "tests/test_a.py"}]
        self.assertEqual(discovery, get_phase("explorer_discovery").validate(json.dumps(discovery)))

        discovery["evidence_trace"][0]["claim_id"] = "missing"
        with self.assertRaises(PhaseValidationError):
            get_phase("explorer_discovery").validate(json.dumps(discovery))

    def test_staged_explorer_value_fields_reject_malformed_outputs(self) -> None:
        bad_intake = {"schema_version": 1, "phase": "explorer_intake", "strategic_framing": {"mode": "unclear"}, "claims": [{"id": "C1", "class": "repository-factual", "text": "Check behavior."}], "synthesis_notes": []}
        bad_direction = {"schema_version": 1, "phase": "explorer_discovery", "claims": [{"id": "C1", "status": "resolved", "evidence": ["tests/test_a.py covers it."]}], "candidate_directions": [{"id": "D1", "title": "Missing value dimensions"}], "related_improvements": [], "repository_observations": []}
        bad_critic = {"schema_version": 1, "phase": "explorer_discovery", "claims": [{"id": "C1", "status": "resolved", "evidence": ["tests/test_a.py covers it."]}], "critic_findings": [{"direction_id": "D1", "severity": "fatal", "finding": "Bad severity", "recommendation": "Use a supported severity."}], "related_improvements": [], "repository_observations": []}
        bad_decision = {"schema_version": 1, "phase": "explorer_decision", "outcome": "new_improvement", "rationale": "Evidence supports it.", "evidence": ["tests/test_a.py covers it."], "value_hypothesis": " ", "rejected_alternatives": [{"id": "D2", "reason": "Lower value."}]}
        for phase, candidate in (("explorer_intake", bad_intake), ("explorer_discovery", bad_direction), ("explorer_discovery", bad_critic), ("explorer_decision", bad_decision)):
            with self.assertRaises(PhaseValidationError):
                get_phase(phase).validate(json.dumps(candidate))

    def test_learning_contract_rejects_malformed_proposals(self) -> None:
        valid = learning_output()
        self.assertEqual(valid, get_phase("learning").validate(valid))
        document = json.loads(valid)

        missing_evidence = json.loads(valid)
        missing_evidence["proposed_claims"][0]["evidence"] = []

        duplicate_ids = json.loads(valid)
        duplicate_ids["proposed_claims"].append(dict(duplicate_ids["proposed_claims"][0]))

        unsupported_status = json.loads(valid)
        unsupported_status["proposed_claims"][0]["status"] = "draft"

        missing_manifest = json.loads(valid)
        del missing_manifest["proposal_manifest"]

        invalid_candidates = (
            "# Learning v2\n## Title\nOld Markdown\n",
            json.dumps(missing_evidence),
            json.dumps(duplicate_ids),
            json.dumps(unsupported_status),
            json.dumps(missing_manifest),
        )
        for candidate in invalid_candidates:
            with self.assertRaises(PhaseValidationError):
                get_phase("learning").validate(candidate)

        document["proposed_claims"][0]["status"] = "unverified"
        document["proposed_claims"][0]["evidence"] = []
        self.assertEqual(json.dumps(document), get_phase("learning").validate(json.dumps(document)))

    def test_design_requires_all_test_design_sections(self) -> None:
        valid = """# Design v1
## Boundaries
B
## Invariants
I
## Implementation Approach
A
## Unit Test Design
U
## Integration Test Design
I
## End-to-End Test Design
Not applicable because there is no user-facing boundary.
"""
        self.assertEqual(valid, get_phase("design").validate(valid))
        with self.assertRaises(PhaseValidationError):
            get_phase("design").validate(valid.replace("## Integration Test Design\nI\n", ""))

    def test_tasks_require_dependency_order_and_test_commands(self) -> None:
        tasks = {"schema_version": 1, "phase": "tasks", "tasks": [
            {"id": "T1", "title": "First", "depends_on": [], "acceptance_criteria": ["Works"], "touched_paths": ["src/a.py"], "focused_tests": [["python3", "-m", "unittest", "test_a"]], "broader_tests": [], "status": "pending"},
            {"id": "T2", "title": "Second", "depends_on": ["T1"], "acceptance_criteria": ["Works"], "touched_paths": ["src/b.py"], "focused_tests": [["python3", "-m", "unittest", "test_b"]], "broader_tests": [["python3", "-m", "unittest"]], "status": "pending"},
        ]}
        self.assertEqual(tasks, get_phase("tasks").validate(json.dumps(tasks)))
        tasks["tasks"][0]["depends_on"] = ["T2"]
        with self.assertRaises(PhaseValidationError):
            get_phase("tasks").validate(json.dumps(tasks))

    def test_review_verdict_fails_closed(self) -> None:
        approved = "# Review v1\n## Verdict\nAPPROVE\n## Findings\nNone.\n"
        self.assertEqual(approved, get_phase("review").validate(approved))
        with self.assertRaises(PhaseValidationError):
            get_phase("review").validate(approved.replace("APPROVE", "LGTM"))


if __name__ == "__main__":
    unittest.main()
