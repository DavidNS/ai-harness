"""Explicit phase execution collaborator for orchestration phases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from ..config import HarnessConfig
from ..contracts.enums import PhaseName
from ..control_outputs import (
    ControlFlowSignal,
    ControlOutput,
)
from ..models import KnowledgeEntry
from ..output import RunResult
from ..phases import get_phase
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from .context import RunContext
from .control_output_handler import ControlOutputHandler
from .explorer_context import ExplorerContext
from .explore_pipeline import ExplorePipelineService
from .phase_executor import PhaseExecutor
from .phase_repair import PhaseRepairRunner
from .task_execution import TaskExecution


@dataclass(frozen=True)
class PhaseExecutionCallbacks:
    load_knowledge: Callable[[], None]
    persist_route: Callable[[], None]
    persist_strategy: Callable[[], None]
    explorer: Callable[[], None]
    explorer_intake: Callable[[], None]
    explorer_discovery: Callable[[], None]
    explorer_decision: Callable[[], None]
    explorer_artifact: Callable[[], None]
    explorer_review: Callable[[], None]
    finalize: Callable[[], None]
    explorer_scope: Callable[[], dict[str, object]]
    related_improvements: Callable[[], list[dict[str, str | int]]]
    repository_observations: Callable[..., list[dict[str, object]]]
    validate_full_sdd_task_coverage: Callable[[Mapping[str, object], Mapping[str, object]], None]
    invoke: Callable[..., str]
    worker: Callable[[str, Mapping[str, object]], str]
    full_sdd_inputs: Callable[..., dict[str, object]]
    request_brief: Callable[[], str]
    referenced_markdown_documents: Callable[[str], dict[str, str]]
    publish_learning_proposals: Callable[..., str]
    invoke_learning_with_repair: Callable[[], tuple[str, Mapping[str, object]]]
    explorer_context_from_discovery: Callable[[], ExplorerContext]
    markdown_section: Callable[[str, str], str]
    publish_explorer_bundle: Callable[..., object]
    waiting_result: Callable[[object], RunResult]
    clip_text: Callable[[object, int], str]


class PhaseExecution:
    """Execute phase bodies against explicit context and callbacks."""

    def __init__(self, context: RunContext, callbacks: PhaseExecutionCallbacks) -> None:
        self._ctx = context
        self._callbacks = callbacks
        self._task_execution = TaskExecution(context, callbacks, self._invoke_with_repair)
        self._control_output_handler = ControlOutputHandler(context, callbacks)

    @property
    def target(self) -> Path:
        return self._ctx.target

    @property
    def config(self) -> HarnessConfig:
        return self._ctx.config

    @property
    def artifacts(self) -> ArtifactStore:
        return self._ctx.artifacts

    @property
    def state(self) -> StateStore:
        return self._ctx.state

    @property
    def progress(self) -> Callable[[str], None]:
        return self._ctx.progress

    @property
    def knowledge_context(self) -> list[KnowledgeEntry]:
        return self._ctx.knowledge_context

    @property
    def task_documents(self) -> dict[str, Mapping[str, object]]:
        return self._ctx.task_documents

    @task_documents.setter
    def task_documents(self, value: dict[str, Mapping[str, object]]) -> None:
        self._ctx.task_documents = value

    @property
    def repository_observations(self) -> list[dict[str, object]]:
        return self._ctx.repository_observations

    @repository_observations.setter
    def repository_observations(self, value: list[dict[str, object]]) -> None:
        self._ctx.repository_observations = value

    @property
    def warnings(self) -> list[str]:
        return self._ctx.warnings

    def _phase_handlers(self) -> dict[str, Callable[[], None]]:
        return {
            PhaseName.INITIALIZING: self._noop,
            PhaseName.DETECTING_INTENT: self._noop,
            PhaseName.LOADING_KNOWLEDGE: self._callbacks.load_knowledge,
            PhaseName.ROUTING: self._callbacks.persist_route,
            PhaseName.SELECTING_STRATEGY: self._callbacks.persist_strategy,
            PhaseName.EXPLORE: self._explore,
            PhaseName.PURPOSE: self._purpose,
            PhaseName.SPEC: self._spec,
            PhaseName.DESIGN: self._design,
            PhaseName.TASKS: self._task_execution.tasks,
            PhaseName.SIMPLE_TASK: self._task_execution.simple_task,
            PhaseName.TDD_LOOP: self._task_execution.tdd,
            PhaseName.EXPLORER: self._callbacks.explorer,
            PhaseName.EXPLORER_INTAKE: self._callbacks.explorer_intake,
            PhaseName.EXPLORER_DISCOVERY: self._callbacks.explorer_discovery,
            PhaseName.EXPLORER_DECISION: self._callbacks.explorer_decision,
            PhaseName.EXPLORER_ARTIFACT: self._callbacks.explorer_artifact,
            PhaseName.EXPLORER_REVIEW: self._callbacks.explorer_review,
            PhaseName.LEARNING: self._learning,
            PhaseName.NON_CODE_STUB: self._non_code,
            PhaseName.FINALIZING: self._callbacks.finalize,
        }

    def known_phases(self) -> frozenset[str]:
        return frozenset(self._phase_handlers())

    def _phase(self, phase: str) -> None:
        PhaseExecutor(self._phase_handlers()).execute(phase)

    @staticmethod
    def _noop() -> None:
        return None

    def _explore(self) -> None:
        ExplorePipelineService(self._ctx, self._callbacks, self._invoke_with_repair).run()

    def _purpose(self) -> None:
        self._callbacks.worker("purpose", {
            "request": self._callbacks.request_brief(),
            "explore/outcome_bundle.json": self.artifacts.read_json("explore/outcome_bundle.json"),
            "explorer_scope": self._callbacks.explorer_scope(),
        })

    def _spec(self) -> None:
        self._callbacks.worker("spec", self._callbacks.full_sdd_inputs("explore/outcome_bundle.json", "purpose.md"))

    def _design(self) -> None:
        self._callbacks.worker("design", self._callbacks.full_sdd_inputs("explore/outcome_bundle.json", "spec.md"))

    def _invoke_with_repair(self, name: str, inputs: Mapping[str, object], *, parse_control: bool = True) -> str:
        return PhaseRepairRunner(
            invoke=self._callbacks.invoke,
            artifacts=self.artifacts,
            state=self.state,
            progress=self.progress,
            clip_text=self._callbacks.clip_text,
        ).invoke(name, inputs, parse_control=parse_control)

    def _learning(self) -> None:
        try:
            output, synthesis_inputs = self._callbacks.invoke_learning_with_repair()
        except ControlFlowSignal:
            raise
        except Exception as exc:
            message = " ".join(str(exc).split())[:500] or type(exc).__name__
            self.warnings.append(f"Learning failed; knowledge proposal skipped: {message}")
            return
        try:
            artifact = get_phase("learning").artifact
            self.artifacts.write(artifact, output)
            self.state.record_artifact(artifact, "LEARNING")
            self._callbacks.publish_learning_proposals(output, "LEARNING", synthesis_inputs=synthesis_inputs)
        except Exception as exc:
            message = " ".join(str(exc).split())[:500] or type(exc).__name__
            self.warnings.append(f"Learning failed; knowledge proposal skipped: {message}")
            return

    def _non_code(self) -> None:
        self.artifacts.write("non_code.md", "# Non-Code Request v1\n\nNon-code orchestration is not implemented in v1.\nNo modifying worker was invoked.\n")
        self.state.record_artifact("non_code.md", "NON_CODE_STUB")

    def _handle_control_output(self, output: ControlOutput, *, target_phase: str) -> RunResult | None:
        return self._control_output_handler.handle(output, target_phase=target_phase)

