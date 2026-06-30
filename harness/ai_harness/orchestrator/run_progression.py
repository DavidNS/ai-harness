"""Run progression and terminalization coordinator."""

from __future__ import annotations

from typing import Protocol

from ..control_outputs import ControlFlowSignal, parse_decision_answer
from ..errors import StateError
from ..models import RunState, RunStatus
from ..output import RunResult
from ..pipeline.state_machine import graph_for, validate_phase_preconditions
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from .result_publication import ResultPublication
from .run_completion import RunCompletion


class _ProgressionHost(Protocol):
    state: StateStore
    artifacts: ArtifactStore

    def progress(self, message: str) -> None: ...
    def _hydrate_resume_context(self, state: RunState) -> None: ...
    def _phase(self, phase: str) -> None: ...
    def _handle_control_output(self, output: object, *, target_phase: str) -> RunResult | None: ...


class RunProgression:
    """Advance resumed or active runs without owning state mutation rules."""

    def __init__(self, host: _ProgressionHost, publication: ResultPublication) -> None:
        self._host = host
        self._publication = publication
        self._completion = RunCompletion(host, publication)

    def resume(self, run_id: str, decision_answer: str | None = None) -> RunState:
        state = self._host.state.validate_resume(run_id)
        self._host._hydrate_resume_context(state)
        if state.status is RunStatus.WAITING_FOR_USER:
            if decision_answer is not None:
                assert state.pending_decision is not None
                answer = parse_decision_answer(decision_answer, pending_decision_id=state.pending_decision.id)
                state = self._host.state.record_decision_answer(answer)
            return state
        if decision_answer is not None:
            raise StateError("decision answers can only resume waiting runs")
        if state.status is not RunStatus.ACTIVE:
            raise StateError("only an active or waiting run can resume")
        return state

    def execute(self, initial: RunState) -> RunResult:
        del initial
        while True:
            state = self._host.state.load()
            if state.status is RunStatus.WAITING_FOR_USER:
                return self._publication.waiting(state)
            if state.status is RunStatus.IMPOSSIBLE:
                return self._publication.impossible(state)
            if state.status is not RunStatus.ACTIVE:
                raise StateError("only an active run can execute")
            graph = graph_for(state.strategy, state.complexity)
            if len(state.completed_phases) >= len(graph):
                return self._completion.complete(state)
            phase = graph[len(state.completed_phases)]
            validate_phase_preconditions(state.strategy, phase, state.completed_phases, state.tasks, state.complexity)
            self._host.state.validate_resume(state.run_id)
            state = self._host.state.load()
            if state.current_phase != phase:
                state = self._host.state.mark_phase_started(phase)
            self._host.progress(f"Running {phase}")
            try:
                self._host._phase(phase)
            except ControlFlowSignal as signal:
                result = self._host._handle_control_output(signal.output, target_phase=phase)
                if result is not None:
                    return result
                continue
            state = self._host.state.load()
            graph = graph_for(state.strategy, state.complexity)
            if state.status is RunStatus.ACTIVE and phase in graph and phase not in state.completed_phases:
                self._host.state.mark_phase_completed(phase)
