"""Run-result assembly for orchestrator lifecycle outcomes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from ..models import RunState, Strategy, Task
from ..output import RunResult
from ..pipeline.state_machine import graph_for
from ..router import RouteDecision
from ..strategy import StrategyDecision


def task_summary(tasks: Sequence[Task]) -> str:
    return ", ".join(f"{task.id}={task.status.value}" for task in tasks) or "none"


def has_partial_success(warnings: Sequence[str]) -> bool:
    return any("persistence failed" in warning or "Learning failed" in warning for warning in warnings)


def run_outcome(state: RunState, warnings: Sequence[str]) -> str:
    if state.strategy is Strategy.NON_CODE_STUB:
        return "non-code stub"
    if has_partial_success(warnings):
        return "partial success"
    return "success"


def completed_result(
    state: RunState,
    route: RouteDecision,
    strategy: StrategyDecision,
    *,
    artifacts: Sequence[str],
    snapshot: Path,
    warnings: Sequence[str],
) -> RunResult:
    return RunResult(
        state.run_id,
        route,
        strategy,
        graph_for(state.strategy, state.complexity),
        task_summary(state.tasks),
        tuple(artifacts),
        run_outcome(state, warnings),
        snapshot,
        tuple(warnings),
    )


def waiting_result(
    state: RunState,
    route: RouteDecision,
    strategy: StrategyDecision,
    *,
    artifacts: Sequence[str],
    request: Mapping[str, object],
    warnings: Sequence[str],
) -> RunResult:
    assert state.pending_decision is not None
    return RunResult(
        state.run_id,
        route,
        strategy,
        graph_for(state.strategy, state.complexity),
        task_summary(state.tasks),
        tuple(artifacts),
        "waiting_for_user",
        None,
        tuple(warnings),
        {"decision_id": state.pending_decision.id, "request": request, "selected_model": state.selected_model},
    )


def impossible_result(
    state: RunState,
    route: RouteDecision,
    strategy: StrategyDecision,
    *,
    artifacts: Sequence[str],
    warnings: Sequence[str],
) -> RunResult:
    return RunResult(
        state.run_id,
        route,
        strategy,
        graph_for(state.strategy, state.complexity),
        task_summary(state.tasks),
        tuple(artifacts),
        "impossible",
        None,
        tuple(warnings),
        {"artifact": "impossible.json"},
    )
