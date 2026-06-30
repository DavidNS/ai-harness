"""Reusable phase learning extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from ..contracts.enums import PhaseName
from .learning_service import LearningService


@dataclass(frozen=True, slots=True)
class PhaseLearningResult:
    output: str
    synthesis_inputs: Mapping[str, object]
    proposal_path: str | None = None


class PhaseLearningExtractor:
    """Run knowledge synthesis/review publication for a phase context.

    The extractor only coordinates the existing knowledge pipeline. Callers remain
    responsible for choosing phase-specific evidence and context.
    """

    def __init__(
        self,
        *,
        knowledge_synthesis_inputs_fn: Callable[..., dict[str, object]],
        invoke_knowledge_synthesis_with_repair_fn: Callable[[Mapping[str, object]], str],
        learning_service_fn: Callable[[], LearningService] | None = None,
    ) -> None:
        self._knowledge_synthesis_inputs = knowledge_synthesis_inputs_fn
        self._invoke_knowledge_synthesis_with_repair = invoke_knowledge_synthesis_with_repair_fn
        self._learning_service = learning_service_fn

    def synthesize(
        self,
        source: str,
        *,
        context: Mapping[str, object],
        accepted_evidence: Sequence[Mapping[str, object]] = (),
        rejected_evidence: Sequence[Mapping[str, object]] = (),
        source_artifacts: Sequence[str] = (),
    ) -> PhaseLearningResult:
        inputs = self._knowledge_synthesis_inputs(
            source,
            context=context,
            accepted_evidence=accepted_evidence,
            rejected_evidence=rejected_evidence,
            source_artifacts=source_artifacts,
        )
        output = self._invoke_knowledge_synthesis_with_repair(inputs)
        return PhaseLearningResult(output=output, synthesis_inputs=inputs)

    def synthesize_and_publish(
        self,
        source: str,
        *,
        phase: str = PhaseName.TDD_BUNDLE,
        context: Mapping[str, object],
        accepted_evidence: Sequence[Mapping[str, object]] = (),
        rejected_evidence: Sequence[Mapping[str, object]] = (),
        source_artifacts: Sequence[str] = (),
    ) -> PhaseLearningResult:
        if self._learning_service is None:
            raise RuntimeError("learning_service_fn is required to publish phase learning")
        result = self.synthesize(
            source,
            context=context,
            accepted_evidence=accepted_evidence,
            rejected_evidence=rejected_evidence,
            source_artifacts=source_artifacts,
        )
        proposal_path = self._learning_service().publish_learning_proposals(
            result.output,
            phase,
            synthesis_inputs=result.synthesis_inputs,
        )
        return PhaseLearningResult(
            output=result.output,
            synthesis_inputs=result.synthesis_inputs,
            proposal_path=proposal_path,
        )
