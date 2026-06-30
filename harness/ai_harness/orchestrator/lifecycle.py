"""Shared orchestration mixin support."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Sequence

from ..explorer_gate import ExplorerGateDecision
from ..canonical import CanonicalDocs
from ..config import HarnessConfig
from ..errors import ValidationError
from ..models import KnowledgeEntry, RunState
from ..output import RunResult
from ..providers.base import Provider
from ..router import RouteDecision
from ..stores.artifact import ArtifactStore
from ..stores.knowledge import KnowledgeStore, SQLiteKnowledgeStore
from ..stores.runtime import RunLock
from ..stores.state import StateStore
from ..strategy import StrategyDecision
from .analysis_quality import AnalysisSupportService
from .ci_finalization import CiFinalization
from .context import RunContext
from .failure_recorder import FailureRecorder as _FailureRecorder
from .explorer_flow import ExplorerFlowService
from .learning_parser import parse_learning_sections as _parse_learning_sections
from .phase_execution import PhaseExecution, PhaseExecutionCallbacks
from .result_publication import ResultPublication as _ResultPublication
from .resume_context_loader import ResumeContextLoader as _ResumeContextLoader
from .routing_coordinator import RoutingCoordinator as _RoutingCoordinator
from .run_initializer import RunInitializer as _RunInitializer
from .run_progression import RunProgression as _RunProgression
from .strategy_persister import StrategyPersister as _StrategyPersister
from .strategy_resolver import StrategyResolver as _StrategyResolver
from .worker_exchange import WorkerExchange
from .worker_gateway import WorkerGateway


class Orchestrator:
    """Own state and gates while workers only return candidate artifacts."""

    def __init__(self, target_repository: Path, config: HarnessConfig, provider: Provider | None,
                 *, artifacts: ArtifactStore | None = None, state_store: StateStore | None = None,
                 knowledge: KnowledgeStore | None = None, lock: RunLock | None = None,
                 progress: Callable[[str], None] | None = None) -> None:
        target = Path(target_repository).resolve()
        if not target.is_dir():
            raise ValidationError("target repository must be a directory")
        _artifacts = artifacts or ArtifactStore(target, create=False)
        self._ctx = RunContext(
            target=target,
            config=config,
            provider=provider,
            external_runtime=artifacts is not None or state_store is not None,
            artifacts=_artifacts,
            canonical=CanonicalDocs(target),
            state=state_store or StateStore(target, _artifacts),
            knowledge=knowledge or SQLiteKnowledgeStore(target / ".ai-harness" / "knowledge.db"),
            lock=lock or RunLock(target),
            progress=progress or (lambda _: None),
        )
        self._results = _ResultPublication(self._ctx)
        self._aqm = AnalysisSupportService(self._ctx, self._invoke_with_repair)
        self._wex = WorkerExchange(self._ctx, self._invoke_with_repair, self._aqm._explorer_scope)
        self._ifl = ExplorerFlowService(
            self._ctx,
            self._wex,
            self._aqm,
            self._invoke,
            self._invoke_with_repair,
        )
        self._ci_finalization = CiFinalization(
            self._ctx.target,
            self._ctx.config,
            self._ctx.artifacts,
            self._ctx.state,
            self._ctx.warnings,
            self._results,
        )
        self._source_run: str | None = None
        self._pex = PhaseExecution(self._ctx, PhaseExecutionCallbacks(
            load_knowledge=self._aqm._load_knowledge,
            persist_route=self._persist_route,
            persist_strategy=self._persist_strategy,
            explorer=self._ifl._explorer,
            explorer_intake=self._ifl._explorer_intake,
            explorer_discovery=self._ifl._explorer_discovery,
            explorer_decision=self._ifl._explorer_decision,
            explorer_artifact=self._ifl._explorer_artifact,
            explorer_review=self._ifl._explorer_review,
            finalize=self._ci_finalization.finalize,
            explorer_scope=self._aqm._explorer_scope,
            related_improvements=self._wex._related_improvements,
            repository_observations=self._wex._repository_observations,
            validate_full_sdd_task_coverage=self._aqm._validate_full_sdd_task_coverage,
            invoke=self._invoke,
            worker=self._wex._worker,
            full_sdd_inputs=self._wex._full_sdd_inputs,
            request_brief=self._wex._request_brief,
            referenced_markdown_documents=self._wex._referenced_markdown_documents,
            publish_learning_proposals=self._publish_learning_proposals,
            invoke_learning_with_repair=self._aqm._invoke_learning_with_repair,
            explorer_context_from_discovery=self._ifl._explorer_context_from_discovery,
            markdown_section=WorkerExchange._markdown_section,
            publish_explorer_bundle=self._ifl._publish_explorer_bundle,
            waiting_result=self._results.waiting,
            clip_text=self._aqm._clip_text,
        ))


    def _publish_learning_proposals(
        self,
        output: str,
        phase: str,
        *,
        synthesis_inputs: object,
    ) -> str:
        return self._ifl._make_learning_service().publish_learning_proposals(
            output, phase, synthesis_inputs=synthesis_inputs
        )

    def _explorer_gate_decision_request(self, gate: object) -> object:
        return self._aqm._make_routing_gate().decision_request(gate)

    def _explorer_gate_answer_choice(self) -> object:
        return self._aqm._make_routing_gate().answer_choice()

    @classmethod
    def parse_learning_sections(cls, candidate: str, *, validate: bool = True) -> dict[str, str | tuple[str, ...]]:
        return _parse_learning_sections(candidate, validate=validate)

    def _invoke(
        self,
        name: str,
        inputs: Mapping[str, object],
        *,
        repair: Mapping[str, object] | None = None,
        parse_control: bool = True,
    ) -> str:
        return WorkerGateway(
            self.provider,
            self.target,
            self.state,
            self.artifacts,
            self.progress,
        ).invoke(name, inputs, repair=repair, parse_control=parse_control)

    def _phase(self, phase: str) -> None:
        return self._pex._phase(phase)

    def _invoke_with_repair(self, name: str, inputs: Mapping[str, object], *, parse_control: bool = True) -> str:
        return self._pex._invoke_with_repair(name, inputs, parse_control=parse_control)

    def _handle_control_output(self, output: object, *, target_phase: str) -> RunResult | None:
        return self._pex._handle_control_output(output, target_phase=target_phase)

    def _worker(self, name: str, inputs: Mapping[str, object]) -> str:
        return self._wex._worker(name, inputs)

    def _inputs(self, *names: str) -> dict[str, object]:
        return self._wex._inputs(*names)

    def _full_sdd_inputs(self, *names: str) -> dict[str, object]:
        return self._wex._full_sdd_inputs(*names)

    @staticmethod
    def _markdown_section(candidate: str, section: str) -> str:
        return WorkerExchange._markdown_section(candidate, section)

    def _explorer_artifact_path(self, candidate: str) -> str:
        return self._wex._explorer_artifact_path(candidate)

    def _related_improvements(self) -> list[dict[str, str | int]]:
        return self._wex._related_improvements()

    def _repository_observations(
        self,
        related_improvements: Sequence[Mapping[str, object]],
        intake: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        return self._wex._repository_observations(related_improvements, intake)

    def _referenced_markdown_documents(self, request: str) -> dict[str, str]:
        return self._wex._referenced_markdown_documents(request)

    def _request_brief(self) -> str:
        return self._wex._request_brief()

    # ------------------------------------------------------------------
    # Property delegation — all mixin code references self.<name> which
    # transparently reads/writes self._ctx.<name>.  Properties are the
    # seam that will let collaborators accept a RunContext by constructor
    # once the mixin inheritance is dissolved in Step 5.
    # ------------------------------------------------------------------

    @property
    def target(self) -> Path:
        return self._ctx.target

    @property
    def config(self) -> HarnessConfig:
        return self._ctx.config

    @property
    def provider(self) -> Provider | None:
        return self._ctx.provider

    @property
    def canonical(self) -> CanonicalDocs:
        return self._ctx.canonical

    @canonical.setter
    def canonical(self, value: CanonicalDocs) -> None:
        self._ctx.canonical = value

    @property
    def knowledge(self) -> KnowledgeStore:
        return self._ctx.knowledge

    @property
    def lock(self) -> RunLock:
        return self._ctx.lock

    @property
    def progress(self) -> Callable[[str], None]:
        return self._ctx.progress

    @property
    def _external_runtime(self) -> bool:
        return self._ctx.external_runtime

    @property
    def artifacts(self) -> ArtifactStore:
        return self._ctx.artifacts

    @artifacts.setter
    def artifacts(self, value: ArtifactStore) -> None:
        self._ctx.artifacts = value

    @property
    def state(self) -> StateStore:
        return self._ctx.state

    @state.setter
    def state(self, value: StateStore) -> None:
        self._ctx.state = value

    @property
    def route(self) -> RouteDecision | None:
        return self._ctx.route

    @route.setter
    def route(self, value: RouteDecision | None) -> None:
        self._ctx.route = value

    @property
    def strategy(self) -> StrategyDecision | None:
        return self._ctx.strategy

    @strategy.setter
    def strategy(self, value: StrategyDecision | None) -> None:
        self._ctx.strategy = value

    @property
    def explorer_gate(self) -> ExplorerGateDecision | None:
        return self._ctx.explorer_gate

    @explorer_gate.setter
    def explorer_gate(self, value: ExplorerGateDecision | None) -> None:
        self._ctx.explorer_gate = value

    @property
    def knowledge_context(self) -> list[KnowledgeEntry]:
        return self._ctx.knowledge_context

    @knowledge_context.setter
    def knowledge_context(self, value: list[KnowledgeEntry]) -> None:
        self._ctx.knowledge_context = value

    @property
    def repository_observations(self) -> list[dict[str, object]]:
        return self._ctx.repository_observations

    @repository_observations.setter
    def repository_observations(self, value: list[dict[str, object]]) -> None:
        self._ctx.repository_observations = value

    @property
    def _explorer_extraction_records(self) -> list[dict[str, object]]:
        return self._ctx.explorer_extraction_records

    @_explorer_extraction_records.setter
    def _explorer_extraction_records(self, value: list[dict[str, object]]) -> None:
        self._ctx.explorer_extraction_records = value

    @property
    def task_documents(self) -> dict[str, Mapping[str, object]]:
        return self._ctx.task_documents

    @task_documents.setter
    def task_documents(self, value: dict[str, Mapping[str, object]]) -> None:
        self._ctx.task_documents = value

    @property
    def _explorer_scope_cache(self) -> dict[str, object] | None:
        return self._ctx.explorer_scope_cache

    @_explorer_scope_cache.setter
    def _explorer_scope_cache(self, value: dict[str, object] | None) -> None:
        self._ctx.explorer_scope_cache = value

    @property
    def warnings(self) -> list[str]:
        return self._ctx.warnings

    @warnings.setter
    def warnings(self, value: list[str]) -> None:
        self._ctx.warnings = value

    def run(
        self,
        request: str,
        *,
        resume_run_id: str | None = None,
        decision_answer: str | None = None,
        route_decision: RouteDecision | None = None,
        strategy_decision: StrategyDecision | None = None,
        source_run: str | None = None,
    ) -> RunResult:
        if not resume_run_id and not request.strip():
            raise ValidationError("request must not be empty")
        with self.lock:
            self._source_run = source_run
            state = (
                self._resume(resume_run_id, decision_answer)
                if resume_run_id
                else self._initialize(request, route_decision=route_decision, strategy_decision=strategy_decision)
            )
            try:
                return self._execute(state)
            except Exception as exc:
                _FailureRecorder(self.state, self.artifacts).record(exc)
                raise

    def _make_run_initializer(self) -> _RunInitializer:
        return _RunInitializer(
            self.target, self.provider, self.config,
            external_runtime=self._external_runtime,
            artifacts=self.artifacts, state=self.state,
            resolve_fn=self._make_strategy_resolver().resolve,
            warnings=self.warnings,
            source_run=self._source_run,
        )

    def _initialize(
        self,
        request: str,
        *,
        route_decision: RouteDecision | None = None,
        strategy_decision: StrategyDecision | None = None,
    ) -> RunState:
        result = self._make_run_initializer().initialize(
            request, route_decision=route_decision, strategy_decision=strategy_decision
        )
        self.route = result.route
        self.strategy = result.strategy
        self.explorer_gate = result.explorer_gate
        self.artifacts = result.artifacts
        self.state = result.state
        return result.run_state

    def _resume(self, run_id: str, decision_answer: str | None = None) -> RunState:
        return self._make_run_progression().resume(run_id, decision_answer)

    def _make_strategy_resolver(self) -> _StrategyResolver:
        return _StrategyResolver(self.route, self.warnings)

    def _hydrate_resume_context(self, state: RunState) -> None:
        ctx = _ResumeContextLoader(self.artifacts).load(state)
        self.route = ctx.route
        self.strategy = ctx.strategy
        self.explorer_gate = ctx.explorer_gate

    def _make_run_progression(self) -> _RunProgression:
        return _RunProgression(self, self._results)

    def _execute(self, initial: RunState) -> RunResult:
        return self._make_run_progression().execute(initial)

    def _make_routing_coordinator(self) -> _RoutingCoordinator:
        assert self.route
        return _RoutingCoordinator(
            self.route, self.strategy, self.explorer_gate, self.state, self.artifacts, self.target
        )

    def _persist_route(self) -> None:
        result = self._make_routing_coordinator().coordinate()
        if result is not None:
            self.route = result.route
            self.strategy = result.strategy
            self.explorer_gate = result.explorer_gate

    def _make_strategy_persister(self) -> _StrategyPersister:
        assert self.strategy
        return _StrategyPersister(
            self.explorer_gate,
            self.strategy,
            self.state,
            self.artifacts,
            answer_choice_fn=self._explorer_gate_answer_choice,
            decision_request_fn=self._explorer_gate_decision_request,
            resolve_fn=self._make_strategy_resolver().resolve,
        )

    def _persist_strategy(self) -> None:
        result = self._make_strategy_persister().persist()
        if result is not None:
            self.explorer_gate = result.explorer_gate
            self.strategy = result.strategy
