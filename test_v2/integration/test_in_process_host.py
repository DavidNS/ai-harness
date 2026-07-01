from __future__ import annotations

import unittest

from harness_v2.backend.application.contracts import (
    CancelRun,
    GetAvailableActions,
    GetRun,
    GetRunState,
    ListRuns,
    PhaseCompleted,
    PhaseStarted,
    RunCompleted,
    RunStarted,
    StartRun,
    SubmitUserDecision,
)
from harness_v2.backend.application.run_service import InMemoryRunService, InvalidRunStateError
from harness_v2.backend.domain.runs import RunRecord, RunStatus
from harness_v2.hosts.in_process.host import InProcessHost


class InProcessHostIntegrationTests(unittest.TestCase):
    def test_start_run_completes_simulated_run_and_emits_ordered_events(self) -> None:
        host = InProcessHost(InMemoryRunService(id_factory=lambda: "run-1"))

        result = host.execute(StartRun("Fix tests"))

        self.assertIsInstance(result.run, RunRecord)
        self.assertEqual("run-1", result.run.run_id)
        self.assertEqual(RunStatus.COMPLETED, result.run.status)
        self.assertEqual(("SIMULATED",), result.run.completed_phases)
        self.assertEqual(
            [RunStarted, PhaseStarted, PhaseCompleted, RunCompleted],
            [type(event) for event in result.events],
        )

    def test_queries_return_authoritative_backend_state(self) -> None:
        host = InProcessHost(InMemoryRunService(id_factory=lambda: "run-1"))
        host.execute(StartRun("Fix tests"))

        self.assertEqual(RunStatus.COMPLETED, host.query(GetRunState("run-1")))
        self.assertEqual((), host.query(GetAvailableActions("run-1")))
        self.assertEqual("Fix tests", host.query(GetRun("run-1")).request)
        self.assertEqual(["run-1"], [run.run_id for run in host.query(ListRuns())])

    def test_completed_run_cannot_be_cancelled(self) -> None:
        host = InProcessHost(InMemoryRunService(id_factory=lambda: "run-1"))
        host.execute(StartRun("Fix tests"))

        with self.assertRaises(InvalidRunStateError):
            host.execute(CancelRun("run-1"))

    def test_submit_decision_without_pending_request_fails_closed(self) -> None:
        host = InProcessHost(InMemoryRunService(id_factory=lambda: "run-1"))
        host.execute(StartRun("Fix tests"))

        with self.assertRaises(InvalidRunStateError):
            host.execute(SubmitUserDecision("run-1", "decision-1", "continue"))


if __name__ == "__main__":
    unittest.main()

