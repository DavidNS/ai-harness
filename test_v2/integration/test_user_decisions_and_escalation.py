from __future__ import annotations

import unittest

from test_v2.support.runtime import memory_orchestrator
from harness_v2.backend.application.contracts import SubmitUserDecision
from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord


class UserDecisionIntegrationTests(unittest.TestCase):
    def test_submit_decision_records_history_and_returns_to_running(self) -> None:
        service, state, _artifacts, _knowledge = memory_orchestrator()
        decision = PendingDecision("decision-1", BundleName.EXPLORE_BUNDLE, "Choose", "created", options=("continue",))
        state.save(RunRecord("run-1", "Fix tests", RunStatus.WAITING_FOR_USER, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING, pending_decision=decision))

        result = service.execute(SubmitUserDecision("run-1", "decision-1", "continue"))

        self.assertEqual("RUNNING", result.run.status)
        self.assertIsNone(result.run.pending_decision)
        self.assertEqual("decision-1", state.get("run-1").decision_history[0].decision_id)


if __name__ == "__main__":
    unittest.main()
