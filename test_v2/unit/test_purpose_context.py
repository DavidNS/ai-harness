from __future__ import annotations

import unittest

from harness_v2.backend.application.phase_artifacts import sdd


def explore_bundle(action: str = "create", *, target: dict[str, object] | None = None) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": "entry-1",
        "classification": "improvement",
        "action": action,
        "title": "Entry",
        "rationale": "Evidence supports the entry.",
        "evidence_refs": ["E1"],
    }
    if target is not None:
        entry["target"] = target
    return {
        "schema_version": 1,
        "kind": "explore_outcome_bundle",
        "status": "ready_for_purpose",
        "normalized_request": {"summary": "Request"},
        "triage": {},
        "evidence": [],
        "exploration_map": {},
        "entries": [entry],
    }


def purpose(*, mode: str = "direct_patch", outcome: str = "proceed", selected: list[str] | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "purpose_bundle",
        "summary": "Implement",
        "implementation_mode": mode,
        "problem": "Problem",
        "scope": "One bounded change.",
        "approach": "Patch the behavior.",
        "outcome": outcome,
        "selected_entries": selected or ["entry-1"],
        "structural_work": [],
        "exclusions": ["No unrelated work."],
        "acceptance_outline": ["Tests pass."],
        "evidence_refs": ["E1"],
    }


def spec(path: str = "docs/explorer/improvements/existing/improvement.md") -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "spec",
        "summary": f"Update {path} behavior.",
        "behavioral_requirements": [f"The selected behavior is preserved in {path}."],
        "acceptance_criteria": [f"Review {path} for the selected behavior."],
        "non_goals": ["No unrelated behavior changes."],
    }


def design(path: str = "docs/explorer/improvements/existing/improvement.md") -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "design",
        "boundaries": [f"Keep changes bounded to {path}."],
        "invariants": ["Preserve existing behavior."],
        "implementation_approach": [f"Update {path} with the selected behavior."],
        "test_strategy": {
            "unit": [f"Review {path}."],
            "integration": ["Run focused validation."],
            "acceptance": ["Complete the selected update."],
        },
    }


def tasks(path: str = "docs/explorer/improvements/existing/improvement.md") -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "tasks",
        "tasks": [{
            "id": "T1",
            "title": f"Update {path}",
            "depends_on": [],
            "acceptance_criteria": [f"{path} captures the selected behavior."],
            "touched_paths": [path],
            "focused_tests": [["python3", "-m", "unittest"]],
            "broader_tests": [],
            "status": "pending",
        }],
    }


class PurposeContextValidationTests(unittest.TestCase):
    def test_create_requires_implementable_mode_and_known_entry(self) -> None:
        sdd.validate_purpose_against_explore(purpose(), explore_bundle())

        with self.assertRaises(ValueError):
            sdd.validate_purpose_against_explore(purpose(mode="existing_functionality"), explore_bundle())

        with self.assertRaises(ValueError):
            sdd.validate_purpose_against_explore(purpose(selected=["missing"]), explore_bundle())

    def test_update_existing_requires_mode_and_target_mention(self) -> None:
        target = {"path": "docs/explorer/improvements/existing/improvement.md", "checksum": "abc"}
        valid = purpose(mode="update_existing")
        valid["scope"] = "Update docs/explorer/improvements/existing/improvement.md."

        sdd.validate_purpose_against_explore(valid, explore_bundle("update_existing", target=target))

        with self.assertRaises(ValueError):
            sdd.validate_purpose_against_explore(purpose(mode="direct_patch"), explore_bundle("update_existing", target=target))

    def test_existing_functionality_is_non_implementation(self) -> None:
        target = {"path": "src/already.py"}
        valid = purpose(mode="existing_functionality", outcome="alternative")
        valid["acceptance_outline"] = []

        sdd.validate_purpose_against_explore(valid, explore_bundle("existing_functionality", target=target))

        with self.assertRaises(ValueError):
            sdd.validate_purpose_against_explore(purpose(mode="direct_patch"), explore_bundle("existing_functionality", target=target))

    def test_duplicate_reject_ask_user_and_blocked_actions_are_preserved(self) -> None:
        duplicate = purpose(mode="blocked", outcome="reject")
        duplicate["rejection_reason"] = "Duplicate."
        duplicate["acceptance_outline"] = []
        sdd.validate_purpose_against_explore(duplicate, explore_bundle("duplicate_noop", target={"path": "src/existing.py"}))

        ask = purpose(mode="blocked", outcome="clarify")
        ask["question"] = "Which direction?"
        ask["options"] = ["A", "B"]
        sdd.validate_purpose_against_explore(ask, explore_bundle("ask_user"))

        blocked = purpose(mode="blocked", outcome="reject")
        blocked["rejection_reason"] = "CI unavailable."
        blocked["acceptance_outline"] = []
        sdd.validate_purpose_against_explore(blocked, explore_bundle("blocked"))

        with self.assertRaises(ValueError):
            sdd.validate_purpose_against_explore(purpose(), explore_bundle("duplicate_noop", target={"path": "src/existing.py"}))

    def test_downstream_artifacts_preserve_update_existing_target(self) -> None:
        target = {"path": "docs/explorer/improvements/existing/improvement.md", "checksum": "abc"}
        bundle = explore_bundle("update_existing", target=target)
        selected = purpose(mode="update_existing")
        selected["scope"] = "Update docs/explorer/improvements/existing/improvement.md."

        sdd.validate_spec_against_purpose_and_explore(spec(), selected, bundle)
        sdd.validate_design_against_purpose_and_explore(design(), selected, bundle)
        sdd.validate_tasks_against_purpose_and_explore(tasks(), selected, bundle)

        with self.assertRaises(ValueError):
            sdd.validate_spec_against_purpose_and_explore(spec("src/other.py"), selected, bundle)
        with self.assertRaises(ValueError):
            sdd.validate_design_against_purpose_and_explore(design("src/other.py"), selected, bundle)
        with self.assertRaises(ValueError):
            sdd.validate_tasks_against_purpose_and_explore(tasks("src/other.py"), selected, bundle)

    def test_downstream_artifacts_do_not_continue_non_implementation_outcomes(self) -> None:
        existing = purpose(mode="existing_functionality", outcome="alternative")
        existing["acceptance_outline"] = []
        existing_bundle = explore_bundle("existing_functionality", target={"path": "src/already.py"})

        with self.assertRaises(ValueError):
            sdd.validate_spec_against_purpose_and_explore(spec(), existing, existing_bundle)
        with self.assertRaises(ValueError):
            sdd.validate_design_against_purpose_and_explore(design(), existing, existing_bundle)
        with self.assertRaises(ValueError):
            sdd.validate_tasks_against_purpose_and_explore(tasks(), existing, existing_bundle)

        rejected = purpose(mode="blocked", outcome="reject")
        rejected["rejection_reason"] = "Duplicate."
        rejected["acceptance_outline"] = []
        rejected_bundle = explore_bundle("duplicate_noop", target={"path": "src/existing.py"})

        with self.assertRaises(ValueError):
            sdd.validate_spec_against_purpose_and_explore(spec(), rejected, rejected_bundle)

        clarify = purpose(mode="blocked", outcome="clarify")
        clarify["question"] = "Which direction?"
        clarify["options"] = ["A", "B"]

        with self.assertRaises(ValueError):
            sdd.validate_tasks_against_purpose_and_explore(tasks(), clarify, explore_bundle("ask_user"))


if __name__ == "__main__":
    unittest.main()
