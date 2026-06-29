"""Fail-closed pipeline transition validation."""

from __future__ import annotations

from collections.abc import Sequence

from ..errors import TransitionError, ValidationError
from ..models import Complexity, Strategy, Task, validate_tasks
from . import full_sdd, explorer, non_code, simple

GRAPHS = {
    Strategy.SDD: full_sdd.PHASES,
    Strategy.EXPLORER: explorer.PHASES,
    Strategy.NON_CODE_STUB: non_code.PHASES,
}


def graph_for(strategy: Strategy, complexity: Complexity | str | None = None) -> tuple[str, ...]:
    if strategy is Strategy.SDD and str(complexity or "") == Complexity.LOW.value:
        return simple.PHASES
    return GRAPHS[strategy]


def allowed_transitions(strategy: Strategy, complexity: Complexity | str | None = None) -> frozenset[tuple[str, str]]:
    phases = graph_for(strategy, complexity)
    normal = {(left, right) for left, right in zip(phases, phases[1:])}
    failures = {(phase, "FAILED") for phase in phases if phase not in {"COMPLETED", "FAILED"}}
    return frozenset(normal | failures)


def validate_transition(strategy: Strategy, current: str, target: str, complexity: Complexity | str | None = None) -> None:
    if (current, target) not in allowed_transitions(strategy, complexity):
        raise TransitionError(f"illegal {strategy.value} transition: {current} -> {target}")


def validate_phase_preconditions(strategy: Strategy, phase: str, completed: Sequence[str], tasks: Sequence[Task] = (), complexity: Complexity | str | None = None) -> None:
    graph = graph_for(strategy, complexity)
    if phase not in graph:
        raise ValidationError(f"phase {phase} is not in the selected graph")
    if len(completed) != len(set(completed)):
        raise ValidationError("completed phases must be unique")
    required = set(graph[:graph.index(phase)])
    if not required <= set(completed):
        raise ValidationError("phase prerequisites are incomplete")
    validate_tasks(tasks)
