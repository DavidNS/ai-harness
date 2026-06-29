from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))

import check_architecture
from ai_harness.errors import ValidationError
from ai_harness.orchestrator.phase_executor import PhaseExecutor


class ArchitectureContractTests(unittest.TestCase):
    def test_architecture_checker_has_no_blocking_errors(self) -> None:
        report = check_architecture.run_checks()
        self.assertEqual([], report.errors)

    def test_architecture_checker_exposes_structured_findings(self) -> None:
        report = check_architecture.run_checks()
        payload = report.to_dict()

        self.assertEqual("passed", payload["status"])
        self.assertEqual(0, payload["error_count"])
        self.assertEqual(len(report.warnings), payload["warning_count"])
        self.assertEqual(len(report.findings), len(payload["findings"]))
        self.assertTrue(all("code" in finding for finding in payload["findings"]))

    def test_architecture_checker_structures_budget_warnings(self) -> None:
        report = check_architecture.run_checks()
        budget_findings = [
            finding
            for finding in report.findings
            if finding.code in {"line_budget.source", "line_budget.integration"}
        ]

        self.assertTrue(budget_findings)
        self.assertTrue(all(finding.category == "budget" for finding in budget_findings))
        self.assertTrue(all("lines" in finding.details for finding in budget_findings))
        self.assertTrue(all("budget" in finding.details for finding in budget_findings))
        self.assertTrue(all("over_by" in finding.details for finding in budget_findings))

    def test_architecture_checker_summary_rendering(self) -> None:
        report = check_architecture.run_checks()

        self.assertEqual(
            f"Architecture check passed: {len(report.warnings)} warning(s)",
            check_architecture.render_summary(report),
        )

    def test_phase_executor_fails_closed_for_unknown_phase(self) -> None:
        with self.assertRaises(ValidationError):
            PhaseExecutor({}).execute("MISSING_PHASE")

    def test_phase_executor_runs_known_phase(self) -> None:
        calls: list[str] = []
        PhaseExecutor({"KNOWN": lambda: calls.append("called")}).execute("KNOWN")
        self.assertEqual(["called"], calls)

    def test_dispatcher_covers_graph_phases(self) -> None:
        dispatched = check_architecture.dispatcher_phases()
        graph_phases = {
            check_architecture.phase_value(phase)
            for graph in check_architecture.GRAPHS.values()
            for phase in graph
        }
        missing = graph_phases - dispatched - {"SNAPSHOTTING", "COMPLETED"}
        self.assertEqual(set(), missing)


if __name__ == "__main__":
    unittest.main()
