"""KnowledgeSynthesizer — knowledge proposal pipeline.

Single responsibility: generate, validate, review, and repair learning proposals
via the knowledge_synthesis and knowledge_review workers.

Previously the synthesis cluster on AnalysisQualityMixin.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Mapping, Sequence

from ..contracts.limits import LEARNING as _LEARNING_LIMITS
from ..knowledge_source import (
    KnowledgeReviewBundle,
    KnowledgeSourceError,
    LearningProposalBundle,
    apply_knowledge_review,
    parse_knowledge_review,
    parse_learning_proposal,
    validate_repository_evidence_policy,
)
from ..phases import PhaseValidationError
from ..stores.state import StateStore
from .repository_scan import RepositoryScanner


def _clip_text(value: object, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[clipped {len(text) - limit} chars]"


class KnowledgeSynthesizer:
    """Generate, validate, review, and repair learning proposals.

    Cheap to instantiate per-operation; warnings mutated in-place.
    """

    def __init__(
        self,
        target: Path,
        state: StateStore,
        warnings: list[str],
        task_documents: dict[str, Mapping[str, object]],
        repository_observations: list[dict[str, object]],
        *,
        invoke_fn: Callable[[str, Mapping[str, object]], str],
    ) -> None:
        self._target = target
        self._state = state
        self._warnings = warnings
        self._task_documents = task_documents
        self._repository_observations = repository_observations
        self._invoke = invoke_fn

    def synthesis_inputs(
        self,
        source: str,
        *,
        context: Mapping[str, object],
        accepted_evidence: Sequence[Mapping[str, object]] = (),
        rejected_evidence: Sequence[Mapping[str, object]] = (),
        source_artifacts: Sequence[str] = (),
        repair: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        state = self._state.load()
        return {
            "source": source,
            "run": {
                "run_id": state.run_id,
                "strategy": state.strategy.value,
                "mode": state.mode.value,
                "current_phase": state.current_phase,
                "completed_phases": state.completed_phases,
                "warnings": self._warnings,
            },
            "source_artifacts": list(source_artifacts),
            "repository_snapshot": RepositoryScanner(self._target, self._warnings).snapshot(
                self._task_documents, self._repository_observations
            ),
            "accepted_evidence": [dict(item) for item in accepted_evidence],
            "rejected_evidence": [dict(item) for item in rejected_evidence],
            "context": dict(context),
            "repair": dict(repair or {}),
        }

    def invoke_synthesis(self, inputs: Mapping[str, object]) -> str:
        return self._validate_policy(self._invoke("knowledge_synthesis", inputs))

    def reviewed_bundle(
        self,
        output: str,
        synthesis_inputs: Mapping[str, object],
    ) -> tuple[LearningProposalBundle, tuple[dict[str, object], ...], KnowledgeReviewBundle]:
        bundle = parse_learning_proposal(output)
        validate_repository_evidence_policy(bundle, self._target)
        review = self._invoke_review(output, synthesis_inputs)
        if any(item["decision"] in {"reject_for_repair", "fail_review"} for item in review.claim_reviews):
            repair: dict[str, object] = {
                "validation_error": "knowledge review requested synthesis repair",
                "knowledge_review": {
                    "proposal_id": review.proposal_id,
                    "claim_reviews": [dict(item) for item in review.claim_reviews],
                    "relation_reviews": [dict(item) for item in review.relation_reviews],
                },
                "rejected_candidate_excerpt": _clip_text(output, _LEARNING_LIMITS.rejected),
            }
            repaired_inputs = {**dict(synthesis_inputs), "repair": repair}
            output = self.invoke_synthesis(repaired_inputs)
            bundle = parse_learning_proposal(output)
            validate_repository_evidence_policy(bundle, self._target)
            review = self._invoke_review(output, repaired_inputs)
        claims, reviewed = apply_knowledge_review(bundle, review)
        result = LearningProposalBundle(bundle.manifest, tuple(claims), bundle.relations)
        validate_repository_evidence_policy(result, self._target)
        return result, reviewed, review

    def _validate_policy(self, output: str) -> str:
        try:
            bundle = parse_learning_proposal(output)
            validate_repository_evidence_policy(bundle, self._target)
        except KnowledgeSourceError as exc:
            error = PhaseValidationError(str(exc))
            setattr(error, "candidate_stdout", output)
            raise error from exc
        return output

    def _review_inputs(self, output: str, synthesis_inputs: Mapping[str, object]) -> dict[str, object]:
        return {
            "proposal": json.loads(output),
            "source": synthesis_inputs["source"],
            "context": synthesis_inputs["context"],
            "repository_snapshot": synthesis_inputs["repository_snapshot"],
            "accepted_evidence": synthesis_inputs["accepted_evidence"],
            "rejected_evidence": synthesis_inputs["rejected_evidence"],
        }

    def _invoke_review(
        self,
        output: str,
        synthesis_inputs: Mapping[str, object],
    ) -> KnowledgeReviewBundle:
        review_output = self._invoke(
            "knowledge_review",
            self._review_inputs(output, synthesis_inputs),
        )
        return parse_knowledge_review(review_output)
