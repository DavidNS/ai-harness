from __future__ import annotations

import unittest

from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.errors import DomainValidationError, ErrorRecord
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.domain.tasks import TaskStatus, TaskSummary

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class RunDomainTests(unittest.TestCase):
    def test_completed_bundle_run_carries_root_bundle_and_phases(self) -> None:
        phases = bundle_catalog.phases(BundleName.EXPLORE_BUNDLE)
        run = RunRecord("run-1", "Fix tests", RunStatus.COMPLETED, root_bundle=BundleName.EXPLORE_BUNDLE, completed_phases=phases)

        self.assertEqual(BundleName.EXPLORE_BUNDLE, run.root_bundle)
        self.assertEqual(phases, run.completed_phases)
        self.assertIsNone(run.current_bundle)

    def test_current_bundle_is_derived_from_current_phase(self) -> None:
        run = RunRecord("run-1", "Fix tests", RunStatus.RUNNING, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING)

        self.assertEqual(BundleName.EXPLORE_BUNDLE, run.current_bundle)
        self.assertEqual(PhaseName.EXPLORE_REQUEST_UNDERSTANDING, run.current_phase)

    def test_completed_sdd_run_requires_all_root_bundle_phases(self) -> None:
        phases = bundle_catalog.phases(BundleName.SDD_BUNDLE)
        run = RunRecord("run-1", "Fix tests", RunStatus.COMPLETED, completed_phases=phases)
        self.assertEqual(phases, run.completed_phases)

        with self.assertRaises(DomainValidationError):
            RunRecord("run-1", "Fix tests", RunStatus.COMPLETED, completed_phases=(PhaseName.EXPLORE_REQUEST_UNDERSTANDING,))

    def test_active_run_current_phase_must_be_next_after_completed_prefix(self) -> None:
        valid = RunRecord(
            "run-1",
            "Fix tests",
            RunStatus.RUNNING,
            current_phase=PhaseName.EXPLORE_CONTEXT_PACK,
            completed_phases=(PhaseName.EXPLORE_REQUEST_UNDERSTANDING,),
        )
        self.assertEqual(PhaseName.EXPLORE_CONTEXT_PACK, valid.current_phase)

        invalid_cases = (
            lambda: RunRecord("run-1", "Fix tests", RunStatus.RUNNING),
            lambda: RunRecord("run-1", "Fix tests", RunStatus.RUNNING, current_phase=PhaseName.PROPOSAL_DRAFT),
            lambda: RunRecord("run-1", "Fix tests", RunStatus.RUNNING, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING, completed_phases=(PhaseName.EXPLORE_REQUEST_UNDERSTANDING,)),
        )
        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(DomainValidationError):
                    create()

    def test_waiting_run_requires_matching_pending_decision_bundle(self) -> None:
        decision = PendingDecision("decision-1", BundleName.EXPLORE_BUNDLE, "Choose", TIMESTAMP, options=("continue",))
        run = RunRecord("run-1", "Fix tests", RunStatus.WAITING_FOR_USER, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING, pending_decision=decision)
        self.assertEqual(decision, run.pending_decision)

        with self.assertRaises(DomainValidationError):
            RunRecord("run-1", "Fix tests", RunStatus.WAITING_FOR_USER, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING)
        with self.assertRaises(DomainValidationError):
            RunRecord("run-1", "Fix tests", RunStatus.WAITING_FOR_USER, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING, pending_decision=PendingDecision("decision-2", BundleName.PROPOSAL_BUNDLE, "Choose", TIMESTAMP))

    def test_replace_ignores_legacy_current_bundle_and_preserves_fields(self) -> None:
        run = RunRecord("run-1", "Fix tests", RunStatus.RUNNING, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING)
        updated = run.replace(status=RunStatus.CANCELLED, current_phase=None, current_bundle=BundleName.PROPOSAL_BUNDLE)

        self.assertEqual(run.run_id, updated.run_id)
        self.assertEqual(RunStatus.CANCELLED, updated.status)
        self.assertIsNone(updated.current_phase)

    def test_task_summary_and_error_record_validate_required_fields(self) -> None:
        task = TaskSummary("task-1", "Implement", TaskStatus.IN_PROGRESS)
        error = ErrorRecord("E001", "failed", bundle=BundleName.EXPLORE_BUNDLE.value, phase=PhaseName.EXPLORE_CONTEXT_PACK.value, timestamp=TIMESTAMP)

        self.assertEqual(TaskStatus.IN_PROGRESS, task.status)
        self.assertEqual("EXPLORE_BUNDLE", error.bundle)
        self.assertEqual("EXPLORE_CONTEXT_PACK", error.phase)

        invalid_cases = (
            lambda: TaskSummary("", "Implement"),
            lambda: TaskSummary("task-1", ""),
            lambda: TaskSummary("task-1", "Implement", "UNKNOWN"),
            lambda: TaskSummary("task-1", "Implement", attempts=-1),
            lambda: ErrorRecord("", "failed", timestamp=TIMESTAMP),
            lambda: ErrorRecord("E001", "", timestamp=TIMESTAMP),
        )
        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises((DomainValidationError, ValueError)):
                    create()


if __name__ == "__main__":
    unittest.main()
