"""Controller-only state mutation and strict resume validation."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from ...control_outputs import DecisionAnswer, DecisionRequest, ImpossibleOutcome, PhaseEscalation
from ...errors import StateError, ValidationError
from ...models import (
    ErrorRecord,
    PendingDecision,
    RunState,
    RunStatus,
    TaskStatus,
    run_state_from_dict,
    utc_now,
    validate_tasks,
)
from ...pipeline.state_machine import graph_for, validate_transition
from ..artifact import ArtifactStore
from ..live_registry import OPEN_STATUSES, LiveRunRegistry
from .records import (
    artifact_metadata,
    decision_history,
    escalation_history,
    next_control_id,
    next_decision_id,
)


def _bundle_phase_for(phase: str) -> str:
    mapping = {
        "EXPLORE": "EXPLORE_BUNDLE",
        "EXPLORER": "EXPLORE_BUNDLE",
        "EXPLORER_INTAKE": "EXPLORE_BUNDLE",
        "EXPLORER_DISCOVERY": "EXPLORE_BUNDLE",
        "EXPLORER_DECISION": "EXPLORE_BUNDLE",
        "EXPLORER_ARTIFACT": "EXPLORE_BUNDLE",
        "EXPLORER_REVIEW": "EXPLORE_BUNDLE",
        "PURPOSE": "PROPOSAL_BUNDLE",
        "PROPOSAL": "PROPOSAL_BUNDLE",
        "SPEC": "SPEC_BUNDLE",
        "DESIGN": "DESIGN_BUNDLE",
        "TASKS": "TASKS_BUNDLE",
        "SIMPLE_TASK": "TASKS_BUNDLE",
        "TDD_LOOP": "TDD_BUNDLE",
        "IMPLEMENT": "TDD_BUNDLE",
        "IMPLEMENTING": "TDD_BUNDLE",
        "TEST": "TDD_BUNDLE",
        "REVIEW": "TDD_BUNDLE",
    }
    return mapping.get(str(phase), str(phase))


class StateStore:
    """The controller's sole mutable interface to operational state."""

    def __init__(self, target_repository: Path, artifacts: ArtifactStore | None = None) -> None:
        self.artifacts = artifacts or ArtifactStore(target_repository)
        self._state_name = "state.json"

    def load(self) -> RunState:
        if not self.artifacts.exists(self._state_name):
            raise StateError("state does not exist")
        value = self.artifacts.read_json(self._state_name)
        if not isinstance(value, dict):
            raise StateError("state must be a JSON object")
        try:
            return run_state_from_dict(value)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise StateError("state is malformed") from exc

    def save(self, state: RunState) -> None:
        state.validate()
        validate_tasks(state.tasks)
        state.updated_at = utc_now()
        self.artifacts.write_json(self._state_name, state.to_dict())
        self._record_live_status(state)

    def update(self, **fields: Any) -> RunState:
        state = self.load()
        unknown = set(fields) - set(state.__dataclass_fields__)
        if unknown:
            raise StateError(f"unknown state fields: {sorted(unknown)}")
        for name, value in fields.items():
            setattr(state, name, value)
        self.save(state)
        return state

    def mark_phase_started(self, phase: str) -> RunState:
        state = self.load()
        if state.status is not RunStatus.ACTIVE:
            raise StateError("only an active run can start a phase")
        if phase in state.completed_phases:
            raise StateError(f"phase is already completed: {phase}")
        if phase != state.current_phase:
            validate_transition(state.strategy, state.current_phase, phase, state.complexity)
            state.current_phase = phase
        self.save(state)
        return state

    def mark_phase_completed(self, phase: str) -> RunState:
        state = self.load()
        if state.status is not RunStatus.ACTIVE:
            raise StateError("only an active run can complete a phase")
        if state.current_phase != phase or phase in state.completed_phases:
            raise StateError("only the active, incomplete phase can complete")
        state.completed_phases.append(phase)
        if phase == "COMPLETED":
            state.status = RunStatus.COMPLETED
            state.finished_at = utc_now()
        self.save(state)
        return state

    def prepare_completion(self) -> RunState:
        """Build terminal state without exposing it as the live state yet."""
        state = self.load()
        graph = graph_for(state.strategy, state.complexity)
        if state.completed_phases != list(graph):
            raise StateError("completion requires every selected bundle phase")
        finished_at = utc_now()
        terminal = replace(
            state,
            current_phase="COMPLETED",
            status=RunStatus.COMPLETED,
            updated_at=finished_at,
            finished_at=finished_at,
        )
        terminal.validate()
        validate_tasks(terminal.tasks)
        return terminal

    def commit_completion(self, terminal: RunState) -> RunState:
        """Atomically publish the already-snapshotted terminal state."""
        if terminal.status is not RunStatus.COMPLETED or terminal.current_phase != "COMPLETED":
            raise StateError("completion state is not terminal")
        terminal.validate()
        validate_tasks(terminal.tasks)
        self.artifacts.write_json(self._state_name, terminal.to_dict())
        self._record_live_status(terminal)
        return terminal

    def _record_live_status(self, state: RunState) -> None:
        pid = os.getpid() if state.status.value in OPEN_STATUSES else None
        LiveRunRegistry(self.artifacts.target_repository).record(
            state.run_id,
            self.artifacts.current,
            state.status.value,
            created_at=state.started_at,
            updated_at=state.updated_at,
            pid=pid,
        )

    def mark_phase_failed(self, phase: str, error: ErrorRecord | str) -> RunState:
        state = self.load()
        if state.status is not RunStatus.ACTIVE:
            raise StateError("only an active run can fail")
        if state.current_phase != phase:
            raise StateError("only the active phase can fail")
        validate_transition(state.strategy, phase, "FAILED", state.complexity)
        state.current_phase = "FAILED"
        state.failed_phases.append(phase)
        state.errors.append(error if isinstance(error, ErrorRecord) else ErrorRecord("phase_failed", error, phase))
        state.status = RunStatus.FAILED
        state.finished_at = utc_now()
        self.save(state)
        return state

    def record_artifact(self, name: str, phase: str) -> RunState:
        state = self.load()
        state.artifacts[name] = artifact_metadata(self.artifacts, name, phase)
        self.save(state)
        return state

    def record_decision_request(self, request: DecisionRequest, *, target_phase: str) -> RunState:
        state = self.load()
        if state.status is not RunStatus.ACTIVE or state.pending_decision is not None:
            raise StateError("only an active run without a pending decision can wait")
        if target_phase not in graph_for(state.strategy, state.complexity):
            raise StateError("pending decision target phase is not valid for the strategy")
        decision_id = next_decision_id(state)
        request = request.with_id(decision_id)
        name = f"decisions/{decision_id}/request.json"
        self.artifacts.write_json(name, request.to_dict())
        state.artifacts[name] = artifact_metadata(self.artifacts, name, request.origin_phase)
        state.status = RunStatus.WAITING_FOR_USER
        state.current_phase = target_phase
        state.pending_decision = PendingDecision(decision_id, request.origin_phase, target_phase, name)
        self.save(state)
        return state

    def record_decision_answer(self, answer: DecisionAnswer) -> RunState:
        state = self.load()
        pending = state.pending_decision
        if state.status is not RunStatus.WAITING_FOR_USER or pending is None:
            raise StateError("run is not waiting for a decision answer")
        if answer.decision_id != pending.id:
            raise StateError("answer decision ID does not match the pending decision")
        name = f"decisions/{pending.id}/answer.json"
        if self.artifacts.exists(name):
            raise StateError("pending decision already has an answer")
        request = self.artifacts.read_json(pending.request_artifact)
        options = request.get("options", []) if isinstance(request, dict) else []
        option_ids = {item.get("id") for item in options if isinstance(item, dict)}
        if answer.selected_option is not None and answer.selected_option not in option_ids:
            raise StateError("selected option does not match the pending decision")
        self.artifacts.write_json(name, answer.to_dict())
        state.artifacts[name] = artifact_metadata(self.artifacts, name, pending.origin_phase)
        state.status = RunStatus.ACTIVE
        state.current_phase = pending.target_phase
        state.pending_decision = None
        self.save(state)
        return state

    def record_phase_escalation(self, escalation: PhaseEscalation, *, active_graph_phase: str) -> RunState:
        state = self.load()
        if state.status is not RunStatus.ACTIVE:
            raise StateError("only an active run can escalate a phase")
        graph = graph_for(state.strategy, state.complexity)
        target_phase = _bundle_phase_for(escalation.target_phase)
        active_graph_phase = _bundle_phase_for(active_graph_phase)
        if target_phase not in graph or active_graph_phase not in graph:
            raise StateError("phase escalation references a phase outside the selected graph")
        target_index = graph.index(target_phase)
        active_index = graph.index(active_graph_phase)
        if target_index >= active_index:
            raise StateError("phase escalation target must be earlier than the active graph phase")
        name = f"escalations/{next_control_id(state, 'E', 'escalations')}.json"
        payload = escalation.to_dict() | {"created_at": utc_now(), "active_graph_phase": active_graph_phase, "target_bundle": target_phase}
        self.artifacts.write_json(name, payload)
        state.artifacts[name] = artifact_metadata(self.artifacts, name, "CONTROL")

        invalidated = set(graph[target_index:])
        for artifact, metadata in list(state.artifacts.items()):
            if artifact == name or artifact.startswith("decisions/") or artifact.startswith("escalations/"):
                continue
            if metadata.get("phase") in invalidated:
                self.artifacts.delete(artifact)
                del state.artifacts[artifact]
        state.completed_phases = list(graph[:target_index])
        state.current_phase = target_phase
        if {"TASKS_BUNDLE", "TDD_BUNDLE"} & invalidated:
            state.tasks = []
        self.save(state)
        return state

    def mark_impossible(self, impossible: ImpossibleOutcome) -> RunState:
        state = self.load()
        if state.status is not RunStatus.ACTIVE:
            raise StateError("only an active run can be marked impossible")
        name = "impossible.json"
        payload = impossible.to_dict() | {"created_at": utc_now()}
        self.artifacts.write_json(name, payload)
        state.artifacts[name] = artifact_metadata(self.artifacts, name, impossible.origin_phase)
        state.current_phase = "IMPOSSIBLE"
        state.status = RunStatus.IMPOSSIBLE
        state.pending_decision = None
        state.finished_at = utc_now()
        self.save(state)
        return state

    def decision_history(self) -> list[dict[str, object]]:
        return decision_history(self.load(), self.artifacts)

    def escalation_history(self) -> list[dict[str, object]]:
        return escalation_history(self.load(), self.artifacts)

    def validate_resume(self, expected_run_id: str) -> RunState:
        state = self.load()
        if state.run_id != expected_run_id:
            raise StateError("run ID does not match persisted state")
        graph = graph_for(state.strategy, state.complexity)
        if state.current_phase not in graph and state.current_phase not in {"FAILED", "IMPOSSIBLE"}:
            raise StateError("current phase is not valid for the strategy")
        expected_prefix = list(graph[:len(state.completed_phases)])
        if state.completed_phases != expected_prefix:
            raise StateError("completed phases are not a valid graph prefix")
        for name, metadata in state.artifacts.items():
            if metadata.get("path") != name or not self.artifacts.exists(name):
                raise StateError(f"recorded artifact is missing: {name}")
            if self.artifacts.checksum(name) != metadata.get("checksum"):
                raise StateError(f"artifact checksum mismatch: {name}")
        pending = state.pending_decision
        if state.status is RunStatus.WAITING_FOR_USER:
            if pending is None:
                raise StateError("waiting state is missing a pending decision")
            if pending.target_phase not in graph:
                raise StateError("pending decision target phase is invalid")
            if pending.request_artifact not in state.artifacts:
                raise StateError("pending decision request is not recorded")
            if self.artifacts.exists(f"decisions/{pending.id}/answer.json"):
                raise StateError("waiting decision already has an answer")
        elif pending is not None:
            raise StateError("non-waiting state has a pending decision")
        in_progress = [task for task in state.tasks if task.status is TaskStatus.IN_PROGRESS]
        if len(in_progress) > 1 or (state.current_phase != "TDD_BUNDLE" and in_progress):
            raise StateError("task status is inconsistent with the current phase")
        return state
