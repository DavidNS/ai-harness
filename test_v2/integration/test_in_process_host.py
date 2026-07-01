from __future__ import annotations

import unittest

from harness_v2.adapters.storage import InMemoryStateStore
from harness_v2.backend.application.contracts import (
    CancelRun,
    CommandResult,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetRun,
    GetRunResult,
    GetRunState,
    GetRunStateResult,
    InvalidRunStateError,
    ListRuns,
    ListRunsResult,
    PhaseCompleted,
    PhaseStarted,
    QueryResult,
    ResumeRun,
    RunCompleted,
    RunNotFoundError,
    RunResumed,
    RunStarted,
    RunView,
    StartRun,
    SubmitUserDecision,
    UserDecisionReceived,
    UserDecisionRequested,
)
from harness_v2.backend.application.run_service import DecisionRequest, RequestUserDecisionService, RunService
from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.lifecycle import PhaseName, RunStrategy
from harness_v2.backend.domain.runs import RunRecord, RunStatus
from harness_v2.hosts.in_process.host import InProcessHost

TIMESTAMP = "2026-07-01T00:00:00+00:00"


def running_run(run_id: str = "run-1") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        request="Fix tests",
        status=RunStatus.RUNNING,
        strategy=RunStrategy.SDD,
        current_phase=PhaseName.EXPLORE_BUNDLE,
    )


class InProcessHostIntegrationTests(unittest.TestCase):
    def test_start_run_completes_simulated_run_and_emits_ordered_events(self) -> None:
        host = InProcessHost(RunService(InMemoryStateStore(), id_factory=lambda: "run-1"))

        result = host.execute(StartRun("Fix tests"))

        self.assertIsInstance(result.run, RunView)
        self.assertEqual("run-1", result.run.run_id)
        self.assertEqual("COMPLETED", result.run.status)
        self.assertEqual(("EXPLORE_BUNDLE",), result.run.completed_phases)
        self.assertEqual(
            [RunStarted, PhaseStarted, PhaseCompleted, RunCompleted],
            [type(event) for event in result.events],
        )

    def test_start_run_persists_state_in_injected_store(self) -> None:
        store = InMemoryStateStore()
        host = InProcessHost(RunService(store, id_factory=lambda: "run-1"))

        host.execute(StartRun("Fix tests"))

        persisted = store.get("run-1")
        self.assertEqual(RunStatus.COMPLETED, persisted.status)

    def test_queries_return_stable_dtos_for_authoritative_backend_state(self) -> None:
        host = InProcessHost(RunService(InMemoryStateStore(), id_factory=lambda: "run-1"))
        host.execute(StartRun("Fix tests"))

        state = host.query(GetRunState("run-1"))
        actions = host.query(GetAvailableActions("run-1"))
        run = host.query(GetRun("run-1"))
        runs = host.query(ListRuns())

        self.assertIsInstance(state, GetRunStateResult)
        self.assertEqual("COMPLETED", state.status)
        self.assertIsInstance(actions, GetAvailableActionsResult)
        self.assertEqual((), actions.actions)
        self.assertIsInstance(run, GetRunResult)
        self.assertEqual("Fix tests", run.run.request)
        self.assertIsInstance(runs, ListRunsResult)
        self.assertEqual(["run-1"], [summary.run_id for summary in runs.runs])

    def test_resume_pending_run_starts_first_phase_and_persists_state(self) -> None:
        store = InMemoryStateStore()
        store.save(RunRecord(run_id="run-1", request="Fix tests", status=RunStatus.PENDING, strategy=RunStrategy.SDD))
        host = InProcessHost(RunService(store))

        result = host.execute(ResumeRun("run-1"))

        self.assertEqual("RUNNING", result.run.status)
        self.assertEqual("EXPLORE_BUNDLE", result.run.current_phase)
        self.assertEqual([RunResumed, PhaseStarted], [type(event) for event in result.events])
        persisted = store.get("run-1")
        self.assertEqual(RunStatus.RUNNING, persisted.status)
        self.assertEqual(PhaseName.EXPLORE_BUNDLE, persisted.current_phase)

    def test_resume_running_run_emits_resume_event_without_state_rewrite(self) -> None:
        store = InMemoryStateStore()
        store.save(running_run("run-1"))
        host = InProcessHost(RunService(store))

        result = host.execute(ResumeRun("run-1"))

        self.assertEqual("run-1", result.run.run_id)
        self.assertEqual("RUNNING", result.run.status)
        self.assertEqual([RunResumed], [type(event) for event in result.events])
        with self.assertRaises(RunNotFoundError):
            host.execute(ResumeRun("missing"))

    def test_resume_fails_closed_for_waiting_and_terminal_runs(self) -> None:
        decision = PendingDecision("decision-1", PhaseName.EXPLORE_BUNDLE, "Choose", TIMESTAMP)
        cases = (
            RunRecord(
                run_id="waiting",
                request="Fix tests",
                status=RunStatus.WAITING_FOR_USER,
                strategy=RunStrategy.SDD,
                current_phase=PhaseName.EXPLORE_BUNDLE,
                pending_decision=decision,
            ),
            RunRecord(
                run_id="completed",
                request="Fix tests",
                status=RunStatus.COMPLETED,
                strategy=RunStrategy.EXPLORE_BUNDLE,
                completed_phases=(PhaseName.EXPLORE_BUNDLE,),
            ),
            RunRecord(run_id="failed", request="Fix tests", status=RunStatus.FAILED, strategy=RunStrategy.SDD),
            RunRecord(run_id="cancelled", request="Fix tests", status=RunStatus.CANCELLED, strategy=RunStrategy.SDD),
        )
        for run in cases:
            with self.subTest(run=run.run_id):
                store = InMemoryStateStore()
                store.save(run)
                host = InProcessHost(RunService(store))

                with self.assertRaises(InvalidRunStateError):
                    host.execute(ResumeRun(run.run_id))

    def test_running_run_can_be_cancelled(self) -> None:
        store = InMemoryStateStore()
        store.save(running_run("run-1"))
        host = InProcessHost(RunService(store))

        result = host.execute(CancelRun("run-1"))

        self.assertEqual("CANCELLED", result.run.status)
        self.assertEqual(RunStatus.CANCELLED, store.get("run-1").status)

    def test_completed_run_cannot_be_cancelled(self) -> None:
        host = InProcessHost(RunService(InMemoryStateStore(), id_factory=lambda: "run-1"))
        host.execute(StartRun("Fix tests"))

        with self.assertRaises(InvalidRunStateError):
            host.execute(CancelRun("run-1"))

    def test_internal_request_decision_then_public_submit_decision_round_trips_through_backend_events(self) -> None:
        store = InMemoryStateStore()
        store.save(running_run("run-1"))
        decision_service = RequestUserDecisionService(store, timestamp_factory=lambda: TIMESTAMP)
        host = InProcessHost(RunService(store))

        requested = decision_service.execute(DecisionRequest("run-1", "decision-1", "Choose", ("continue", "cancel")))

        self.assertEqual("WAITING_FOR_USER", requested.run.status)
        self.assertIsNotNone(requested.run.pending_decision)
        self.assertEqual("decision-1", requested.run.pending_decision.decision_id)
        self.assertEqual(TIMESTAMP, requested.run.pending_decision.created_at)
        self.assertEqual([UserDecisionRequested], [type(event) for event in requested.events])
        waiting = store.get("run-1")
        self.assertEqual(RunStatus.WAITING_FOR_USER, waiting.status)
        self.assertIsNotNone(waiting.pending_decision)

        submitted = host.execute(SubmitUserDecision("run-1", "decision-1", "continue"))

        self.assertEqual("RUNNING", submitted.run.status)
        self.assertIsNone(submitted.run.pending_decision)
        self.assertEqual([UserDecisionReceived], [type(event) for event in submitted.events])
        persisted = store.get("run-1")
        self.assertEqual(RunStatus.RUNNING, persisted.status)
        self.assertIsNone(persisted.pending_decision)

    def test_internal_request_decision_requires_running_run(self) -> None:
        store = InMemoryStateStore()
        host = InProcessHost(RunService(store, id_factory=lambda: "run-1"))
        host.execute(StartRun("Fix tests"))
        decision_service = RequestUserDecisionService(store, timestamp_factory=lambda: TIMESTAMP)

        with self.assertRaises(InvalidRunStateError):
            decision_service.execute(DecisionRequest("run-1", "decision-1", "Choose"))

    def test_submit_decision_validates_pending_request(self) -> None:
        host = InProcessHost(RunService(InMemoryStateStore(), id_factory=lambda: "run-1"))
        host.execute(StartRun("Fix tests"))

        with self.assertRaises(InvalidRunStateError):
            host.execute(SubmitUserDecision("run-1", "decision-1", "continue"))

    def test_host_delegates_execute_and_query_without_transforming_results(self) -> None:
        class SpyService:
            def __init__(self) -> None:
                self.commands = []
                self.queries = []
                self.command_result = CommandResult(
                    run=RunView("run-1", "Fix tests", "RUNNING", "SDD", current_phase="EXPLORE_BUNDLE"),
                    events=(RunResumed("run-1"),),
                )
                self.query_result: QueryResult = GetRunStateResult("run-1", "RUNNING", "EXPLORE_BUNDLE")

            def execute(self, command: object) -> CommandResult:
                self.commands.append(command)
                return self.command_result

            def query(self, query: object) -> QueryResult:
                self.queries.append(query)
                return self.query_result

        service = SpyService()
        host = InProcessHost(service=service)
        command = ResumeRun("run-1")
        query = GetRunState("run-1")

        self.assertIs(service.command_result, host.execute(command))
        self.assertIs(service.query_result, host.query(query))
        self.assertEqual([command], service.commands)
        self.assertEqual([query], service.queries)


if __name__ == "__main__":
    unittest.main()
