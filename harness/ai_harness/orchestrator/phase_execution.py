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
            PhaseName.EXPLORE_BUNDLE: self._explore_bundle,
            PhaseName.PROPOSAL_BUNDLE: self._proposal_bundle,
            PhaseName.SPEC_BUNDLE: self._spec_bundle,
            PhaseName.DESIGN_BUNDLE: self._design_bundle,
            PhaseName.TASKS_BUNDLE: self._tasks_bundle,
            PhaseName.TDD_BUNDLE: self._tdd_bundle,
        }

    def known_phases(self) -> frozenset[str]:
        return frozenset(self._phase_handlers())

    def _phase(self, phase: str) -> None:
        PhaseExecutor(self._phase_handlers()).execute(phase)

    @staticmethod
    def _noop() -> None:
        return None

    def _publish_handoff(self, bundle: str, payload: Mapping[str, object]) -> None:
        artifact = f"published/{bundle}-handoff.json"
        self.artifacts.write_json(artifact, {"schema_version": 1, "bundle": bundle, **dict(payload)})
        self.state.record_artifact(artifact, bundle.upper() + "_BUNDLE")

    def _archive_knowledge(self, phase: str) -> None:
        archive_artifact = f"knowledge/{phase.lower()}-archive.json"
        self.artifacts.write_json(archive_artifact, {
            "schema_version": 1,
            "phase": phase,
            "source_artifacts": self.artifacts.list(),
        })
        self.state.record_artifact(archive_artifact, phase)
        try:
            output, synthesis_inputs = self._callbacks.invoke_learning_with_repair()
            artifact = f"knowledge/{phase.lower()}.json"
            self.artifacts.write(artifact, output)
            self.state.record_artifact(artifact, phase)
            self._callbacks.publish_learning_proposals(output, phase, synthesis_inputs=synthesis_inputs)
        except ControlFlowSignal:
            raise
        except Exception as exc:
            message = " ".join(str(exc).split())[:500] or type(exc).__name__
            self.warnings.append(f"Knowledge archive failed for {phase}; proposal skipped: {message}")

    def _explore_bundle(self) -> None:
        self._explore()
        if self.artifacts.exists("explore/outcome_bundle.json"):
            self._publish_handoff("explore", {
                "artifacts": ["explore/outcome_bundle.json", "explore/exploration_map.json", "explore/review.md"],
                "next_bundle": "PROPOSAL_BUNDLE",
            })
        self._archive_knowledge("EXPLORE_BUNDLE")

    def _proposal_bundle(self) -> None:
        self._purpose()
        self._publish_handoff("proposal", {"artifacts": ["purpose.md"], "next_bundle": "SPEC_BUNDLE"})

    def _spec_bundle(self) -> None:
        self._spec()
        self._publish_handoff("spec", {"artifacts": ["spec.md"], "next_bundle": "DESIGN_BUNDLE"})

    def _design_bundle(self) -> None:
        self._design()
        self._publish_handoff("design", {"artifacts": ["design.md"], "next_bundle": "TASKS_BUNDLE"})

    def _tasks_bundle(self) -> None:
        self._task_execution.tasks()
        self._publish_handoff("tasks", {"artifacts": ["tasks.json"], "next_bundle": "TDD_BUNDLE"})

    def _tdd_bundle(self) -> None:
        self._task_execution.tdd()
        self._publish_handoff("tdd", {"artifacts": ["review.md", "tasks.json"], "next_bundle": None})
        self._archive_knowledge("TDD_BUNDLE")

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

    def _handle_control_output(self, output: ControlOutput, *, target_phase: str) -> RunResult | None:
        return self._control_output_handler.handle(output, target_phase=target_phase)

