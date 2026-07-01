from __future__ import annotations

import unittest

from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.errors import DomainValidationError, ErrorRecord
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy, SDD_PHASES
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.domain.tasks import TaskStatus, TaskSummary


TIMESTAMP = "2026-07-01T00:00:00+00:00"


class RunDomainTests(unittest.TestCase):
    def test_completed_bundle_run_carries_domain_phase_and_strategy(self) -> None:
        run = RunRecord(
            run_id="run-1",
            request="Fix tests",
            status=RunStatus.COMPLETED,
            strategy=RunStrategy.EXPLORE_BUNDLE,
            completed_phases=(PhaseName.EXPLORE_BUNDLE,),
        )

        self.assertEqual("run-1", run.run_id)
        self.assertEqual(RunStatus.COMPLETED, run.status)
        self.assertEqual(RunStrategy.EXPLORE_BUNDLE, run.strategy)
        self.assertEqual((PhaseName.EXPLORE_BUNDLE,), run.completed_phases)

    def test_completed_sdd_run_requires_all_strategy_phases(self) -> None:
        run = RunRecord(
            run_id="run-1",
            request="Fix tests",
            status=RunStatus.COMPLETED,
            strategy=RunStrategy.SDD,
            completed_phases=SDD_PHASES,
        )
        self.assertEqual(SDD_PHASES, run.completed_phases)

        with self.assertRaises(DomainValidationError):
            RunRecord(
                run_id="run-1",
                request="Fix tests",
                status=RunStatus.COMPLETED,
                strategy=RunStrategy.SDD,
                completed_phases=(PhaseName.EXPLORE_BUNDLE,),
            )

    def test_replace_preserves_run_fields(self) -> None:
        run = RunRecord(
            run_id="run-1",
            request="Fix tests",
            status=RunStatus.RUNNING,
            current_phase=PhaseName.EXPLORE_BUNDLE,
        )
        updated = run.replace(status=RunStatus.CANCELLED, current_phase=None)

        self.assertEqual(run.run_id, updated.run_id)
        self.assertEqual(run.request, updated.request)
        self.assertEqual(RunStatus.CANCELLED, updated.status)
        self.assertIsNone(updated.current_phase)

    def test_run_status_invariants_fail_closed(self) -> None:
        decision = PendingDecision("decision-1", PhaseName.EXPLORE_BUNDLE, "Choose", TIMESTAMP)
        invalid_cases = (
            lambda: RunRecord("run-1", "Fix tests", RunStatus.RUNNING),
            lambda: RunRecord("run-1", "Fix tests", RunStatus.PENDING, current_phase=PhaseName.EXPLORE_BUNDLE),
            lambda: RunRecord("run-1", "Fix tests", RunStatus.FAILED, current_phase=PhaseName.EXPLORE_BUNDLE),
            lambda: RunRecord("run-1", "Fix tests", RunStatus.CANCELLED, pending_decision=decision),
        )

        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(DomainValidationError):
                    create()

    def test_active_run_current_phase_must_be_next_after_completed_prefix(self) -> None:
        valid = RunRecord(
            "run-1",
            "Fix tests",
            RunStatus.RUNNING,
            current_phase=PhaseName.PROPOSAL_BUNDLE,
            completed_phases=(PhaseName.EXPLORE_BUNDLE,),
        )
        self.assertEqual(PhaseName.PROPOSAL_BUNDLE, valid.current_phase)

        invalid_cases = (
            lambda: RunRecord(
                "run-1",
                "Fix tests",
                RunStatus.RUNNING,
                current_phase=PhaseName.EXPLORE_BUNDLE,
                completed_phases=(PhaseName.EXPLORE_BUNDLE,),
            ),
            lambda: RunRecord(
                "run-1",
                "Fix tests",
                RunStatus.RUNNING,
                current_phase=PhaseName.EXPLORE_BUNDLE,
                completed_phases=SDD_PHASES,
            ),
        )
        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(DomainValidationError):
                    create()

    def test_waiting_run_requires_matching_pending_decision(self) -> None:
        decision = PendingDecision(
            decision_id="decision-1",
            origin_phase=PhaseName.EXPLORE_BUNDLE,
            prompt="Choose",
            created_at=TIMESTAMP,
            options=("continue", "cancel"),
        )
        run = RunRecord(
            run_id="run-1",
            request="Fix tests",
            status=RunStatus.WAITING_FOR_USER,
            current_phase=PhaseName.EXPLORE_BUNDLE,
            pending_decision=decision,
        )
        self.assertEqual(decision, run.pending_decision)

        proposal_decision = PendingDecision("decision-2", PhaseName.PROPOSAL_BUNDLE, "Choose", TIMESTAMP)
        proposal_waiting = RunRecord(
            run_id="run-1",
            request="Fix tests",
            status=RunStatus.WAITING_FOR_USER,
            current_phase=PhaseName.PROPOSAL_BUNDLE,
            completed_phases=(PhaseName.EXPLORE_BUNDLE,),
            pending_decision=proposal_decision,
        )
        self.assertEqual(proposal_decision, proposal_waiting.pending_decision)

        with self.assertRaises(DomainValidationError):
            RunRecord(
                run_id="run-1",
                request="Fix tests",
                status=RunStatus.WAITING_FOR_USER,
                current_phase=PhaseName.EXPLORE_BUNDLE,
            )
        with self.assertRaises(DomainValidationError):
            RunRecord(
                run_id="run-1",
                request="Fix tests",
                status=RunStatus.WAITING_FOR_USER,
                current_phase=PhaseName.PROPOSAL_BUNDLE,
                pending_decision=decision,
            )
        with self.assertRaises(DomainValidationError):
            RunRecord(
                run_id="run-1",
                request="Fix tests",
                status=RunStatus.WAITING_FOR_USER,
                current_phase=PhaseName.EXPLORE_BUNDLE,
                completed_phases=(PhaseName.EXPLORE_BUNDLE,),
                pending_decision=decision,
            )

    def test_task_summary_and_error_record_validate_required_fields(self) -> None:
        task = TaskSummary("task-1", "Implement", TaskStatus.IN_PROGRESS)
        error = ErrorRecord("E001", "failed", phase=PhaseName.EXPLORE_BUNDLE.value, timestamp=TIMESTAMP)

        self.assertEqual(TaskStatus.IN_PROGRESS, task.status)
        self.assertEqual("E001", error.code)

        invalid_cases = (
            lambda: TaskSummary("", "Implement"),
            lambda: TaskSummary("task-1", ""),
            lambda: TaskSummary("task-1", "Implement", "UNKNOWN"),
            lambda: ErrorRecord("", "failed", timestamp=TIMESTAMP),
            lambda: ErrorRecord("E001", "", timestamp=TIMESTAMP),
            lambda: ErrorRecord("E001", "failed", timestamp=""),
        )
        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises((DomainValidationError, ValueError)):
                    create()


if __name__ == "__main__":
    unittest.main()
