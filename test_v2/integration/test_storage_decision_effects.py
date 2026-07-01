from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness_v2.adapters.storage import FileArtifactStore, FileStateStore, InMemoryArtifactStore
from harness_v2.backend.domain.decisions import DecisionAction, DecisionEffect, DecisionRecord, PendingDecision
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactNotFoundError

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class StorageDecisionEffectIntegrationTests(unittest.TestCase):
    def test_file_state_round_trips_pending_and_historical_decision_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = FileStateStore(Path(temp))
            pending = PendingDecision(
                "decision-1",
                PhaseName.DESIGN_BUNDLE,
                "Choose",
                TIMESTAMP,
                options=("continue", "respec"),
                effects=(DecisionEffect("respec", DecisionAction.ESCALATE, PhaseName.SPEC_BUNDLE),),
                default_action=DecisionAction.ESCALATE,
                default_target_phase=PhaseName.SPEC_BUNDLE,
            )
            history = DecisionRecord(
                "decision-0",
                PhaseName.PROPOSAL_BUNDLE,
                "Choose",
                "continue",
                TIMESTAMP,
                TIMESTAMP,
                options=("continue",),
            )
            run = RunRecord(
                "run-1",
                "Fix tests",
                RunStatus.WAITING_FOR_USER,
                RunStrategy.SDD,
                current_phase=PhaseName.DESIGN_BUNDLE,
                completed_phases=(PhaseName.EXPLORE_BUNDLE, PhaseName.PROPOSAL_BUNDLE, PhaseName.SPEC_BUNDLE),
                pending_decision=pending,
                decision_history=(history,),
            )

            store.save(run)
            loaded = store.get("run-1")

            self.assertEqual(pending, loaded.pending_decision)
            self.assertEqual((history,), loaded.decision_history)
            self.assertEqual(DecisionAction.ESCALATE, loaded.pending_decision.effects[0].action)
            self.assertEqual(PhaseName.SPEC_BUNDLE, loaded.pending_decision.effects[0].target_phase)
            self.assertEqual(DecisionAction.ESCALATE, loaded.pending_decision.default_action)
            self.assertEqual(PhaseName.SPEC_BUNDLE, loaded.pending_decision.default_target_phase)

    def test_artifact_delete_removes_existing_artifact_and_missing_returns_false(self) -> None:
        memory = InMemoryArtifactStore()
        memory.write("run-1", "reports/output.txt", b"content")
        self.assertTrue(memory.delete("run-1", "reports/output.txt"))
        self.assertFalse(memory.delete("run-1", "reports/output.txt"))
        with self.assertRaises(ArtifactNotFoundError):
            memory.read("run-1", "reports/output.txt")

        with tempfile.TemporaryDirectory() as temp:
            file_store = FileArtifactStore(Path(temp))
            file_store.write("run-1", "reports/output.txt", b"content")
            self.assertTrue(file_store.delete("run-1", "reports/output.txt"))
            self.assertFalse(file_store.delete("run-1", "reports/output.txt"))
            with self.assertRaises(ArtifactNotFoundError):
                file_store.read("run-1", "reports/output.txt")


if __name__ == "__main__":
    unittest.main()
