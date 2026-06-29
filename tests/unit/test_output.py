from __future__ import annotations

import unittest
from pathlib import Path

from ai_harness.output import default_command_context, render_pending_decision, render_resume_command, RunResult, render_result
from ai_harness.router import RouteDecision
from ai_harness.strategy import StrategyDecision


class OutputTests(unittest.TestCase):
    def test_sections_and_run_identity_are_stable(self) -> None:
        result = RunResult(
            "run-1", RouteDecision("code", "modify_code", 0.9, "heuristic"),
            StrategyDecision("SDD", "LOW", 0, "small", ()),
            ("INITIALIZING", "COMPLETED"), "T1=completed", ("state.json",),
            "success", Path("/tmp/run-1"),
        )
        output = render_result(result)
        headings = ["## Router", "## Strategy", "## Pipeline", "## Artifacts", "## Result"]
        self.assertEqual(sorted(output.index(item) for item in headings), [output.index(item) for item in headings])
        self.assertIn("Run ID: run-1", output)
        self.assertIn("Snapshot: /tmp/run-1", output)

    def test_pending_decision_renders_self_contained_recovery_commands(self) -> None:
        context = default_command_context(Path("/tmp/target-repo"), Path("/tmp/checkout/run.py"))
        output = render_pending_decision(
            "run-1",
            "D1",
            {
                "origin_phase": "DESIGN",
                "question": "Choose an option.",
                "options": [{"id": "keep", "label": "Keep", "consequence": "Compatibility stays."}],
            },
            context,
            model="gpt-5",
        )
        self.assertIn("python", output)
        self.assertIn("-B /tmp/checkout/run.py --cwd /tmp/target-repo --resume run-1 --model gpt-5", output)
        self.assertIn("--answer <answer> --selected-option <option-id>", output)
        self.assertIn("--answer-file <path>", output)
        self.assertIn("--archive run-1", output)

    def test_render_resume_command_can_include_model(self) -> None:
        context = default_command_context(Path("/tmp/target-repo"), Path("/tmp/checkout/run.py"))
        self.assertIn("--model gpt-5", render_resume_command(context, "run-1", model="gpt-5"))


if __name__ == "__main__":
    unittest.main()
