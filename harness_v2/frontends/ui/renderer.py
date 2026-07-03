"""Deterministic terminal rendering for the v2 UI frontend."""

from __future__ import annotations

from harness_v2.backend.application.contracts import PendingDecisionView, RunView
from harness_v2.frontends.ui.screens import build_items, screen_title
from harness_v2.frontends.ui.state import UiState, current_screen


def render(state: UiState) -> str:
    lines = ["AI Harness v2 UI", ""]
    if state.error:
        lines.extend((f"Error: {state.error}", ""))
    if state.notice:
        lines.extend((f"Notice: {state.notice}", ""))
    lines.extend(_render_runs(state))
    lines.append("")
    lines.extend(_render_selected(state.selected_run, state.selected_actions))
    lines.append("")
    lines.extend(_render_events(state))
    lines.extend(("", render_screen(state).rstrip("\n")))
    return "\n".join(lines).rstrip() + "\n"


def render_screen(state: UiState) -> str:
    """Render the active window. Generic — works for any Screen in the registry."""
    screen = current_screen(state)
    title = screen_title(screen, state)
    if screen.kind == "prompt":
        return f"{title}\n"
    if screen.kind == "input":
        return f"{title}\n(type your answer, empty line cancels)\n"
    items = build_items(screen, state)
    lines = [title]
    for index, item in enumerate(items):
        marker = ">" if index == screen.selected else " "
        lines.append(f"{marker} {index + 1}. {item.label}")
    lines.append("Use Up/Down + Enter, digits, Esc to go back, / for a command.")
    return "\n".join(lines) + "\n"


def _render_runs(state: UiState) -> list[str]:
    lines = ["Runs"]
    if not state.runs:
        return [*lines, "  none"]
    selected_id = state.selected_run.run_id if state.selected_run else None
    for run in state.runs:
        marker = "*" if run.run_id == selected_id else " "
        phase = f" phase={run.current_step.phase}" if run.current_step else ""
        lines.append(f"{marker} {run.run_id} status={run.status}{phase} request={run.request}")
    return lines


def _render_selected(run: RunView | None, actions: tuple[str, ...]) -> list[str]:
    if run is None:
        return ["Selected run", "  none"]
    lines = [
        "Selected run",
        f"  id: {run.run_id}",
        f"  status: {run.status}",
        f"  root bundle: {run.root_bundle}",
        f"  request: {run.request}",
    ]
    if run.current_step:
        step = run.current_step
        lines.append(f"  current step: {step.step_id} {step.bundle}/{step.phase}")
    if run.completed_steps:
        lines.append("  completed: " + " -> ".join(step.phase for step in run.completed_steps))
    if run.tasks:
        lines.append("  tasks:")
        for task in run.tasks:
            failure = f" failure={task.last_failure}" if task.last_failure else ""
            lines.append(f"    {task.task_id} {task.status} attempts={task.attempts} title={task.title}{failure}")
    if run.errors:
        lines.append("  errors:")
        for error in run.errors:
            step = f" step={error.step_id}" if error.step_id else ""
            phase = f" phase={error.phase}" if error.phase else ""
            lines.append(f"    {error.code}{step}{phase}: {error.message}")
    if run.pending_decision:
        lines.extend(_render_decision(run.pending_decision))
    lines.append("  actions: " + (", ".join(actions) if actions else "none"))
    return lines


def _render_decision(decision: PendingDecisionView) -> list[str]:
    lines = [
        "  pending decision:",
        f"    id: {decision.decision_id}",
        f"    bundle: {decision.origin_bundle}",
        f"    prompt: {decision.prompt}",
    ]
    if decision.options:
        lines.append("    options: " + ", ".join(decision.options))
    return lines


def _render_events(state: UiState) -> list[str]:
    lines = [f"Events after cursor {state.event_cursor}"]
    if not state.events:
        return [*lines, "  none"]
    for event in state.events:
        event_id = "-" if event.event_id is None else str(event.event_id)
        run = f" run={event.run_id}" if event.run_id else ""
        summary = f" {event.summary}" if event.summary else ""
        lines.append(f"  {event_id}: {event.event_type}{run}{summary}")
    return lines
