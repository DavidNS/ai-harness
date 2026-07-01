from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from harness_v2.backend.application.contracts import (
    CancelRun,
    GetAvailableActions,
    GetRun,
    GetRunState,
    ListRuns,
    PhaseCompleted,
    PhaseFailed,
    PhaseStarted,
    ResumeRun,
    RunCancelled,
    RunCompleted,
    RunStarted,
    StartRun,
    SubmitUserDecision,
    UserDecisionReceived,
    UserDecisionRequested,
)


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
            RunCompleted("run-1"),
            RunCancelled("run-1"),
        )

        self.assertEqual("run-1", events[0].run_id)
        self.assertTrue(all(event is not None for event in events))

    def test_text_fields_are_trimmed(self) -> None:
        self.assertEqual("Fix tests", StartRun("  Fix tests  ").request)
        self.assertEqual("run-1", GetRun("  run-1  ").run_id)
        self.assertEqual("EXPLORE_BUNDLE", PhaseStarted("run-1", "  EXPLORE_BUNDLE  ").phase)

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
            lambda: RunCompleted(""),
            lambda: RunCancelled(""),
        )

        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(ValueError):
                    create()

    def test_phase_events_reject_unknown_phase(self) -> None:
        invalid_cases = (
            lambda: PhaseStarted("run-1", "NOT_A_PHASE"),
            lambda: PhaseCompleted("run-1", "NOT_A_PHASE"),
            lambda: PhaseFailed("run-1", "NOT_A_PHASE", "failed"),
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
