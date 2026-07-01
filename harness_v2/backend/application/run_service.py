"""Application services for v2 run commands and queries."""

from __future__ import annotations

from typing import Protocol

from harness_v2.backend.application.contracts import (
    CancelRun,
    Command,
    CommandResult,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetRun,
    InvalidRunStateError,
    GetRunResult,
    GetRunState,
    GetRunStateResult,
    ListRuns,
    ListRunsResult,
    PhaseEscalated,
    PhaseRetryStarted,
    PhaseStarted,
    Query,
    QueryResult,
    ResumeRun,
    RetryPhase,
    RunCancelled,
    RunNotFoundError,
    RunResumed,
    RunStarted,
    RunSummaryView,
    StartRun,
    SubmitUserDecision,
    UserDecisionReceived,
)
from harness_v2.backend.application.artifact_invalidation import ArtifactInvalidationRule, InvalidatedArtifact, invalidate_phase_artifacts, restore_invalidated_artifacts
from harness_v2.backend.application.decision_service import pending_decision_view, run_to_view
from harness_v2.backend.domain.decisions import DecisionAction, DecisionRecord
from harness_v2.backend.domain.errors import DomainValidationError
from harness_v2.backend.domain.lifecycle import LifecycleGraph, PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactStorePort
from harness_v2.backend.ports.clock import ClockPort
from harness_v2.backend.ports.event_sink import EventSinkPort
from harness_v2.backend.ports.id_generator import IdGeneratorPort
from harness_v2.backend.ports.state_store import StateNotFoundError, StateStorePort

INITIAL_PHASE = PhaseName.EXPLORE_BUNDLE


class PhaseOrchestrator(Protocol):
    def execute_current_phase(self, run_id: str) -> CommandResult | None: ...


class _UnknownClock:
    def now_iso(self) -> str:
        return "unknown"


def run_to_summary(run: RunRecord) -> RunSummaryView:
    return RunSummaryView(
        run_id=run.run_id,
        request=run.request,
        status=run.status.value,
        current_phase=run.current_phase.value if run.current_phase else None,
    )


def available_actions(run: RunRecord) -> tuple[str, ...]:
    if run.status in {RunStatus.PENDING, RunStatus.RUNNING}:
        return ("resume", "cancel")
    if run.status == RunStatus.WAITING_FOR_USER:
        return ("submit-user-decision", "cancel")
    if run.status == RunStatus.FAILED and run.errors and run.errors[-1].phase is not None:
        return ("retry-phase",)
    return ()


class _RunStateAccess:
    def __init__(self, state_store: StateStorePort) -> None:
        self._state_store = state_store

    def _get(self, run_id: str) -> RunRecord:
        try:
            return self._state_store.get(run_id)
        except StateNotFoundError as exc:
            raise RunNotFoundError(run_id) from exc


class StartRunService(_RunStateAccess):
    def __init__(self, state_store: StateStorePort, id_generator: IdGeneratorPort) -> None:
        super().__init__(state_store)
        self._id_generator = id_generator

    def execute(self, command: StartRun) -> CommandResult:
        run_id = self._id_generator.new_id()
        events = (RunStarted(run_id=run_id, request=command.request),)
        run = RunRecord(
            run_id=run_id,
            request=command.request,
            status=RunStatus.PENDING,
            strategy=RunStrategy(command.strategy),
        )
        self._state_store.save(run)
        return CommandResult(run=run_to_view(run), events=events)


class ResumeRunService(_RunStateAccess):
    def execute(self, command: ResumeRun) -> CommandResult:
        run = self._get(command.run_id)
        if run.status == RunStatus.PENDING:
            start_phase = LifecycleGraph.for_strategy(run.strategy).start_phase
            resumed = RunResumed(run_id=run.run_id)
            started = PhaseStarted(run_id=run.run_id, phase=start_phase.value)
            updated = run.replace(
                status=RunStatus.RUNNING,
                current_phase=start_phase,
            )
            self._state_store.save(updated)
            return CommandResult(run=run_to_view(updated), events=(resumed, started))
        if run.status == RunStatus.RUNNING:
            event = RunResumed(run_id=run.run_id)
            return CommandResult(run=run_to_view(run), events=(event,))
        if run.status == RunStatus.WAITING_FOR_USER:
            raise InvalidRunStateError(f"run {run.run_id} requires a user decision before it can resume")
        raise InvalidRunStateError(f"run {run.run_id} cannot be resumed from {run.status.value}")


class RetryPhaseService(_RunStateAccess):
    def __init__(
        self,
        state_store: StateStorePort,
        artifact_store: ArtifactStorePort | None = None,
        invalidation_rules: dict[PhaseName, ArtifactInvalidationRule] | None = None,
    ) -> None:
        super().__init__(state_store)
        self._artifact_store = artifact_store
        self._invalidation_rules = invalidation_rules or {}

    def execute(self, command: RetryPhase) -> CommandResult:
        run = self._get(command.run_id)
        if run.status is not RunStatus.FAILED:
            raise InvalidRunStateError(f"run {run.run_id} cannot retry from {run.status.value}")
        if not run.errors or run.errors[-1].phase is None:
            raise InvalidRunStateError(f"run {run.run_id} has no failed phase to retry")
        target = PhaseName(command.phase)
        failed_phase = PhaseName(run.errors[-1].phase)
        if target is not failed_phase:
            raise InvalidRunStateError(f"run {run.run_id} last failed phase is {failed_phase.value}")
        graph = LifecycleGraph.for_strategy(run.strategy)
        try:
            expected_completed = graph.completed_prefix_before(target)
        except DomainValidationError as exc:
            raise InvalidRunStateError(str(exc)) from exc
        if run.completed_phases != expected_completed:
            raise InvalidRunStateError(f"run {run.run_id} completed phases do not match retry target {target.value}")
        if self._artifact_store is None:
            raise InvalidRunStateError("retry requires an artifact store")
        invalidated = invalidate_phase_artifacts(self._artifact_store, run.run_id, graph.phases_from(target), self._invalidation_rules)
        updated = run.replace(status=RunStatus.RUNNING, current_phase=target, pending_decision=None)
        try:
            self._state_store.save(updated)
        except Exception:
            restore_invalidated_artifacts(self._artifact_store, run.run_id, invalidated)
            raise
        return CommandResult(run=run_to_view(updated), events=(PhaseRetryStarted(run.run_id, target.value), PhaseStarted(run.run_id, target.value)))


class CancelRunService(_RunStateAccess):
    def execute(self, command: CancelRun) -> CommandResult:
        run = self._get(command.run_id)
        if run.status not in {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_FOR_USER}:
            raise InvalidRunStateError(f"run {run.run_id} cannot be cancelled from {run.status.value}")
        event = RunCancelled(run_id=command.run_id)
        updated = run.replace(
            status=RunStatus.CANCELLED,
            current_phase=None,
            pending_decision=None,
        )
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=(event,))


class SubmitUserDecisionService(_RunStateAccess):
    def __init__(
        self,
        state_store: StateStorePort,
        clock: ClockPort | None = None,
        artifact_store: ArtifactStorePort | None = None,
        invalidation_rules: dict[PhaseName, ArtifactInvalidationRule] | None = None,
    ) -> None:
        super().__init__(state_store)
        self._clock = clock or _UnknownClock()
        self._artifact_store = artifact_store
        self._invalidation_rules = invalidation_rules or {}

    def execute(self, command: SubmitUserDecision) -> CommandResult:
        run = self._get(command.run_id)
        if run.status != RunStatus.WAITING_FOR_USER or run.pending_decision is None:
            raise InvalidRunStateError(f"run {run.run_id} has no pending decision")
        decision = run.pending_decision
        if command.decision_id != decision.decision_id:
            raise InvalidRunStateError(f"run {run.run_id} is waiting for decision {decision.decision_id}")
        if decision.options and command.response not in decision.options:
            allowed = ", ".join(decision.options)
            raise InvalidRunStateError(f"decision response must be one of: {allowed}")

        effect = decision.effect_for(command.response)
        graph = LifecycleGraph.for_strategy(run.strategy)
        if effect.action is DecisionAction.ESCALATE:
            if effect.target_phase is None:
                raise InvalidRunStateError("escalation decision effect requires a target phase")
            try:
                graph.validate_rewind_target(run.current_phase, effect.target_phase)
            except DomainValidationError as exc:
                raise InvalidRunStateError(str(exc)) from exc

        received = UserDecisionReceived(
            run_id=command.run_id,
            decision_id=command.decision_id,
            response=command.response,
        )
        history = DecisionRecord(
            decision_id=decision.decision_id,
            origin_phase=decision.origin_phase,
            prompt=decision.prompt,
            response=command.response,
            created_at=decision.created_at,
            answered_at=self._clock.now_iso(),
            options=decision.options,
            effects=decision.effects,
            default_action=decision.default_action,
            default_target_phase=decision.default_target_phase,
        )
        if effect.action is DecisionAction.ESCALATE:
            updated, escalated, invalidated = self._escalate(run, history, graph, effect.target_phase)
            try:
                self._state_store.save(updated)
            except Exception:
                restore_invalidated_artifacts(self._artifact_store, run.run_id, invalidated)
                raise
            return CommandResult(run=run_to_view(updated), events=(received, escalated, PhaseStarted(run.run_id, effect.target_phase.value)))

        updated = run.replace(
            status=RunStatus.RUNNING,
            pending_decision=None,
            decision_history=(*run.decision_history, history),
        )
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=(received,))

    def _escalate(
        self,
        run: RunRecord,
        history: DecisionRecord,
        graph: LifecycleGraph,
        target_phase: PhaseName,
    ) -> tuple[RunRecord, PhaseEscalated, tuple[InvalidatedArtifact, ...]]:
        if self._artifact_store is None:
            raise InvalidRunStateError("escalation requires an artifact store")
        invalidated_phases = graph.phases_from(target_phase)
        invalidated = invalidate_phase_artifacts(self._artifact_store, run.run_id, invalidated_phases, self._invalidation_rules)
        tasks = () if PhaseName.TASKS_BUNDLE in invalidated_phases else run.tasks
        updated = run.replace(
            status=RunStatus.RUNNING,
            current_phase=target_phase,
            completed_phases=graph.completed_prefix_before(target_phase),
            pending_decision=None,
            decision_history=(*run.decision_history, history),
            tasks=tasks,
        )
        event = PhaseEscalated(
            run_id=run.run_id,
            from_phase=run.current_phase.value,
            target_phase=target_phase.value,
            decision_id=history.decision_id,
        )
        return updated, event, invalidated


class GetRunService(_RunStateAccess):
    def query(self, query: GetRun) -> GetRunResult:
        return GetRunResult(run=run_to_view(self._get(query.run_id)))


class ListRunsService(_RunStateAccess):
    def query(self, query: ListRuns) -> ListRunsResult:
        return ListRunsResult(runs=tuple(run_to_summary(run) for run in self._state_store.list_all()))


class GetRunStateService(_RunStateAccess):
    def query(self, query: GetRunState) -> GetRunStateResult:
        run = self._get(query.run_id)
        return GetRunStateResult(
            run_id=run.run_id,
            status=run.status.value,
            current_phase=run.current_phase.value if run.current_phase else None,
            pending_decision=pending_decision_view(run),
        )


class GetAvailableActionsService(_RunStateAccess):
    def query(self, query: GetAvailableActions) -> GetAvailableActionsResult:
        run = self._get(query.run_id)
        return GetAvailableActionsResult(run_id=run.run_id, actions=available_actions(run))


class RunService:
    """Facade over explicit application services with persistence behind ports."""

    def __init__(
        self,
        state_store: StateStorePort,
        id_generator: IdGeneratorPort,
        orchestrator: PhaseOrchestrator | None = None,
        clock: ClockPort | None = None,
        artifact_store: ArtifactStorePort | None = None,
        invalidation_rules: dict[PhaseName, ArtifactInvalidationRule] | None = None,
        event_sink: EventSinkPort | None = None,
    ) -> None:
        if invalidation_rules is None and artifact_store is not None:
            from harness_v2.backend.application.bundle_registry import default_bundle_registry

            invalidation_rules = default_bundle_registry().invalidation_rules()
        self._state_store = state_store
        self._orchestrator = orchestrator
        self._event_sink = event_sink
        self._start = StartRunService(state_store, id_generator=id_generator)
        self._resume = ResumeRunService(state_store)
        self._retry = RetryPhaseService(state_store, artifact_store=artifact_store, invalidation_rules=invalidation_rules)
        self._cancel = CancelRunService(state_store)
        self._submit_decision = SubmitUserDecisionService(
            state_store,
            clock=clock,
            artifact_store=artifact_store,
            invalidation_rules=invalidation_rules,
        )
        self._get = GetRunService(state_store)
        self._list = ListRunsService(state_store)
        self._get_state = GetRunStateService(state_store)
        self._get_actions = GetAvailableActionsService(state_store)

    def execute(self, command: Command) -> CommandResult:
        if isinstance(command, StartRun):
            return self._publish(self._start.execute(command))
        if isinstance(command, ResumeRun):
            resumed = self._resume.execute(command)
            if self._orchestrator is None:
                return self._publish(resumed)
            phase_result = self._orchestrator.execute_current_phase(command.run_id)
            if phase_result is None:
                return self._publish(resumed)
            return self._publish(CommandResult(run=phase_result.run, events=(*resumed.events, *phase_result.events)))
        if isinstance(command, RetryPhase):
            return self._publish(self._retry.execute(command))
        if isinstance(command, CancelRun):
            return self._publish(self._cancel.execute(command))
        if isinstance(command, SubmitUserDecision):
            return self._publish(self._submit_decision.execute(command))
        raise TypeError(f"unsupported command: {type(command).__name__}")

    def _publish(self, result: CommandResult) -> CommandResult:
        if self._event_sink is not None:
            for event in result.events:
                self._event_sink.emit(event)
        return result

    def query(self, query: Query) -> QueryResult:
        if isinstance(query, GetRun):
            return self._get.query(query)
        if isinstance(query, ListRuns):
            return self._list.query(query)
        if isinstance(query, GetRunState):
            return self._get_state.query(query)
        if isinstance(query, GetAvailableActions):
            return self._get_actions.query(query)
        raise TypeError(f"unsupported query: {type(query).__name__}")
