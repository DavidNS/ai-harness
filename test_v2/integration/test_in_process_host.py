from __future__ import annotations

import unittest

from test_v2.support.runtime import memory_orchestrator
from harness_v2.backend.application.contracts import GetRun, ResumeRun, StartRun


class RuntimeLifecycleIntegrationTests(unittest.TestCase):
    def test_start_and_resume_enter_first_phase_of_root_bundle(self) -> None:
        service, _state, _artifacts, _knowledge = memory_orchestrator()

        started = service.execute(StartRun("Fix tests", root_bundle="EXPLORE_BUNDLE"))
        resumed = service.execute(ResumeRun(started.run.run_id))
        fetched = service.query(GetRun(started.run.run_id))

        self.assertEqual("EXPLORE_BUNDLE", resumed.run.root_bundle)
        self.assertEqual("EXPLORE_BUNDLE", resumed.run.current_step.bundle)
        self.assertEqual("EXPLORE_REQUEST_UNDERSTANDING", resumed.run.current_step.phase)
        self.assertEqual(resumed.run, fetched.run)


if __name__ == "__main__":
    unittest.main()
