"""Frontend-owned state for the v2 terminal UI."""

from __future__ import annotations

from dataclasses import dataclass

from harness_v2.backend.application.contracts import Event, RunSummaryView, RunView


@dataclass(frozen=True, slots=True)
class UiEventView:
    event_id: int | None
    event_type: str
    run_id: str | None = None
    summary: str = ""


@dataclass(frozen=True, slots=True)
class UiState:
    runs: tuple[RunSummaryView, ...] = ()
    selected_run: RunView | None = None
    selected_actions: tuple[str, ...] = ()
    event_cursor: int = 0
    events: tuple[UiEventView, ...] = ()
    error: str | None = None
    notice: str | None = None


def clear_messages(state: UiState) -> UiState:
    return UiState(
        runs=state.runs,
        selected_run=state.selected_run,
        selected_actions=state.selected_actions,
        event_cursor=state.event_cursor,
        events=state.events,
        error=None,
        notice=None,
    )


def with_error(state: UiState, message: str) -> UiState:
    clean = clear_messages(state)
    return UiState(
        runs=clean.runs,
        selected_run=clean.selected_run,
        selected_actions=clean.selected_actions,
        event_cursor=clean.event_cursor,
        events=clean.events,
        error=message,
    )


def with_notice(state: UiState, message: str) -> UiState:
    clean = clear_messages(state)
    return UiState(
        runs=clean.runs,
        selected_run=clean.selected_run,
        selected_actions=clean.selected_actions,
        event_cursor=clean.event_cursor,
        events=clean.events,
        notice=message,
    )


def replace_run_list(state: UiState, runs: tuple[RunSummaryView, ...]) -> UiState:
    selected = state.selected_run
    if selected is not None and all(run.run_id != selected.run_id for run in runs):
        selected = None
    return UiState(
        runs=runs,
        selected_run=selected,
        selected_actions=state.selected_actions if selected is not None else (),
        event_cursor=state.event_cursor,
        events=state.events,
        error=state.error,
        notice=state.notice,
    )


def select_run(state: UiState, run: RunView, actions: tuple[str, ...] = ()) -> UiState:
    return UiState(
        runs=state.runs,
        selected_run=run,
        selected_actions=actions,
        event_cursor=state.event_cursor,
        events=state.events,
        error=state.error,
        notice=state.notice,
    )


def append_events(state: UiState, events: tuple[UiEventView, ...], *, limit: int = 50) -> UiState:
    cursor = state.event_cursor
    for event in events:
        if event.event_id is not None:
            cursor = max(cursor, event.event_id)
    return UiState(
        runs=state.runs,
        selected_run=state.selected_run,
        selected_actions=state.selected_actions,
        event_cursor=cursor,
        events=(*state.events, *events)[-limit:],
        error=state.error,
        notice=state.notice,
    )


def event_view(event: Event, event_id: int | None = None) -> UiEventView:
    event_type = type(event).__name__
    run_id = getattr(event, "run_id", None)
    parts: list[str] = []
    for name in ("phase", "origin_phase", "decision_id", "issue_id", "category", "action", "target_phase"):
        value = getattr(event, name, None)
        if value is not None:
            parts.append(f"{name}={value}")
    if event_type == "PhaseFailed":
        parts.append(f"error={event.error}")
    if event_type == "KnowledgePatchCreated":
        parts.append(f"patch={event.patch_id}")
    if event_type == "UserDecisionRequested":
        if event.options:
            parts.append("options=" + ",".join(event.options))
    return UiEventView(event_id=event_id, event_type=event_type, run_id=run_id, summary=" ".join(parts))
