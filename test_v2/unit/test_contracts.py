from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
import json
import unittest

from harness_v2.backend.application.contracts import (
    CancelRun,
    CommandResult,
    ErrorView,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetRun,
    GetRunResult,
    GetRunState,
    GetRunStateResult,
    ListRuns,
    ListRunsResult,
    PendingDecisionView,
    PhaseCompleted,
    PhaseFailed,
    PhaseStarted,
    ResumeRun,
    RunCancelled,
    RunCompleted,
    RunResumed,
    RunStarted,
    RunSummaryView,
    RunView,
    StartRun,
    SubmitUserDecision,
    TaskSummaryView,
    UserDecisionReceived,
    UserDecisionRequested,
)
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord


class ContractTests(unittest.TestCase):
    def test_all_commands_can_be_created_with_valid_data(self) -> None:
        commands = (
            StartRun("Fix tests"),
            ResumeRun("run-1"),
            CancelRun("run-1"),
            SubmitUserDecision("run-1", "decision-1", "continue"),
        )

        self.assertEqual("Fix tests", commands[0].request)
        self.assertTrue(all(command is not None for command in commands))

    def test_all_queries_can_be_created_with_valid_data(self) -> None:
        queries = (
            GetRun("run-1"),
            ListRuns(),
            GetRunState("run-1"),
            GetAvailableActions("run-1"),
        )

        self.assertTrue(all(query is not None for query in queries))

    def test_all_events_can_be_created_with_valid_data(self) -> None:
        events = (
            RunStarted("run-1", "Fix tests"),
            PhaseStarted("run-1", "EXPLORE_BUNDLE"),
            PhaseCompleted("run-1", "EXPLORE_BUNDLE"),
            PhaseFailed("run-1", "EXPLORE_BUNDLE", "failed"),
            UserDecisionRequested("run-1", "decision-1", "Choose", ("continue",)),
            UserDecisionReceived("run-1", "decision-1", "continue"),
            RunResumed("run-1"),
            RunCompleted("run-1"),
            RunCancelled("run-1"),
        )

        self.assertEqual("run-1", events[0].run_id)
        self.assertTrue(all(event is not None for event in events))

    def test_result_dtos_can_be_created_with_valid_data(self) -> None:
        decision = PendingDecisionView("decision-1", "EXPLORE_BUNDLE", "Choose", "2026-07-01T00:00:00+00:00", ("continue",))
        task = TaskSummaryView("task-1", "Implement", "IN_PROGRESS")
        error = ErrorView("E001", "failed", "EXPLORE_BUNDLE", "2026-07-01T00:00:00+00:00")
        run = RunView(
            run_id="run-1",
            request="Fix tests",
            status="WAITING_FOR_USER",
            strategy="SDD",
            current_phase="EXPLORE_BUNDLE",
            completed_phases=(),
            pending_decision=decision,
            tasks=(task,),
            errors=(error,),
        )

        results = (
            CommandResult(run=run, events=(RunStarted("run-1", "Fix tests"),)),
            GetRunResult(run=run),
            ListRunsResult(runs=(RunSummaryView("run-1", "Fix tests", "WAITING_FOR_USER", "EXPLORE_BUNDLE"),)),
            GetRunStateResult("run-1", "WAITING_FOR_USER", "EXPLORE_BUNDLE", decision),
            GetAvailableActionsResult("run-1", ("submit-user-decision", "cancel")),
        )

        self.assertTrue(all(result is not None for result in results))
        self.assertEqual("WAITING_FOR_USER", run.status)
        self.assertEqual("EXPLORE_BUNDLE", run.current_phase)

    def test_result_dtos_are_json_serializable(self) -> None:
        result = CommandResult(
            run=RunView(
                run_id="run-1",
                request="Fix tests",
                status="COMPLETED",
                strategy="EXPLORE_BUNDLE",
                completed_phases=("EXPLORE_BUNDLE",),
            ),
            events=(RunCompleted("run-1"),),
        )

        encoded = json.dumps(asdict(result), sort_keys=True)

        self.assertIn('"status": "COMPLETED"', encoded)
        self.assertIn('"completed_phases": ["EXPLORE_BUNDLE"]', encoded)

    def test_result_dtos_reject_raw_domain_objects(self) -> None:
        domain_run = RunRecord(
            run_id="run-1",
            request="Fix tests",
            status=RunStatus.COMPLETED,
            strategy=RunStrategy.EXPLORE_BUNDLE,
            completed_phases=(PhaseName.EXPLORE_BUNDLE,),
        )

        invalid_cases = (
            lambda: CommandResult(run=domain_run, events=()),
            lambda: GetRunResult(run=domain_run),
            lambda: ListRunsResult(runs=(domain_run,)),
        )

        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(TypeError):
                    create()

    def test_result_dtos_reject_non_serializable_nested_objects(self) -> None:
        invalid_cases = (
            lambda: RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE", tasks=(object(),)),
            lambda: RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE", errors=(object(),)),
            lambda: RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE", pending_decision=object()),
            lambda: GetRunStateResult("run-1", "WAITING_FOR_USER", pending_decision=object()),
            lambda: CommandResult(
                run=RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE"),
                events=(object(),),
            ),
        )

        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(TypeError):
                    create()

    def test_result_dtos_reject_unknown_status_and_strategy(self) -> None:
        invalid_cases = (
            lambda: RunView("run-1", "Fix tests", "NOT_A_STATUS", "EXPLORE_BUNDLE"),
            lambda: RunView("run-1", "Fix tests", "COMPLETED", "NOT_A_STRATEGY"),
            lambda: RunSummaryView("run-1", "Fix tests", "NOT_A_STATUS"),
            lambda: GetRunStateResult("run-1", "NOT_A_STATUS"),
        )

        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(ValueError):
                    create()

    def test_text_fields_are_trimmed(self) -> None:
        self.assertEqual("Fix tests", StartRun("  Fix tests  ").request)
        self.assertEqual("run-1", GetRun("  run-1  ").run_id)
        self.assertEqual("EXPLORE_BUNDLE", PhaseStarted("run-1", "  EXPLORE_BUNDLE  ").phase)
        self.assertEqual("COMPLETED", RunView("run-1", "Fix", "  COMPLETED  ", "SDD").status)

    def test_commands_reject_missing_required_text(self) -> None:
        invalid_cases = (
            lambda: StartRun(" "),
            lambda: ResumeRun(""),
            lambda: CancelRun(""),
            lambda: SubmitUserDecision("", "decision-1", "continue"),
            lambda: SubmitUserDecision("run-1", "", "continue"),
            lambda: SubmitUserDecision("run-1", "decision-1", ""),
        )

        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(ValueError):
                    create()

    def test_queries_reject_missing_required_text(self) -> None:
        for query_type in (GetRun, GetRunState, GetAvailableActions):
            with self.subTest(query_type=query_type.__name__):
                with self.assertRaises(ValueError):
                    query_type("")

    def test_events_reject_missing_required_text(self) -> None:
        invalid_cases = (
            lambda: RunStarted("", "Fix tests"),
            lambda: RunStarted("run-1", ""),
            lambda: PhaseStarted("", "EXPLORE_BUNDLE"),
            lambda: PhaseStarted("run-1", ""),
            lambda: PhaseCompleted("", "EXPLORE_BUNDLE"),
            lambda: PhaseCompleted("run-1", ""),
            lambda: PhaseFailed("", "EXPLORE_BUNDLE", "failed"),
            lambda: PhaseFailed("run-1", "", "failed"),
            lambda: PhaseFailed("run-1", "EXPLORE_BUNDLE", ""),
            lambda: UserDecisionRequested("", "decision-1", "Choose"),
            lambda: UserDecisionRequested("run-1", "", "Choose"),
            lambda: UserDecisionRequested("run-1", "decision-1", ""),
            lambda: UserDecisionReceived("", "decision-1", "continue"),
            lambda: UserDecisionReceived("run-1", "", "continue"),
            lambda: UserDecisionReceived("run-1", "decision-1", ""),
            lambda: RunResumed(""),
            lambda: RunCompleted(""),
            lambda: RunCancelled(""),
        )

        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(ValueError):
                    create()

    def test_result_dtos_reject_missing_required_text(self) -> None:
        invalid_cases = (
            lambda: RunView("", "Fix tests", "COMPLETED", "SDD"),
            lambda: RunView("run-1", "", "COMPLETED", "SDD"),
            lambda: RunSummaryView("run-1", "Fix tests", ""),
            lambda: PendingDecisionView("", "EXPLORE_BUNDLE", "Choose", "now"),
            lambda: TaskSummaryView("task-1", "", "TODO"),
            lambda: ErrorView("E001", "", timestamp="now"),
            lambda: GetAvailableActionsResult("run-1", ("resume", "resume")),
        )

        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(ValueError):
                    create()

    def test_phase_values_reject_unknown_phase(self) -> None:
        invalid_cases = (
            lambda: PhaseStarted("run-1", "NOT_A_PHASE"),
            lambda: PhaseCompleted("run-1", "NOT_A_PHASE"),
            lambda: PhaseFailed("run-1", "NOT_A_PHASE", "failed"),
            lambda: RunView("run-1", "Fix", "RUNNING", "SDD", current_phase="NOT_A_PHASE"),
            lambda: PendingDecisionView("decision-1", "NOT_A_PHASE", "Choose", "now"),
        )

        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(ValueError):
                    create()

    def test_event_immutability(self) -> None:
        event = RunStarted(run_id="run-1", request="Fix tests")

        with self.assertRaises(FrozenInstanceError):
            event.run_id = "run-2"

    def test_user_decision_requested_normalizes_options_to_tuple(self) -> None:
        event = UserDecisionRequested(
            run_id="run-1",
            decision_id="decision-1",
            prompt="Choose",
            options=["continue", "cancel"],
        )

        self.assertEqual(("continue", "cancel"), event.options)

    def test_user_decision_requested_rejects_duplicate_options(self) -> None:
        with self.assertRaises(ValueError):
            UserDecisionRequested(
                run_id="run-1",
                decision_id="decision-1",
                prompt="Choose",
                options=["continue", "continue"],
            )


if __name__ == "__main__":
    unittest.main()
