"""Deterministic terminal rendering for the v2 UI frontend."""

from __future__ import annotations

from harness_v2.backend.application.contracts import PendingDecisionView, RunView
from harness_v2.frontends.ui.state import UiState


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
    return "\n".join(lines).rstrip() + "\n"


def _render_runs(state: UiState) -> list[str]:
    lines = ["Runs"]
    if not state.runs:
        return [*lines, "  none"]
    selected_id = state.selected_run.run_id if state.selected_run else None
    for run in state.runs:
        marker = "*" if run.run_id == selected_id else " "
        phase = f" phase={run.current_phase}" if run.current_phase else ""
        lines.append(f"{marker} {run.run_id} status={run.status}{phase} request={run.request}")
    return lines


def _render_selected(run: RunView | None, actions: tuple[str, ...]) -> list[str]:
    if run is None:
        return ["Selected run", "  none"]
    lines = [
        "Selected run",
        f"  id: {run.run_id}",
        f"  status: {run.status}",
        f"  strategy: {run.strategy}",
        f"  request: {run.request}",
    ]
    if run.current_phase:
        lines.append(f"  current phase: {run.current_phase}")
    if run.completed_phases:
        lines.append("  completed: " + " -> ".join(run.completed_phases))
    if run.tasks:
        lines.append("  tasks:")
        for task in run.tasks:
            failure = f" failure={task.last_failure}" if task.last_failure else ""
            lines.append(f"    {task.task_id} {task.status} attempts={task.attempts} title={task.title}{failure}")
    if run.errors:
        lines.append("  errors:")
        for error in run.errors:
            phase = f" phase={error.phase}" if error.phase else ""
            lines.append(f"    {error.code}{phase}: {error.message}")
    if run.pending_decision:
        lines.extend(_render_decision(run.pending_decision))
    lines.append("  actions: " + (", ".join(actions) if actions else "none"))
    return lines


def _render_decision(decision: PendingDecisionView) -> list[str]:
    lines = [
        "  pending decision:",
        f"    id: {decision.decision_id}",
        f"    phase: {decision.origin_phase}",
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
