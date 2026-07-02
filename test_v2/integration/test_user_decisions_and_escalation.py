from __future__ import annotations

import unittest

from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.backend.application.contracts import InvalidRunStateError, SubmitUserDecision
from harness_v2.backend.application.decision_service import DecisionRequest, RequestUserDecisionService
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.domain.decisions import DecisionAction, DecisionEffect, PendingDecision
from harness_v2.backend.domain.escalation import EscalationCategory
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.domain.tasks import TaskStatus, TaskSummary
from harness_v2.backend.ports.artifact_store import ArtifactNotFoundError

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class StaticIdGenerator:
    def new_id(self) -> str:
        return "run-1"


class StaticClock:
    def now_iso(self) -> str:
        return TIMESTAMP


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


def waiting_tdd_run() -> RunRecord:
    return RunRecord(
        run_id="run-1",
        request="Fix tests",
        status=RunStatus.WAITING_FOR_USER,
        strategy=RunStrategy.SDD,
        current_phase=PhaseName.TDD_BUNDLE,
        completed_phases=(
            PhaseName.EXPLORE_BUNDLE,
            PhaseName.KNOWLEDGE_EXTRACT_EXPLORE,
            PhaseName.PROPOSAL_BUNDLE,
            PhaseName.SPEC_BUNDLE,
            PhaseName.DESIGN_BUNDLE,
            PhaseName.TASKS_BUNDLE,
        ),
        pending_decision=PendingDecision(
            "decision-1",
            PhaseName.TDD_BUNDLE,
            "Continue or redesign?",
            TIMESTAMP,
            options=("continue", "redesign"),
            effects=(DecisionEffect("redesign", DecisionAction.ESCALATE, EscalationCategory.DESIGN_GAP),),
        ),
        tasks=(TaskSummary("task-1", "Implement", TaskStatus.COMPLETED),),
    )


def service(state: InMemoryStateStore, artifacts: InMemoryArtifactStore) -> RunService:
    return RunService(state, StaticIdGenerator(), clock=StaticClock(), artifact_store=artifacts)


class UserDecisionEscalationIntegrationTests(unittest.TestCase):
    def test_request_decision_persists_waiting_state_with_escalation_category(self) -> None:
        state = InMemoryStateStore()
        state.save(
            RunRecord(
                "run-1",
                "Fix tests",
                RunStatus.RUNNING,
                RunStrategy.SDD,
                current_phase=PhaseName.DESIGN_BUNDLE,
                completed_phases=(PhaseName.EXPLORE_BUNDLE, PhaseName.KNOWLEDGE_EXTRACT_EXPLORE, PhaseName.PROPOSAL_BUNDLE, PhaseName.SPEC_BUNDLE),
            )
        )
        decision_service = RequestUserDecisionService(state, StaticClock())

        result = decision_service.execute(
            DecisionRequest(
                "run-1",
                "decision-1",
                "Continue or respec?",
                options=("continue", "respec"),
                effects=(DecisionEffect("respec", DecisionAction.ESCALATE, EscalationCategory.REQUIREMENTS_GAP),),
            )
        )

        self.assertEqual("WAITING_FOR_USER", result.run.status)
        self.assertEqual("decision-1", result.run.pending_decision.decision_id)
        self.assertEqual(RunStatus.WAITING_FOR_USER, state.get("run-1").status)

    def test_submit_decision_rejects_wrong_id_and_invalid_option_without_mutating_state(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        original = waiting_tdd_run()
        state.save(original)
        app = service(state, artifacts)

        with self.assertRaises(InvalidRunStateError):
            app.execute(SubmitUserDecision("run-1", "wrong", "continue"))
        self.assertEqual(original, state.get("run-1"))

        with self.assertRaises(InvalidRunStateError):
            app.execute(SubmitUserDecision("run-1", "decision-1", "unknown"))
        self.assertEqual(original, state.get("run-1"))

    def test_continue_answer_resumes_same_phase_and_records_history(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        state.save(waiting_tdd_run())
        app = service(state, artifacts)

        result = app.execute(SubmitUserDecision("run-1", "decision-1", "continue"))

        self.assertEqual("RUNNING", result.run.status)
        self.assertEqual("TDD_BUNDLE", result.run.current_phase)
        self.assertEqual(["UserDecisionReceived"], [type(event).__name__ for event in result.events])
        persisted = state.get("run-1")
        self.assertEqual(1, len(persisted.decision_history))
        self.assertEqual("continue", persisted.decision_history[0].response)
        self.assertEqual((TaskSummary("task-1", "Implement", TaskStatus.COMPLETED),), persisted.tasks)

    def test_escalation_rewinds_state_and_invalidates_later_artifacts_and_tasks(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        state.save(waiting_tdd_run())
        for artifact_id in (
            "explore/outcome_bundle.json",
            "purpose/bundle.json",
            "spec.md",
            "design.md",
            "tasks.json",
            "published/design-handoff.json",
            "published/tasks-handoff.json",
            "published/tdd-handoff.json",
            "workers/DESIGN_BUNDLE/design/request.json",
            "workers/TASKS_BUNDLE/tasks/result.json",
            "workers/TDD_BUNDLE/tdd/request.json",
        ):
            artifacts.write("run-1", artifact_id, b"content")
        app = service(state, artifacts)

        result = app.execute(SubmitUserDecision("run-1", "decision-1", "redesign"))

        self.assertEqual("RUNNING", result.run.status)
        self.assertEqual("DESIGN_BUNDLE", result.run.current_phase)
        self.assertEqual(("EXPLORE_BUNDLE", "KNOWLEDGE_EXTRACT_EXPLORE", "PROPOSAL_BUNDLE", "SPEC_BUNDLE"), result.run.completed_phases)
        self.assertEqual(["UserDecisionReceived", "EscalationRaised", "EscalationResolved", "PhaseStarted"], [type(event).__name__ for event in result.events])
        persisted = state.get("run-1")
        self.assertEqual(PhaseName.DESIGN_BUNDLE, persisted.current_phase)
        self.assertEqual((PhaseName.EXPLORE_BUNDLE, PhaseName.KNOWLEDGE_EXTRACT_EXPLORE, PhaseName.PROPOSAL_BUNDLE, PhaseName.SPEC_BUNDLE), persisted.completed_phases)
        self.assertEqual((), persisted.tasks)
        self.assertEqual("redesign", persisted.decision_history[0].response)

        for kept in ("explore/outcome_bundle.json", "purpose/bundle.json", "spec.md"):
            self.assertEqual(b"content", artifacts.read("run-1", kept))
        for deleted in (
            "design.md",
            "tasks.json",
            "published/design-handoff.json",
            "published/tasks-handoff.json",
            "published/tdd-handoff.json",
            "workers/DESIGN_BUNDLE/design/request.json",
            "workers/TASKS_BUNDLE/tasks/result.json",
            "workers/TDD_BUNDLE/tdd/request.json",
        ):
            with self.subTest(deleted=deleted):
                with self.assertRaises(ArtifactNotFoundError):
                    artifacts.read("run-1", deleted)

    def test_escalation_restores_invalidated_artifacts_when_state_save_fails(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        original = waiting_tdd_run()
        state.save(original)
        artifacts.write("run-1", "design.md", b"design")
        artifacts.write("run-1", "tasks.json", b"tasks")
        artifacts.write("run-1", "workers/TDD_BUNDLE/tdd/request.json", b"worker")
        app = RunService(FailingSaveStateStore(state), StaticIdGenerator(), clock=StaticClock(), artifact_store=artifacts)

        with self.assertRaises(RuntimeError):
            app.execute(SubmitUserDecision("run-1", "decision-1", "redesign"))

        self.assertEqual(original, state.get("run-1"))
        self.assertEqual(b"design", artifacts.read("run-1", "design.md"))
        self.assertEqual(b"tasks", artifacts.read("run-1", "tasks.json"))
        self.assertEqual(b"worker", artifacts.read("run-1", "workers/TDD_BUNDLE/tdd/request.json"))

    def test_escalation_target_is_revalidated_when_answer_is_submitted(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        state.save(
            RunRecord(
                "run-1",
                "Fix tests",
                RunStatus.WAITING_FOR_USER,
                RunStrategy.SDD,
                current_phase=PhaseName.SPEC_BUNDLE,
                completed_phases=(PhaseName.EXPLORE_BUNDLE, PhaseName.KNOWLEDGE_EXTRACT_EXPLORE, PhaseName.PROPOSAL_BUNDLE),
                pending_decision=PendingDecision(
                    "decision-1",
                    PhaseName.SPEC_BUNDLE,
                    "Invalid target",
                    TIMESTAMP,
                    options=("future",),
                    effects=(DecisionEffect("future", DecisionAction.ESCALATE, EscalationCategory.TASK_PLAN_GAP),),
                ),
            )
        )

        result = service(state, artifacts).execute(SubmitUserDecision("run-1", "decision-1", "future"))

        self.assertEqual("FAILED", result.run.status)
        self.assertEqual(["UserDecisionReceived", "EscalationRaised", "EscalationResolved", "PhaseFailed"], [type(event).__name__ for event in result.events])
        self.assertEqual(RunStatus.FAILED, state.get("run-1").status)


if __name__ == "__main__":
    unittest.main()
