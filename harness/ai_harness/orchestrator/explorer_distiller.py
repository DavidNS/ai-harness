"""ExplorerDistiller - run the explorer_distill worker on a compact improvement candidate.

Handles the invoke-validate-repair cycle. Previously _distilled_compact_improvement on
AnalysisQualityMixin, with cross-mixin deps injected as callbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..contracts.limits import LEARNING as _LEARNING_LIMITS
from ..control_outputs import ExplorerBundleEntry
from ..errors import HarnessError
from ..stores.artifact import ArtifactStore
from .explorer_context import (
    ExplorerContext,
    ExplorerExtractionContext,
)
from .quality import ImprovementQualityGate

_QUALITY_GATE = ImprovementQualityGate()
_LEARNING_REJECTED_LIMIT = _LEARNING_LIMITS.rejected


@dataclass
class DistillResult:
    content: str
    observations: list[dict[str, object]]


class ExplorerDistiller:
    """Distill a compact improvement candidate through the explorer_distill worker."""

    def __init__(
        self,
        artifacts: ArtifactStore,
        *,
        request_brief_fn: Callable[[], str],
        stage_json_fn: Callable[[str], object],
        invoke_with_repair_fn: Callable[[str, dict[str, object]], str],
        invoke_fn: Callable[..., str],
        progress_fn: Callable[[str], None],
    ) -> None:
        self._artifacts = artifacts
        self._request_brief_fn = request_brief_fn
        self._stage_json_fn = stage_json_fn
        self._invoke_with_repair_fn = invoke_with_repair_fn
        self._invoke_fn = invoke_fn
        self._progress_fn = progress_fn

    def distill(
        self,
        content: str,
        entry: ExplorerBundleEntry,
        context: ExplorerContext,
        *,
        split_child: bool,
    ) -> DistillResult:
        """Distill content; return result with updated observations.

        If content is not a compact improvement, returns it unchanged.
        """
        if not _QUALITY_GATE.is_compact_improvement(content):
            return DistillResult(content, [])
        extraction_context = ExplorerExtractionContext(
            entry_id=entry.entry_id,
            artifact_kind=entry.artifact_kind or "improvement",
            learning=content,
            entry_content=content,
            intake={},
            discovery=self._stage_json_fn("explorer_discovery"),
            decision=self._stage_json_fn("explorer_decision"),
            review=(
                self._artifacts.read("explorer/review.md")
                if self._artifacts.exists("explorer/review.md")
                else ""
            ),
            related_improvements=context.related_improvements,
            repository_observations=context.repository_observations,
            evidence_sources_checked=[],
        )
        distill_inputs = extraction_context.distill_inputs(self._request_brief_fn())
        distilled = self._invoke_with_repair_fn("explorer_distill", distill_inputs)
        try:
            _QUALITY_GATE.validate_compact_improvement_quality(
                distilled,
                entry,
                split_child=split_child,
                observations=context.repository_observations,
            )
        except HarnessError as exc:
            text = str(distilled)
            clipped = text[:_LEARNING_REJECTED_LIMIT] + f"\n...[clipped {len(text) - _LEARNING_REJECTED_LIMIT} chars]" if len(text) > _LEARNING_REJECTED_LIMIT else text
            repair: dict[str, object] = {
                "quality_gate_error": str(exc),
                "rejected_candidate_excerpt": clipped,
                "required_changes": [
                    "Keep output as a single compact improvement artifact.",
                    "Preserve concrete repository observations and implementation intent.",
                    "Emit clear acceptance criteria that are structured or explicit and measurable.",
                    "Keep acceptance criteria concrete; avoid phrasing only describing the described behavior.",
                ],
            }
            self._progress_fn("Explorer distill candidate failed quality gate; invoking one repair attempt")
            try:
                distilled = self._invoke_fn("explorer_distill", distill_inputs, repair=repair)
            except TypeError:
                distilled = self._invoke_fn("explorer_distill", {**distill_inputs, "repair": repair})
            _QUALITY_GATE.validate_compact_improvement_quality(
                distilled,
                entry,
                split_child=split_child,
                observations=context.repository_observations,
            )
        return DistillResult(distilled, list(context.repository_observations))
