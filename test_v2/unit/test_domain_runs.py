from __future__ import annotations

import unittest

from harness_v2.backend.domain.runs import RunRecord, RunStatus


class RunDomainTests(unittest.TestCase):
    def test_run_record_carries_completed_state(self) -> None:
        run = RunRecord(
            run_id="run-1",
            request="Fix tests",
            status=RunStatus.COMPLETED,
            completed_phases=("SIMULATED",),
        )

        self.assertEqual("run-1", run.run_id)
        self.assertEqual(RunStatus.COMPLETED, run.status)
        self.assertEqual(("SIMULATED",), run.completed_phases)

    def test_with_events_preserves_run_fields(self) -> None:
        run = RunRecord(run_id="run-1", request="Fix tests", status=RunStatus.RUNNING)
        updated = run.with_events(("event",))

        self.assertEqual(run.run_id, updated.run_id)
        self.assertEqual(run.request, updated.request)
        self.assertEqual(run.status, updated.status)
        self.assertEqual(("event",), updated.events)


if __name__ == "__main__":
    unittest.main()

