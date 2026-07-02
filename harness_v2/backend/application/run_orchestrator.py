"""Single run orchestrator for v2 commands and queries."""

from __future__ import annotations

import json

from harness_v2.backend.application.artifact_invalidation import ArtifactInvalidationRule, invalidate_phase_artifacts, restore_invalidated_artifacts
from harness_v2.backend.application.contracts import (
    BundleCompleted,
    BundleFailed,
    BundleRetryStarted,
    BundleStarted,
    CancelRun,
    CiTemplatesInstalled,
    Command,
    CommandExecutionResult,
    CommandResult,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetKnowledgePatch,
    GetKnowledgePatchResult,
    GetRun,
    GetRunResult,
    GetRunState,
    GetRunStateResult,
    InstallCiTemplates,
    InstallCiTemplatesResult,
    InvalidRunStateError,
    KnowledgePatchRejected,
    KnowledgePatchView,
    ListKnowledgePatches,
    ListKnowledgePatchesResult,
    ListRuns,
    ListRunsResult,
    PhaseCompleted,
    PhaseFailed,
    PhaseStarted,
    Query,
    QueryResult,
    RejectKnowledgePatch,
    RejectKnowledgePatchResult,
    ResumeRun,
    RetryBundle,
    RetryPhase,
    RunCancelled,
    RunCompleted,
    RunNotFoundError,
    RunResumed,
    RunStarted,
    RunSummaryView,
    StartRun,
    SubmitUserDecision,
    UserDecisionReceived,
)
from harness_v2.backend.application.decision_service import DecisionRequest, RequestUserDecisionService, pending_decision_view, run_to_view
from harness_v2.backend.application.escalation_service import EscalationPolicyService
from harness_v2.backend.application.phase_executor import PhaseExecutor
from harness_v2.backend.application.release_context import ReleaseContextService
from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.decisions import DecisionAction, DecisionRecord
from harness_v2.backend.domain.errors import DomainValidationError, ErrorRecord
from harness_v2.backend.domain.escalation import EscalationIssue
from harness_v2.backend.domain.knowledge import KnowledgePatchRecord, KnowledgePatchStatus
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus, TerminalState
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactStorePort
from harness_v2.backend.ports.clock import ClockPort
from harness_v2.backend.ports.event_sink import EventSinkPort
from harness_v2.backend.ports.id_generator import IdGeneratorPort
from harness_v2.backend.ports.knowledge_patch_store import KnowledgePatchNotFoundError, KnowledgePatchStorePort
from harness_v2.backend.ports.state_store import StateNotFoundError, StateStorePort


class _UnknownClock:
    def now_iso(self) -> str:
        return "unknown"


def run_to_summary(run: RunRecord) -> RunSummaryView:
    current_bundle = run.current_bundle
    return RunSummaryView(
        run_id=run.run_id,
        request=run.request,
        status=run.status.value,
        current_bundle=current_bundle.value if current_bundle else None,
        current_phase=run.current_phase.value if run.current_phase else None,
    )


def knowledge_patch_to_view(record: KnowledgePatchRecord) -> KnowledgePatchView:
    return KnowledgePatchView(
        patch_id=record.patch_id,
        run_id=record.run_id,
        origin_bundle=record.origin_bundle.value,
        version=record.version,
        status=record.status.value,
        path=record.path,
        proposal_id=record.proposal_id,
        summary=record.summary,
        created_at=record.created_at,
        rejected_at=record.rejected_at,
        rejection_reason=record.rejection_reason,
    )


def available_actions(run: RunRecord) -> tuple[str, ...]:
    if run.status in {RunStatus.PENDING, RunStatus.RUNNING}:
        return ("resume", "cancel")
    if run.status == RunStatus.WAITING_FOR_USER:
        return ("submit-user-decision", "cancel")
    if run.status == RunStatus.FAILED and run.errors and run.errors[-1].phase is not None:
        return ("retry-phase", "retry-bundle")
    return ()


class RunOrchestrator:
    def __init__(
        self,
        state_store: StateStorePort,
        id_generator: IdGeneratorPort,
        phase_executor: PhaseExecutor | None = None,
        clock: ClockPort | None = None,
        artifact_store: ArtifactStorePort | None = None,
        invalidation_rules: dict[PhaseName, ArtifactInvalidationRule] | None = None,
        event_sink: EventSinkPort | None = None,
        release_context: ReleaseContextService | None = None,
        knowledge_patches: KnowledgePatchStorePort | None = None,
    ) -> None:
        self._state_store = state_store
        self._id_generator = id_generator
        self._phase_executor = phase_executor
        self._clock = clock or _UnknownClock()
        self._artifact_store = artifact_store
        self._invalidation_rules = invalidation_rules or {}
        self._event_sink = event_sink
        self._release_context = release_context
        self._knowledge_patches = knowledge_patches
        self._decision_service = RequestUserDecisionService(state_store, self._clock)
        self._escalation_policy = (
            EscalationPolicyService(state_store, artifact_store, self._clock, self._invalidation_rules)
            if artifact_store is not None
            else None
        )

    def execute(self, command: Command) -> CommandExecutionResult:
        if isinstance(command, InstallCiTemplates):
            result = self._install_ci(command)
        elif isinstance(command, StartRun):
            result = self._start(command)
        elif isinstance(command, ResumeRun):
            result = self._resume(command)
        elif isinstance(command, RetryPhase):
            result = self._retry_phase(command)
        elif isinstance(command, RetryBundle):
            result = self._retry_bundle(command)
        elif isinstance(command, CancelRun):
            result = self._cancel(command)
        elif isinstance(command, SubmitUserDecision):
            result = self._submit_decision(command)
        elif isinstance(command, RejectKnowledgePatch):
            result = self._reject_knowledge_patch(command)
        else:
            raise TypeError(f"unsupported command: {type(command).__name__}")
        return self._publish(result)

    def query(self, query: Query) -> QueryResult:
        if isinstance(query, GetRun):
            return GetRunResult(run=run_to_view(self._get(query.run_id)))
        if isinstance(query, ListRuns):
            return ListRunsResult(runs=tuple(run_to_summary(run) for run in self._state_store.list_all()))
        if isinstance(query, GetRunState):
            run = self._get(query.run_id)
            current_bundle = run.current_bundle
            return GetRunStateResult(
                run_id=run.run_id,
                status=run.status.value,
                current_bundle=current_bundle.value if current_bundle else None,
                current_phase=run.current_phase.value if run.current_phase else None,
                pending_decision=pending_decision_view(run),
            )
        if isinstance(query, GetAvailableActions):
            run = self._get(query.run_id)
            return GetAvailableActionsResult(run_id=run.run_id, actions=available_actions(run))
        if isinstance(query, GetKnowledgePatch):
            return GetKnowledgePatchResult(knowledge_patch_to_view(self._get_patch(query.patch_id)))
        if isinstance(query, ListKnowledgePatches):
            store = self._knowledge_store()
            status = None if query.status is None else KnowledgePatchStatus(query.status)
            return ListKnowledgePatchesResult(tuple(knowledge_patch_to_view(patch) for patch in store.list_patches(run_id=query.run_id, status=status)))
        raise TypeError(f"unsupported query: {type(query).__name__}")

    def _start(self, command: StartRun) -> CommandResult:
        run_id = self._id_generator.new_id()
        root_bundle = BundleName(command.root_bundle)
        run = RunRecord(run_id=run_id, request=command.request, status=RunStatus.PENDING, root_bundle=root_bundle)
        self._state_store.save(run)
        return CommandResult(run=run_to_view(run), events=(RunStarted(run_id, command.request, root_bundle.value),))

    def _resume(self, command: ResumeRun) -> CommandResult:
        run = self._get(command.run_id)
        if run.status == RunStatus.PENDING:
            first = bundle_catalog.start_step(run.root_bundle)
            updated = run.replace(status=RunStatus.RUNNING, current_step_id=first.step_id)
            self._state_store.save(updated)
            start_events = (RunResumed(run.run_id), *(BundleStarted(run.run_id, bundle.value) for bundle in dict.fromkeys(first.bundle_path)), PhaseStarted(run.run_id, first.bundle_name.value, first.phase_name.value))
            phase_result = self._execute_current_phase(updated)
            if phase_result is None:
                return CommandResult(run=run_to_view(updated), events=start_events)
            return CommandResult(run=phase_result.run, events=(*start_events, *phase_result.events))
        if run.status == RunStatus.RUNNING:
            resumed = CommandResult(run=run_to_view(run), events=(RunResumed(run.run_id),))
            phase_result = self._execute_current_phase(run)
            if phase_result is None:
                return resumed
            return CommandResult(run=phase_result.run, events=(*resumed.events, *phase_result.events))
        if run.status == RunStatus.WAITING_FOR_USER:
            raise InvalidRunStateError(f"run {run.run_id} requires a user decision before it can resume")
        raise InvalidRunStateError(f"run {run.run_id} cannot be resumed from {run.status.value}")

    def _execute_current_phase(self, run: RunRecord) -> CommandResult | None:
        if self._phase_executor is None or run.status is not RunStatus.RUNNING or run.current_step_id is None:
            return None
        bundle = run.current_bundle
        if bundle is None:
            return None
        try:
            result = self._phase_executor.execute(run, bundle, run.current_phase)
            if result.tasks is not None:
                run = self._get(run.run_id).replace(tasks=result.tasks)
                self._state_store.save(run)
            if result.decision_request is not None:
                return self._decision_service.execute(result.decision_request)
            if result.escalation_issue is not None:
                if self._escalation_policy is None:
                    raise InvalidRunStateError("escalation requires an artifact store")
                return self._escalation_policy.execute(run.run_id, result.escalation_issue)
            return self._complete_phase(run.run_id, bundle, run.current_step_id, extra_events=result.events)
        except Exception as exc:
            return self._fail_phase(run.run_id, bundle, run.current_step_id, exc)

    def _complete_phase(self, run_id: str, bundle: BundleName, step_id: str, *, extra_events: tuple[object, ...] = ()) -> CommandResult:
        run = self._get(run_id)
        current_step = bundle_catalog.step_for_step_id(run.root_bundle, step_id)
        if run.status is not RunStatus.RUNNING or run.current_step_id != step_id:
            raise InvalidRunStateError(f"run {run.run_id} is not running {bundle.value}/{current_step.phase_name.value}")
        next_step = bundle_catalog.next_after(run.root_bundle, step_id)
        completed = (*run.completed_step_ids, step_id)
        events: list[object] = [*extra_events, PhaseCompleted(run.run_id, bundle.value, current_step.phase_name.value)]
        before = bundle_catalog.completed_bundles(run.root_bundle, run.completed_step_ids)
        after = bundle_catalog.completed_bundles(run.root_bundle, completed)
        for completed_bundle in after:
            if completed_bundle not in before:
                events.append(BundleCompleted(run.run_id, completed_bundle.value))
        if next_step is TerminalState.COMPLETED:
            updated = run.replace(status=RunStatus.COMPLETED, current_step_id=None, completed_step_ids=completed)
            events.append(RunCompleted(run.run_id))
        else:
            updated = run.replace(current_step_id=next_step.step_id, completed_step_ids=completed)
            if next_step.bundle_name not in after and next_step.bundle_name != bundle:
                events.append(BundleStarted(run.run_id, next_step.bundle_name.value))
            events.append(PhaseStarted(run.run_id, next_step.bundle_name.value, next_step.phase_name.value))
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=tuple(events))

    def _fail_phase(self, run_id: str, bundle: BundleName, step_id: str, exc: Exception) -> CommandResult:
        run = self._get(run_id)
        message = str(exc) or type(exc).__name__
        current_step = bundle_catalog.step_for_step_id(run.root_bundle, step_id)
        if self._artifact_store is not None:
            payload = {"schema_version": 1, "bundle": bundle.value, "phase": current_step.phase_name.value, "error": message, "error_type": type(exc).__name__}
            self._artifact_store.write(run_id, f"validation/{bundle.value}-{current_step.phase_name.value}-failure.json", (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        error = ErrorRecord(f"{current_step.phase_name.value}_FAILED", message, bundle=bundle.value, phase=current_step.phase_name.value, timestamp=self._clock.now_iso())
        updated = run.replace(status=RunStatus.FAILED, pending_decision=None, errors=(*run.errors, error))
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=(PhaseFailed(run_id, bundle.value, current_step.phase_name.value, message), BundleFailed(run_id, bundle.value, message)))

    def _retry_phase(self, command: RetryPhase) -> CommandResult:
        run = self._get(command.run_id)
        target_bundle = BundleName(command.bundle)
        target_phase = PhaseName(command.phase)
        if run.status is not RunStatus.FAILED:
            raise InvalidRunStateError(f"run {run.run_id} cannot retry from {run.status.value}")
        if run.current_step_id is None:
            raise InvalidRunStateError(f"run {run.run_id} has no failed step to retry")
        current_step = bundle_catalog.step_for_step_id(run.root_bundle, run.current_step_id)
        if current_step.bundle_name is not target_bundle or current_step.phase_name is not target_phase:
            raise InvalidRunStateError(f"run {run.run_id} last failed step is {current_step.bundle_name.value}/{current_step.phase_name.value}")
        return self._retry_at_step(run, current_step, retry_bundle=None)

    def _retry_bundle(self, command: RetryBundle) -> CommandResult:
        run = self._get(command.run_id)
        if run.status is not RunStatus.FAILED:
            raise InvalidRunStateError(f"run {run.run_id} cannot retry from {run.status.value}")
        target_bundle = BundleName(command.bundle)
        candidates = [step for step in bundle_catalog.linearize_bundle(run.root_bundle) if step.bundle_name is target_bundle]
        if not candidates:
            raise InvalidRunStateError(f"bundle {target_bundle.value} is not in {run.root_bundle.value}")
        return self._retry_at_step(run, candidates[0], retry_bundle=target_bundle)

    def _retry_at_step(self, run: RunRecord, target_step, retry_bundle: BundleName | None) -> CommandResult:
        if self._artifact_store is None:
            raise InvalidRunStateError("retry requires an artifact store")
        target_bundle = retry_bundle or target_step.bundle_name
        if bundle_catalog.parent_bundle(run.root_bundle, target_step.step_id) is not target_bundle:
            raise InvalidRunStateError(f"{target_step.phase_name.value} does not belong to {target_bundle.value}")
        try:
            expected_completed = bundle_catalog.completed_prefix_before(run.root_bundle, target_step.step_id)
            invalidated_step_ids = bundle_catalog.step_ids_from(run.root_bundle, target_step.step_id)
        except DomainValidationError as exc:
            raise InvalidRunStateError(str(exc)) from exc
        invalidated_phases = tuple(bundle_catalog.step_for_step_id(run.root_bundle, step_id).phase_name for step_id in invalidated_step_ids)
        invalidated = invalidate_phase_artifacts(self._artifact_store, run.run_id, invalidated_phases, self._invalidation_rules)
        invalidated_bundles = set(bundle_catalog.parent_bundle(run.root_bundle, step_id) for step_id in invalidated_step_ids)
        tasks = () if BundleName.TASKS_BUNDLE in invalidated_bundles else run.tasks
        updated = run.replace(status=RunStatus.RUNNING, current_step_id=target_step.step_id, completed_step_ids=expected_completed, pending_decision=None, tasks=tasks)
        try:
            self._state_store.save(updated)
        except Exception:
            restore_invalidated_artifacts(self._artifact_store, run.run_id, invalidated)
            raise
        events: tuple[object, ...]
        if retry_bundle is None:
            events = (PhaseStarted(run.run_id, target_bundle.value, target_step.phase_name.value),)
        else:
            events = (BundleRetryStarted(run.run_id, retry_bundle.value), PhaseStarted(run.run_id, target_bundle.value, target_step.phase_name.value))
        return CommandResult(run=run_to_view(updated), events=events)

    def _cancel(self, command: CancelRun) -> CommandResult:
        run = self._get(command.run_id)
        if run.status not in {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_FOR_USER}:
            raise InvalidRunStateError(f"run {run.run_id} cannot be cancelled from {run.status.value}")
        updated = run.replace(status=RunStatus.CANCELLED, current_step_id=None, pending_decision=None)
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=(RunCancelled(command.run_id),))

    def _submit_decision(self, command: SubmitUserDecision) -> CommandResult:
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
        received = UserDecisionReceived(command.run_id, command.decision_id, command.response)
        history = DecisionRecord(
            decision_id=decision.decision_id,
            origin_bundle=decision.origin_bundle,
            prompt=decision.prompt,
            response=command.response,
            created_at=decision.created_at,
            answered_at=self._clock.now_iso(),
            options=decision.options,
            effects=decision.effects,
            default_action=decision.default_action,
            default_category=decision.default_category,
        )
        updated = run.replace(status=RunStatus.RUNNING, pending_decision=None, decision_history=(*run.decision_history, history))
        if effect.action is DecisionAction.ESCALATE:
            if self._escalation_policy is None:
                raise InvalidRunStateError("escalation requires an artifact store")
            issue = EscalationIssue(
                f"decision-{decision.decision_id}",
                decision.origin_bundle,
                effect.category,
                f"user decision {decision.decision_id} escalated: {command.response}",
                decision_id=decision.decision_id,
                response=command.response,
            )
            result = self._escalation_policy.execute(run.run_id, issue, base_run=updated)
            return CommandResult(run=result.run, events=(received, *result.events))
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=(received,))

    def _install_ci(self, command: InstallCiTemplates) -> InstallCiTemplatesResult:
        if self._release_context is None:
            raise InvalidRunStateError("install-ci requires a release context service")
        result = self._release_context.install_ci_templates(command.target, force=command.force)
        event = CiTemplatesInstalled(command.target, result.installed, result.skipped, result.warnings)
        return InstallCiTemplatesResult(command.target, result.installed, result.skipped, result.warnings, (event,))

    def _reject_knowledge_patch(self, command: RejectKnowledgePatch) -> RejectKnowledgePatchResult:
        try:
            patch = self._knowledge_store().reject_patch(command.patch_id, command.reason, self._clock.now_iso())
        except KnowledgePatchNotFoundError as exc:
            raise RunNotFoundError(command.patch_id) from exc
        event = KnowledgePatchRejected(patch.patch_id, command.reason)
        return RejectKnowledgePatchResult(knowledge_patch_to_view(patch), (event,))

    def _knowledge_store(self) -> KnowledgePatchStorePort:
        if self._knowledge_patches is None:
            raise InvalidRunStateError("knowledge patch store is not configured")
        return self._knowledge_patches

    def _get_patch(self, patch_id: str) -> KnowledgePatchRecord:
        try:
            return self._knowledge_store().get_patch(patch_id)
        except KnowledgePatchNotFoundError as exc:
            raise RunNotFoundError(patch_id) from exc

    def _get(self, run_id: str) -> RunRecord:
        try:
            return self._state_store.get(run_id)
        except StateNotFoundError as exc:
            raise RunNotFoundError(run_id) from exc

    def _publish(self, result: CommandExecutionResult) -> CommandExecutionResult:
        if self._event_sink is not None:
            for event in result.events:
                self._event_sink.emit(event)
        return result
