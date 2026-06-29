"""Analysis, knowledge, and quality support services for orchestration."""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

from ..control_outputs import ExplorerBundle
from .context import RunContext
from .explorer_context import ExplorerContext
from .explorer_distiller import ExplorerDistiller as _ExplorerDistiller
from .knowledge_loader import KnowledgeLoader as _KnowledgeLoader
from .knowledge_synthesizer import KnowledgeSynthesizer as _KnowledgeSynthesizer
from .learning_context_builder import LearningContextBuilder as _LearningContextBuilder
from .learning_parser import parse_learning_sections as _parse_learning_sections
from .phase_learning_extractor import PhaseLearningExtractor as _PhaseLearningExtractor
from .routing_gate import RoutingGate as _RoutingGate
from .task_coverage_validator import TaskCoverageValidator as _TaskCoverageValidator


class AnalysisSupportService:
    """Own explorer scope, knowledge loading/synthesis, and task coverage checks."""

    def __init__(
        self,
        context: RunContext,
        invoke_with_repair: Callable[..., str],
    ) -> None:
        self._ctx = context
        self._invoke_with_repair = invoke_with_repair

    @staticmethod
    def _clip_text(value: object, limit: int) -> str:
        text = str(value)
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n...[clipped {len(text) - limit} chars]"

    @classmethod
    def parse_learning_sections(cls, candidate: str, *, validate: bool = True) -> dict[str, str | tuple[str, ...]]:
        return _parse_learning_sections(candidate, validate=validate)

    def _make_learning_context_builder(self) -> _LearningContextBuilder:
        return _LearningContextBuilder(
            self._ctx.artifacts,
            self._ctx.state,
            self._ctx.target,
            self._ctx.warnings,
            self._ctx.task_documents,
            self._ctx.repository_observations,
        )

    def _make_knowledge_synthesizer(self) -> _KnowledgeSynthesizer:
        return _KnowledgeSynthesizer(
            self._ctx.target,
            self._ctx.state,
            self._ctx.warnings,
            self._ctx.task_documents,
            self._ctx.repository_observations,
            invoke_fn=lambda name, inputs: self._invoke_with_repair(name, inputs, parse_control=False),
        )

    def _knowledge_synthesis_inputs(
        self,
        source: str,
        *,
        context: Mapping[str, object],
        accepted_evidence: Sequence[Mapping[str, object]] = (),
        rejected_evidence: Sequence[Mapping[str, object]] = (),
        source_artifacts: Sequence[str] = (),
        repair: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return self._make_knowledge_synthesizer().synthesis_inputs(
            source,
            context=context,
            accepted_evidence=accepted_evidence,
            rejected_evidence=rejected_evidence,
            source_artifacts=source_artifacts,
            repair=repair,
        )

    def _invoke_knowledge_synthesis_with_repair(self, inputs: Mapping[str, object]) -> str:
        return self._make_knowledge_synthesizer().invoke_synthesis(inputs)

    def _reviewed_learning_bundle(self, output: str, inputs: Mapping[str, object]) -> ExplorerBundle:
        return self._make_knowledge_synthesizer().reviewed_bundle(output, inputs)

    def _make_phase_learning_extractor(self) -> _PhaseLearningExtractor:
        return _PhaseLearningExtractor(
            knowledge_synthesis_inputs_fn=self._knowledge_synthesis_inputs,
            invoke_knowledge_synthesis_with_repair_fn=self._invoke_knowledge_synthesis_with_repair,
        )

    def _invoke_learning_with_repair(self) -> tuple[str, Mapping[str, object]]:
        context = self._make_learning_context_builder().build()
        result = self._make_phase_learning_extractor().synthesize(
            "learning",
            context=context,
            source_artifacts=self._ctx.artifacts.list(),
        )
        return result.output, result.synthesis_inputs

    def _make_knowledge_loader(self) -> _KnowledgeLoader:
        return _KnowledgeLoader(self._ctx.target, self._ctx.knowledge, self._ctx.warnings, self._ctx.state)

    def _load_knowledge(self) -> None:
        self._ctx.knowledge_context = self._make_knowledge_loader().load()

    def _make_routing_gate(self) -> _RoutingGate:
        return _RoutingGate(self._ctx.state, self._ctx.artifacts, self._ctx.target, self._ctx.canonical)

    def _explorer_scope(self) -> dict[str, object]:
        if self._ctx.explorer_scope_cache is not None:
            return self._ctx.explorer_scope_cache
        result = self._make_routing_gate().scope()
        self._ctx.explorer_scope_cache = result
        return result

    def _explorer_gate_decision_request(self, gate: object) -> object:
        return self._make_routing_gate().decision_request(gate)

    def _explorer_gate_answer_choice(self) -> object:
        return self._make_routing_gate().answer_choice()

    def _validate_full_sdd_task_coverage(self, document: Mapping[str, object], scope: Mapping[str, object]) -> None:
        _TaskCoverageValidator(self._ctx.artifacts, self._ctx.state).validate(document, scope)
