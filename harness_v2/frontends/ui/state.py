"""Frontend-owned state for the v2 terminal UI."""

from __future__ import annotations

from dataclasses import dataclass, replace

from harness_v2.backend.application.contracts import Event, RunSummaryView, RunView
from harness_v2.frontends.ui.messages import Msg


@dataclass(frozen=True, slots=True)
class UiEventView:
    event_id: int | None
    event_type: str
    run_id: str | None = None
    summary: str = ""


@dataclass(frozen=True, slots=True)
class Choice:
    """A menu item: a label plus the message it dispatches when activated."""

    label: str
    msg: Msg


@dataclass(frozen=True, slots=True)
class Screen:
    """A reusable navigable window. Items are NOT stored here; they are derived
    purely from state by ``screens.build_items`` so the model never caches
    backend data."""

    screen_id: str
    kind: str = "menu"  # "menu" | "prompt" | "input"
    selected: int = 0
    context: tuple[str, ...] = ()  # accumulated drill-down args (e.g. chosen bundle)


HOME = Screen("home", kind="menu")


@dataclass(frozen=True, slots=True)
class UiState:
    runs: tuple[RunSummaryView, ...] = ()
    selected_run: RunView | None = None
    selected_actions: tuple[str, ...] = ()
    event_cursor: int = 0
    events: tuple[UiEventView, ...] = ()
    error: str | None = None
    notice: str | None = None
    nav: tuple[Screen, ...] = (HOME,)


def clear_messages(state: UiState) -> UiState:
    return replace(state, error=None, notice=None)


def with_error(state: UiState, message: str) -> UiState:
    return replace(state, error=message, notice=None)


def with_notice(state: UiState, message: str) -> UiState:
    return replace(state, error=None, notice=message)


def replace_run_list(state: UiState, runs: tuple[RunSummaryView, ...]) -> UiState:
    selected = state.selected_run
    if selected is not None and all(run.run_id != selected.run_id for run in runs):
        selected = None
    return replace(
        state,
        runs=runs,
        selected_run=selected,
        selected_actions=state.selected_actions if selected is not None else (),
    )


def select_run(state: UiState, run: RunView, actions: tuple[str, ...] = ()) -> UiState:
    return replace(state, selected_run=run, selected_actions=actions)


def append_events(state: UiState, events: tuple[UiEventView, ...], *, limit: int = 50) -> UiState:
    cursor = state.event_cursor
    for event in events:
        if event.event_id is not None:
            cursor = max(cursor, event.event_id)
    return replace(
        state,
        event_cursor=cursor,
        events=(*state.events, *events)[-limit:],
    )


def current_screen(state: UiState) -> Screen:
    return state.nav[-1]


def push_screen(state: UiState, screen: Screen) -> UiState:
    return replace(state, nav=(*state.nav, screen))


def pop_screen(state: UiState) -> UiState:
    if len(state.nav) <= 1:
        return state
    return replace(state, nav=state.nav[:-1])


def home_screen(state: UiState) -> UiState:
    return replace(state, nav=(state.nav[0],))


def move_selection(state: UiState, selected: int) -> UiState:
    top = replace(state.nav[-1], selected=selected)
    return replace(state, nav=(*state.nav[:-1], top))


def event_view(event: Event, event_id: int | None = None) -> UiEventView:
    event_type = type(event).__name__
    run_id = getattr(event, "run_id", None)
    parts: list[str] = []
    for name in ("step_id", "bundle", "phase", "origin_bundle", "decision_id", "issue_id", "category", "action", "target_bundle"):
        value = getattr(event, name, None)
        if value is not None:
            parts.append(f"{name}={value}")
    if event_type == "StepFailed":
        parts.append(f"error={event.error}")
    if event_type == "KnowledgePatchCreated":
        parts.append(f"patch={event.patch_id}")
    if event_type == "UserDecisionRequested":
        if event.options:
            parts.append("options=" + ",".join(event.options))
    return UiEventView(event_id=event_id, event_type=event_type, run_id=run_id, summary=" ".join(parts))
