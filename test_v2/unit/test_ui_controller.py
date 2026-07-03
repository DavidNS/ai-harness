from __future__ import annotations

import unittest

from harness_v2.backend.application.contracts import (
    CommandResult,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetRun,
    GetRunResult,
    ListRuns,
    ListRunsResult,
    PendingDecisionView,
    StepStarted,
    RunSummaryView,
    RunView,
    StepView,
    StartRun,
    SubmitUserDecision,
)
from harness_v2.frontends.ui.controller import UiController
from harness_v2.frontends.ui.state import UiState


class FakeUiBackend:
    def __init__(self) -> None:
        self.commands: list[object] = []
        self.queries: list[object] = []
        self.events_cursor: list[int] = []
        self.run = RunView("run-1", "Fix tests", "PENDING", "EXPLORE_BUNDLE")

    def execute(self, command: object) -> object:
        self.commands.append(command)
        if isinstance(command, StartRun):
            self.run = RunView("run-2", command.request, "PENDING", command.root_bundle)
            return CommandResult(self.run, ())
        if isinstance(command, SubmitUserDecision):
            self.run = RunView(command.run_id, "Choose", "RUNNING", "SDD_BUNDLE", current_step=StepView("SDD_BUNDLE:002", "EXPLORE_BUNDLE", "EXPLORE_CONTEXT_PACK", 1))
            return CommandResult(self.run, ())
        return CommandResult(self.run, ())

    def query(self, query: object) -> object:
        self.queries.append(query)
        if isinstance(query, ListRuns):
            return ListRunsResult((RunSummaryView(self.run.run_id, self.run.request, self.run.status, self.run.current_step),))
        if isinstance(query, GetRun):
            return GetRunResult(self.run)
        if isinstance(query, GetAvailableActions):
            return GetAvailableActionsResult(self.run.run_id, ("resume", "cancel"))
        raise TypeError(type(query).__name__)

    def events_after(self, event_id: int, *, timeout: float = 0.0) -> tuple[tuple[int, object], ...]:
        self.events_cursor.append(event_id)
        return ((event_id + 1, StepStarted("run-1", "SDD_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING")),)


class UiControllerTests(unittest.TestCase):
    def test_refresh_loads_run_list_and_selects_first_run(self) -> None:
        backend = FakeUiBackend()
        controller = UiController(backend)

        state = controller.refresh(UiState())

        self.assertEqual("run-1", state.selected_run.run_id if state.selected_run else None)
        self.assertEqual(("resume", "cancel"), state.selected_actions)
        self.assertEqual([ListRuns, GetRun, GetAvailableActions], [type(query) for query in backend.queries])

    def test_start_sends_backend_command_and_selects_created_run(self) -> None:
        backend = FakeUiBackend()
        controller = UiController(backend)

        state = controller.start(UiState(), "Fix tests", root_bundle="EXPLORE_BUNDLE")

        self.assertEqual([StartRun], [type(command) for command in backend.commands])
        self.assertEqual("EXPLORE_BUNDLE", backend.commands[0].root_bundle)
        self.assertEqual("run-2", state.selected_run.run_id if state.selected_run else None)
        self.assertEqual("started run", state.notice)

    def test_submit_decision_uses_pending_decision_from_selected_run(self) -> None:
        backend = FakeUiBackend()
        backend.run = RunView(
            "run-1",
            "Choose",
            "WAITING_FOR_USER",
            "SDD_BUNDLE",
            current_step=StepView("SDD_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING", 0),
            pending_decision=PendingDecisionView("decision-1", "EXPLORE_BUNDLE", "Choose", "now", ("continue",)),
        )
        controller = UiController(backend)
        state = controller.refresh(UiState())

        state = controller.submit_decision(state, "continue")

        self.assertEqual([SubmitUserDecision], [type(command) for command in backend.commands])
        command = backend.commands[0]
        self.assertEqual("decision-1", command.decision_id)
        self.assertEqual("continue", command.response)
        self.assertEqual("submitted decision", state.notice)

    def test_poll_events_advances_cursor(self) -> None:
        backend = FakeUiBackend()
        controller = UiController(backend)

        state = controller.poll_events(UiState(event_cursor=4))

        self.assertEqual([4], backend.events_cursor)
        self.assertEqual(5, state.event_cursor)
        self.assertEqual("StepStarted", state.events[0].event_type)


if __name__ == "__main__":
    unittest.main()
