from __future__ import annotations

import unittest

from test_v2.support.runtime import memory_orchestrator
from harness_v2.backend.application.contracts import RetryBundle, RetryPhase
from harness_v2.backend.domain.errors import ErrorRecord
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord


class PhaseRetryIntegrationTests(unittest.TestCase):
    def test_retry_phase_rewinds_to_failed_phase_and_invalidates_tail(self) -> None:
        service, state, _artifacts, _knowledge = memory_orchestrator()
        state.save(RunRecord(
            "run-1",
            "Fix tests",
            RunStatus.FAILED,
            root_bundle=BundleName.EXPLORE_BUNDLE,
            completed_phases=(PhaseName.EXPLORE_REQUEST_UNDERSTANDING,),
            errors=(ErrorRecord("EXPLORE_CONTEXT_PACK_FAILED", "failed", bundle="EXPLORE_BUNDLE", phase="EXPLORE_CONTEXT_PACK", timestamp="now"),),
        ))

        result = service.execute(RetryPhase("run-1", "EXPLORE_BUNDLE", "EXPLORE_CONTEXT_PACK"))

        self.assertEqual("RUNNING", result.run.status)
        self.assertEqual("EXPLORE_CONTEXT_PACK", result.run.current_phase)
        self.assertEqual(("EXPLORE_REQUEST_UNDERSTANDING",), result.run.completed_phases)

    def test_retry_bundle_rewinds_to_first_phase_of_bundle(self) -> None:
        service, state, _artifacts, _knowledge = memory_orchestrator()
        state.save(RunRecord(
            "run-1",
            "Fix tests",
            RunStatus.FAILED,
            root_bundle=BundleName.EXPLORE_BUNDLE,
            errors=(ErrorRecord("EXPLORE_REQUEST_UNDERSTANDING_FAILED", "failed", bundle="EXPLORE_BUNDLE", phase="EXPLORE_REQUEST_UNDERSTANDING", timestamp="now"),),
        ))

        result = service.execute(RetryBundle("run-1", "EXPLORE_BUNDLE"))

        self.assertEqual("EXPLORE_REQUEST_UNDERSTANDING", result.run.current_phase)


if __name__ == "__main__":
    unittest.main()
