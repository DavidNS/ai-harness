"""Reusable screen registry for the v2 UI.

Every window in the UI is a ``Screen`` value rendered and navigated by the same
generic machinery. The only per-screen code is a declarative ``ScreenSpec`` here:
a pure ``items`` builder and a ``title``. Items are derived from ``UiState`` on
demand (never cached in the model), so adding a menu is adding one entry — not a
new branch in the renderer or the update loop.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from harness_v2.backend.application.contracts import BUNDLE_VALUES, RunView
from harness_v2.frontends.ui.messages import Back, Invoke, Navigate, Quit
from harness_v2.frontends.ui.state import Choice, Screen, UiState

# Deterministic order for the start-run bundle menu (SDD first, rest sorted).
ROOT_BUNDLES: tuple[str, ...] = ("SDD_BUNDLE", *sorted(BUNDLE_VALUES - {"SDD_BUNDLE"}))

_BACK = Choice("Back", Back())


@dataclass(frozen=True, slots=True)
class ScreenSpec:
    kind: str
    title: Callable[[UiState, tuple[str, ...]], str]
    items: Callable[[UiState, tuple[str, ...]], tuple[Choice, ...]]


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return tuple(seen)


# --- item builders -------------------------------------------------------------


def _home_items(state: UiState, context: tuple[str, ...]) -> tuple[Choice, ...]:
    items = [
        Choice("Start run", Navigate("start-bundle")),
        Choice("Runs", Navigate("runs")),
    ]
    if state.selected_run is not None:
        items.append(Choice("Selected run actions", Navigate("actions")))
    if "submit-user-decision" in state.selected_actions:
        items.append(Choice("Answer decision", Navigate(_decision_screen(state))))
    items.extend(
        (
            Choice("Refresh", Invoke("refresh")),
            Choice("Watch events", Invoke("watch")),
            Choice("Quit", Quit()),
        )
    )
    return tuple(items)


def _runs_items(state: UiState, context: tuple[str, ...]) -> tuple[Choice, ...]:
    items = []
    for run in state.runs:
        phase = f" phase={run.current_step.phase}" if run.current_step else ""
        label = f"{run.run_id} status={run.status}{phase} request={run.request}"
        items.append(Choice(label, Invoke("select", (run.run_id,))))
    return (*items, _BACK)


def _actions_items(state: UiState, context: tuple[str, ...]) -> tuple[Choice, ...]:
    actions = state.selected_actions
    items: list[Choice] = []
    if "resume" in actions:
        items.append(Choice("Resume run", Invoke("resume")))
    if "cancel" in actions:
        items.append(Choice("Cancel run", Invoke("cancel")))
    if "retry-step" in actions or "retry-bundle" in actions:
        items.append(Choice("Retry", Navigate("retry-mode")))
    if "submit-user-decision" in actions:
        items.append(Choice("Answer decision", Navigate(_decision_screen(state))))
    return (*items, _BACK)


def _retry_mode_items(state: UiState, context: tuple[str, ...]) -> tuple[Choice, ...]:
    items: list[Choice] = []
    if "retry-step" in state.selected_actions:
        items.append(Choice("Retry failed step", Navigate("retry-step")))
    if "retry-bundle" in state.selected_actions:
        items.append(Choice("Retry a whole bundle", Navigate("retry-bundle")))
    return (*items, _BACK)


def _retry_bundle_items(state: UiState, context: tuple[str, ...]) -> tuple[Choice, ...]:
    run = state.selected_run
    if run is None:
        return (_BACK,)
    current_bundle = run.current_step.bundle if run.current_step else ""
    bundles = _dedupe((*run.completed_bundles, current_bundle, *(e.bundle or "" for e in run.errors)))
    items = [Choice(bundle, Invoke("retry-bundle", (bundle,))) for bundle in bundles]
    return (*items, _BACK)


def _retry_step_items(state: UiState, context: tuple[str, ...]) -> tuple[Choice, ...]:
    run = state.selected_run
    if run is None or run.current_step is None:
        return (_BACK,)
    step = run.current_step
    label = f"{step.step_id} {step.bundle}/{step.phase}"
    return (Choice(label, Invoke("retry-step", (step.step_id,))), _BACK)


def _start_bundle_items(state: UiState, context: tuple[str, ...]) -> tuple[Choice, ...]:
    items = [Choice(bundle, Navigate("start-request", (bundle,))) for bundle in ROOT_BUNDLES]
    return (*items, _BACK)


def _decision_options_items(state: UiState, context: tuple[str, ...]) -> tuple[Choice, ...]:
    options = _decision_options(state)
    items = [Choice(option, Invoke("decision", (option,))) for option in options]
    return (*items, _BACK)


def _no_items(state: UiState, context: tuple[str, ...]) -> tuple[Choice, ...]:
    return ()


# --- titles --------------------------------------------------------------------


def _const(text: str) -> Callable[[UiState, tuple[str, ...]], str]:
    return lambda state, context: text


def _home_title(state: UiState, context: tuple[str, ...]) -> str:
    return "Dashboard"


# --- registry ------------------------------------------------------------------


SCREENS: dict[str, ScreenSpec] = {
    "home": ScreenSpec("menu", _home_title, _home_items),
    "runs": ScreenSpec("menu", _const("Runs"), _runs_items),
    "actions": ScreenSpec("menu", _const("Actions"), _actions_items),
    "retry-mode": ScreenSpec("menu", _const("Retry"), _retry_mode_items),
    "retry-bundle": ScreenSpec("menu", _const("Choose a bundle to retry"), _retry_bundle_items),
    "retry-step": ScreenSpec("menu", _const("Choose the step"), _retry_step_items),
    "start-bundle": ScreenSpec("menu", _const("Choose a root bundle"), _start_bundle_items),
    "start-request": ScreenSpec("input", _const("request> "), _no_items),
    "decision-options": ScreenSpec("menu", _const("Answer the decision"), _decision_options_items),
    "decision-input": ScreenSpec("input", _const("decision> "), _no_items),
}


def build_items(screen: Screen, state: UiState) -> tuple[Choice, ...]:
    spec = SCREENS.get(screen.screen_id)
    if spec is None:
        return (_BACK,)
    return spec.items(state, screen.context)


def screen_title(screen: Screen, state: UiState) -> str:
    spec = SCREENS.get(screen.screen_id)
    if spec is None:
        return screen.screen_id
    return spec.title(state, screen.context)


def screen_kind(screen_id: str) -> str:
    spec = SCREENS.get(screen_id)
    return spec.kind if spec is not None else "menu"


def make_screen(screen_id: str, context: tuple[str, ...] = ()) -> Screen:
    return Screen(screen_id, kind=screen_kind(screen_id), context=context)


# --- decision helpers ----------------------------------------------------------


def _decision_options(state: UiState) -> tuple[str, ...]:
    run = state.selected_run
    if run is None or run.pending_decision is None:
        return ()
    return run.pending_decision.options


def _decision_screen(state: UiState) -> str:
    return "decision-options" if _decision_options(state) else "decision-input"
