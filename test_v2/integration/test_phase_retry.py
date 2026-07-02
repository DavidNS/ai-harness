from __future__ import annotations

import unittest

from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.backend.application.contracts import InvalidRunStateError, RetryPhase
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.domain.errors import ErrorRecord
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactNotFoundError

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class StaticIdGenerator:
    def new_id(self) -> str:
        return "run-1"


class FailingSaveStateStore:
    def __init__(self, delegate: InMemoryStateStore) -> None:
        self.delegate = delegate

    def get(self, run_id: str) -> RunRecord:
        return self.delegate.get(run_id)

    def save(self, run: RunRecord) -> None:
        raise RuntimeError("save failed")

    def list_all(self) -> tuple[RunRecord, ...]:
        return self.delegate.list_all()

    def list_active(self) -> tuple[RunRecord, ...]:
        return self.delegate.list_active()

    def list_completed(self) -> tuple[RunRecord, ...]:
        return self.delegate.list_completed()


def failed_design_run() -> RunRecord:
    return RunRecord(
        "run-1",
        "Fix tests",
        RunStatus.FAILED,
        RunStrategy.SDD,
        completed_phases=(PhaseName.EXPLORE_BUNDLE, PhaseName.KNOWLEDGE_EXTRACT_EXPLORE, PhaseName.PROPOSAL_BUNDLE, PhaseName.SPEC_BUNDLE),
        errors=(ErrorRecord("DESIGN_BUNDLE_FAILED", "bad design", phase="DESIGN_BUNDLE", timestamp=TIMESTAMP),),
    )


class PhaseRetryIntegrationTests(unittest.TestCase):
    def test_retry_failed_phase_reopens_phase_and_invalidates_retry_artifacts(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        state.save(failed_design_run())
        artifacts.write("run-1", "spec.md", b"spec")
        artifacts.write("run-1", "design.md", b"design")
        artifacts.write("run-1", "published/design-handoff.json", b"handoff")
        artifacts.write("run-1", "validation/DESIGN_BUNDLE-failure.json", b"failure")
        artifacts.write("run-1", "workers/DESIGN_BUNDLE/design/result.json", b"worker")
        app = RunService(state, StaticIdGenerator(), artifact_store=artifacts)

        result = app.execute(RetryPhase("run-1", "DESIGN_BUNDLE"))

        self.assertEqual("RUNNING", result.run.status)
        self.assertEqual("DESIGN_BUNDLE", result.run.current_phase)
        self.assertEqual(("EXPLORE_BUNDLE", "KNOWLEDGE_EXTRACT_EXPLORE", "PROPOSAL_BUNDLE", "SPEC_BUNDLE"), result.run.completed_phases)
        self.assertEqual(["PhaseRetryStarted", "PhaseStarted"], [type(event).__name__ for event in result.events])
        persisted = state.get("run-1")
        self.assertEqual(RunStatus.RUNNING, persisted.status)
        self.assertEqual(PhaseName.DESIGN_BUNDLE, persisted.current_phase)
        self.assertEqual(1, len(persisted.errors))
        self.assertEqual(b"spec", artifacts.read("run-1", "spec.md"))
        for deleted in ("design.md", "published/design-handoff.json", "validation/DESIGN_BUNDLE-failure.json", "workers/DESIGN_BUNDLE/design/result.json"):
            with self.subTest(deleted=deleted):
                with self.assertRaises(ArtifactNotFoundError):
                    artifacts.read("run-1", deleted)

    def test_retry_restores_invalidated_artifacts_when_state_save_fails(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        original = failed_design_run()
        state.save(original)
        artifacts.write("run-1", "design.md", b"design")
        artifacts.write("run-1", "workers/DESIGN_BUNDLE/design/result.json", b"worker")
        app = RunService(FailingSaveStateStore(state), StaticIdGenerator(), artifact_store=artifacts)

        with self.assertRaises(RuntimeError):
            app.execute(RetryPhase("run-1", "DESIGN_BUNDLE"))

        self.assertEqual(original, state.get("run-1"))
        self.assertEqual(b"design", artifacts.read("run-1", "design.md"))
        self.assertEqual(b"worker", artifacts.read("run-1", "workers/DESIGN_BUNDLE/design/result.json"))

    def test_retry_fails_closed_for_invalid_state_or_phase(self) -> None:
        cases = (
            (RunRecord("run-1", "Fix", RunStatus.RUNNING, RunStrategy.SDD, current_phase=PhaseName.EXPLORE_BUNDLE), RetryPhase("run-1", "EXPLORE_BUNDLE")),
            (failed_design_run(), RetryPhase("run-1", "SPEC_BUNDLE")),
            (
                RunRecord(
                    "run-1",
                    "Fix",
                    RunStatus.FAILED,
                    RunStrategy.SDD,
                    completed_phases=(PhaseName.EXPLORE_BUNDLE,),
                    errors=(ErrorRecord("DESIGN_BUNDLE_FAILED", "bad design", phase="DESIGN_BUNDLE", timestamp=TIMESTAMP),),
                ),
                RetryPhase("run-1", "DESIGN_BUNDLE"),
            ),
        )
        for run, command in cases:
            with self.subTest(run=run.status, phase=command.phase):
                state = InMemoryStateStore()
                artifacts = InMemoryArtifactStore()
                state.save(run)
                with self.assertRaises(InvalidRunStateError):
                    RunService(state, StaticIdGenerator(), artifact_store=artifacts).execute(command)

    def test_retry_requires_artifact_store(self) -> None:
        state = InMemoryStateStore()
        state.save(failed_design_run())

        with self.assertRaises(InvalidRunStateError):
            RunService(state, StaticIdGenerator()).execute(RetryPhase("run-1", "DESIGN_BUNDLE"))


if __name__ == "__main__":
    unittest.main()
