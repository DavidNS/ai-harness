"""Controller for the v2 terminal UI over the daemon host contract."""

from __future__ import annotations

from typing import Protocol

from harness_v2.backend.application.contracts import (
    CancelRun,
    CommandResult,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetRun,
    GetRunResult,
    ListRuns,
    ListRunsResult,
    QueryResult,
    ResumeRun,
    RetryPhase,
    StartRun,
    SubmitUserDecision,
)
from harness_v2.hosts.daemon.client import DaemonClient
from harness_v2.frontends.ui.state import UiState, append_events, event_view, replace_run_list, select_run, with_error, with_notice


class UiBackend(Protocol):
    def execute(self, command: object) -> object: ...

    def query(self, query: object) -> QueryResult: ...

    def events_after(self, event_id: int, *, timeout: float = 0.0) -> tuple[tuple[int, object], ...]: ...


class UiController:
    def __init__(self, backend: UiBackend | None = None) -> None:
        self._backend = backend or DaemonClient()

    def refresh(self, state: UiState) -> UiState:
        try:
            listed = self._backend.query(ListRuns())
            if not isinstance(listed, ListRunsResult):
                raise TypeError("ListRuns returned an unexpected result")
            next_state = replace_run_list(state, listed.runs)
            selected_id = next_state.selected_run.run_id if next_state.selected_run else None
            if selected_id is None and listed.runs:
                selected_id = listed.runs[0].run_id
            if selected_id is not None:
                next_state = self._load_selected(next_state, selected_id)
            return next_state
        except Exception as exc:
            return with_error(state, str(exc))

    def select(self, state: UiState, run_id: str) -> UiState:
        try:
            return self._load_selected(state, run_id)
        except Exception as exc:
            return with_error(state, str(exc))

    def start(self, state: UiState, request: str, *, strategy: str = "SDD") -> UiState:
        return self._execute_run_command(state, StartRun(request=request, strategy=strategy), "started run")

    def resume(self, state: UiState) -> UiState:
        run_id = self._selected_run_id(state)
        if run_id is None:
            return with_error(state, "select a run before resuming")
        return self._execute_run_command(state, ResumeRun(run_id), "resumed run")

    def cancel(self, state: UiState) -> UiState:
        run_id = self._selected_run_id(state)
        if run_id is None:
            return with_error(state, "select a run before cancelling")
        return self._execute_run_command(state, CancelRun(run_id), "cancelled run")

    def retry(self, state: UiState, phase: str) -> UiState:
        run_id = self._selected_run_id(state)
        if run_id is None:
            return with_error(state, "select a run before retrying")
        return self._execute_run_command(state, RetryPhase(run_id, phase), "retry started")

    def submit_decision(self, state: UiState, response: str) -> UiState:
        run = state.selected_run
        if run is None:
            return with_error(state, "select a run before submitting a decision")
        if run.pending_decision is None:
            return with_error(state, f"run {run.run_id} has no pending decision")
        command = SubmitUserDecision(run.run_id, run.pending_decision.decision_id, response)
        return self._execute_run_command(state, command, "submitted decision")

    def poll_events(self, state: UiState, *, timeout: float = 0.0) -> UiState:
        try:
            logged = self._backend.events_after(state.event_cursor, timeout=timeout)
            views = tuple(event_view(event, event_id) for event_id, event in logged)
            return append_events(state, views)
        except Exception as exc:
            return with_error(state, str(exc))

    def _load_selected(self, state: UiState, run_id: str) -> UiState:
        run_result = self._backend.query(GetRun(run_id))
        if not isinstance(run_result, GetRunResult):
            raise TypeError("GetRun returned an unexpected result")
        actions_result = self._backend.query(GetAvailableActions(run_id))
        if not isinstance(actions_result, GetAvailableActionsResult):
            raise TypeError("GetAvailableActions returned an unexpected result")
        return select_run(state, run_result.run, actions_result.actions)

    def _execute_run_command(self, state: UiState, command: object, notice: str) -> UiState:
        try:
            result = self._backend.execute(command)
            if not isinstance(result, CommandResult):
                raise TypeError("command returned an unexpected result")
            next_state = select_run(state, result.run)
            next_state = append_events(next_state, tuple(event_view(event) for event in result.events))
            next_state = self.refresh(next_state)
            return with_notice(next_state, notice)
        except Exception as exc:
            return with_error(state, str(exc))

    def _selected_run_id(self, state: UiState) -> str | None:
        if state.selected_run is None:
            return None
        return state.selected_run.run_id
