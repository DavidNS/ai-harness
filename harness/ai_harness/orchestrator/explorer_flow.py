"""Shared orchestration mixin support."""

from __future__ import annotations

from typing import Callable, Mapping

from ..contracts.enums import PhaseName
from ..contracts.limits import LEARNING as _LEARNING_LIMITS
from ..control_outputs import (
    ControlFlowSignal,
    ExplorerBundle,
    ExplorerBundleEntry,
    PhaseEscalation,
)
from ..errors import HarnessError
from .analysis_quality import AnalysisSupportService
from .context import RunContext
from .explorer_artifacts import ExplorerArtifacts
from .explorer_bundle_parser import ExplorerBundleParser as _ExplorerBundleParser
from .explorer_context import ExplorerContext
from .explorer_decision_reader import ExplorerDecisionReader as _DecisionReader
from .explorer_distiller import ExplorerDistiller as _ExplorerDistiller
from .explorer_inputs import ExplorerInputs
from .explorer_phase_service import ExplorerPhaseService
from .learning_service import LearningService as _LearningService
from .publishing import (
    BundlePlanner,
    ExplorerPublisher,
)
from .quality import ImprovementQualityGate as _ImprovementQualityGate
from .worker_exchange import WorkerExchange

_LEARNING_REJECTED_LIMIT = _LEARNING_LIMITS.rejected


class ExplorerFlowService:
    """Own explorer phase sequencing, repair, review, and publication."""

    def __init__(
        self,
        context: RunContext,
        request_context: WorkerExchange,
        analysis: AnalysisSupportService,
        invoke: Callable[..., str],
        invoke_with_repair: Callable[..., str],
    ) -> None:
        self._ctx = context
        self._request_context = request_context
        self._analysis = analysis
        self._invoke = invoke
        self._invoke_with_repair = invoke_with_repair
        self._explorer_artifacts = ExplorerArtifacts(context)
        self._explorer_inputs_builder = ExplorerInputs(
            context,
            request_context,
            self._explorer_artifacts,
        )
        self._phase_service = ExplorerPhaseService(
            self._explorer_artifacts,
            self._explorer_inputs_builder,
            self._make_decision_reader,
            invoke_with_repair,
        )

    @property
    def state(self):
        return self._ctx.state

    @property
    def artifacts(self):
        return self._ctx.artifacts

    @property
    def canonical(self):
        return self._ctx.canonical

    @property
    def target(self):
        return self._ctx.target

    @property
    def progress(self):
        return self._ctx.progress

    @property
    def warnings(self) -> list[str]:
        return self._ctx.warnings

    @property
    def knowledge_context(self):
        return self._ctx.knowledge_context

    @property
    def repository_observations(self) -> list[dict[str, object]]:
        return self._ctx.repository_observations

    @repository_observations.setter
    def repository_observations(self, value: list[dict[str, object]]) -> None:
        self._ctx.repository_observations = value

    def _request_brief(self) -> str:
        return self._request_context._request_brief()

    def _related_improvements(self) -> list[dict[str, str | int]]:
        return self._request_context._related_improvements()

    def _repository_observations(self, related_improvements, intake=None):
        return self._request_context._repository_observations(related_improvements, intake)

    def _explorer_artifact_path(self, candidate: str) -> str:
        return self._request_context._explorer_artifact_path(candidate)

    @staticmethod
    def _markdown_section(candidate: str, section: str) -> str:
        return WorkerExchange._markdown_section(candidate, section)

    @staticmethod
    def parse_learning_sections(candidate: str, *, validate: bool = True):
        return AnalysisSupportService.parse_learning_sections(candidate, validate=validate)

    @staticmethod
    def _clip_text(value: object, limit: int) -> str:
        return AnalysisSupportService._clip_text(value, limit)

    def _knowledge_synthesis_inputs(self, *args, **kwargs):
        return self._analysis._knowledge_synthesis_inputs(*args, **kwargs)

    def _invoke_knowledge_synthesis_with_repair(self, inputs):
        return self._analysis._invoke_knowledge_synthesis_with_repair(inputs)

    def _make_explorer_distiller(self) -> _ExplorerDistiller:
        return _ExplorerDistiller(
            self.artifacts,
            request_brief_fn=self._request_brief,
            stage_json_fn=self._explorer_stage_json,
            invoke_with_repair_fn=lambda name, inputs: self._invoke_with_repair(name, inputs, parse_control=False),
            invoke_fn=lambda name, inputs, **kwargs: self._invoke(name, inputs, parse_control=False, **kwargs),
            progress_fn=self.progress,
        )

    def _distilled_compact_improvement(
        self,
        content: str,
        entry: ExplorerBundleEntry,
        context: ExplorerContext,
        *,
        split_child: bool,
    ) -> str:
        result = self._make_explorer_distiller().distill(content, entry, context, split_child=split_child)
        self.repository_observations = result.observations
        return result.content

    def _distill_explorer_bundle(self, bundle: ExplorerBundle) -> dict[str, str]:
        split_child_ids = self._make_bundle_planner().bundle_split_child_ids(bundle)
        context = self._explorer_context_from_discovery()
        distilled: dict[str, str] = {}
        for entry in bundle.entries:
            if entry.content is None:
                continue
            try:
                distilled[entry.entry_id] = self._distilled_compact_improvement(
                    entry.content,
                    entry,
                    context,
                    split_child=entry.entry_id in split_child_ids,
                )
            except Exception as exc:
                raise HarnessError(f"explorer bundle entry {entry.entry_id}: {exc}") from exc
        return distilled

    def _bundle_from_explorer_output(self, output: str) -> ExplorerBundle:
        return _ExplorerBundleParser(self.state).parse(output)

    def _make_decision_reader(self) -> _DecisionReader:
        return _DecisionReader(self.state, self.artifacts)

    def _make_bundle_planner(self) -> BundlePlanner:
        return BundlePlanner(
            self.canonical,
            _ImprovementQualityGate(),
            self.repository_observations,
            explorer_artifact_path_fn=self._explorer_artifact_path,
            parse_learning_sections_fn=self.parse_learning_sections,
        )

    def _make_learning_service(self) -> _LearningService:
        return _LearningService(
            self.canonical,
            self.artifacts,
            self.state,
            self.warnings,
            reviewed_learning_bundle_fn=self._analysis._reviewed_learning_bundle,
        )

    def _make_explorer_publisher(self) -> ExplorerPublisher:
        return ExplorerPublisher(
            self.canonical,
            self.artifacts,
            self.state,
            self.warnings,
            self.target,
            repository_observations_fn=lambda: self.repository_observations,
            stage_json_fn=self._explorer_stage_json,
            safe_stage_json_fn=self._safe_explorer_stage_json,
            learning_service_fn=self._make_learning_service,
            knowledge_synthesis_inputs_fn=self._knowledge_synthesis_inputs,
            invoke_knowledge_synthesis_with_repair_fn=self._invoke_knowledge_synthesis_with_repair,
            distilled_compact_improvement_fn=self._distilled_compact_improvement,
            explorer_artifact_path_fn=self._explorer_artifact_path,
            parse_learning_sections_fn=self.parse_learning_sections,
        )

    def _publish_explorer_bundle(
        self,
        bundle: ExplorerBundle,
        context: ExplorerContext,
        *,
        target_phase: str = PhaseName.EXPLORE_BUNDLE,
        split_bundle_rationale: str | None = None,
        pre_distilled_content: Mapping[str, str] | None = None,
    ) -> None:
        self._make_explorer_publisher().publish_bundle(
            bundle,
            context,
            target_phase=target_phase,
            split_bundle_rationale=split_bundle_rationale,
            pre_distilled_content=pre_distilled_content,
        )
        self._record_explorer_bundle(
            bundle,
            context,
            target_phase=target_phase,
            split_bundle_rationale=split_bundle_rationale,
            pre_distilled_content=pre_distilled_content,
        )


    def _record_explorer_bundle(
        self,
        bundle: ExplorerBundle,
        context: ExplorerContext,
        *,
        target_phase: str,
        split_bundle_rationale: str | None = None,
        pre_distilled_content: Mapping[str, str] | None = None,
    ) -> None:
        payload = bundle.to_dict()
        payload["context"] = context.to_dict()
        if split_bundle_rationale:
            payload["split_bundle_rationale"] = split_bundle_rationale
        if pre_distilled_content:
            payload["distilled_content"] = dict(pre_distilled_content)
        self.artifacts.write_json("explorer/bundle.json", payload)
        self.state.record_artifact("explorer/bundle.json", target_phase)

    @staticmethod
    def _is_explorer_quality_error(exc: Exception) -> bool:
        text = str(exc)
        return "compact improvement" in text or "broad explorer improvement" in text or "split_bundle" in text

    def _explorer_inputs(
        self,
        context: ExplorerContext,
        *,
        repair: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return self._explorer_inputs_builder.legacy_explorer(context, repair=repair)

    def _publish_explorer_output_with_repair(
        self,
        output: str,
        context: ExplorerContext,
    ) -> None:
        reader = self._make_decision_reader()
        split_bundle_rationale = reader.split_bundle_rationale()
        try:
            self._record_explorer_bundle(
                self._bundle_from_explorer_output(output),
                context,
                target_phase=PhaseName.EXPLORE_BUNDLE,
                split_bundle_rationale=split_bundle_rationale,
            )
        except HarnessError as exc:
            if not self._is_explorer_quality_error(exc):
                raise
            repair = {
                "quality_gate_error": str(exc),
                "rejected_candidate_excerpt": self._clip_text(output, _LEARNING_REJECTED_LIMIT),
                "required_changes": [
                    "Cite concrete repository observations when available.",
                    "Make desired behavior bounded and distinct from the problem.",
                    "Use observable acceptance criteria.",
                    "Split broad multi-surface requests or include a scope justification.",
                ],
            }
            self.progress("Explorer candidate failed quality gate; invoking one repair attempt")
            repaired = self._invoke("explorer", self._explorer_inputs(context, repair=repair))
            self._record_explorer_bundle(
                self._bundle_from_explorer_output(repaired),
                context,
                target_phase=PhaseName.EXPLORE_BUNDLE,
                split_bundle_rationale=reader.split_bundle_rationale(),
            )

    def _write_phase_artifact(self, name: str, output: str) -> None:
        self._explorer_artifacts.write_phase_artifact(name, output)

    def _explorer_stage_artifact(self, name: str) -> str:
        return self._explorer_artifacts.stage_artifact(name)

    def _explorer_stage_json(self, name: str) -> dict[str, object]:
        return self._explorer_artifacts.stage_json(name)

    def _safe_explorer_stage_json(self, name: str) -> dict[str, object]:
        return self._explorer_artifacts.safe_stage_json(name)

    def _explorer_context_from_discovery(self) -> ExplorerContext:
        return self._explorer_artifacts.context_from_discovery()

    def _explorer_intake(self) -> None:
        self._phase_service.intake()

    def _explorer_discovery(self) -> None:
        self._phase_service.discovery()

    def _explorer_decision(self) -> None:
        self._phase_service.decision()

    def _explorer_artifact_inputs(
        self,
        context: ExplorerContext,
        *,
        repair: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return self._explorer_inputs_builder.artifact(context, repair=repair)

    def _explorer_artifact(self) -> None:
        self._phase_service.artifact()

    def _explorer_candidate_bundle(self, candidate: str) -> ExplorerBundle:
        bundle = self._bundle_from_explorer_output(candidate)
        if self._make_decision_reader().decision_outcome() == "split_bundle" and len(bundle.entries) < 2:
            raise HarnessError("split_bundle outcome requires a bundle with at least 2 entries")
        return bundle

    def _repair_explorer_artifact(self, reason: str, candidate: str) -> str:
        repair = {
            "quality_gate_error": reason,
            "rejected_candidate_excerpt": self._clip_text(candidate, _LEARNING_REJECTED_LIMIT),
            "required_changes": [
                "Preserve the selected explorer decision outcome.",
                "Cite concrete repository evidence when available.",
                "Make desired behavior bounded and distinct from the problem.",
                "Use observable acceptance criteria.",
                "Split broad multi-surface requests or include a scope justification.",
            ],
        }
        self.progress("Explorer artifact candidate failed review or quality gate; invoking one repair attempt")
        context = self._explorer_context_from_discovery()
        repaired = self._invoke(
            "explorer_artifact",
            self._explorer_artifact_inputs(context, repair=repair),
            parse_control=False,
        )
        self._write_phase_artifact("explorer_artifact", repaired)
        return repaired

    def _explorer_review_inputs(self, candidate: str, context: ExplorerContext) -> dict[str, object]:
        return self._explorer_inputs_builder.review(candidate, context)

    def _review_approves_explorer(self, review: str) -> bool:
        return self._markdown_section(review, "Verdict").strip() == "APPROVE"

    def _review_flags_decision_error(self, review: str) -> bool:
        findings = self._markdown_section(review, "Findings").casefold()
        return "decision" in findings or "outcome" in findings

    def _invoke_explorer_review(self, candidate: str) -> str:
        context = self._explorer_context_from_discovery()
        review = self._invoke_with_repair("explorer_review", self._explorer_review_inputs(candidate, context))
        self._write_phase_artifact("explorer_review", review)
        return review

    def _explorer_review(self) -> None:
        candidate = self.artifacts.read(self._explorer_stage_artifact("explorer_artifact"))
        repaired = False
        try:
            bundle = self._explorer_candidate_bundle(candidate)
        except HarnessError as exc:
            if not self._is_explorer_quality_error(exc):
                raise
            candidate = self._repair_explorer_artifact(str(exc), candidate)
            repaired = True
            bundle = self._explorer_candidate_bundle(candidate)

        review = self._invoke_explorer_review(candidate)
        if not self._review_approves_explorer(review):
            if self._review_flags_decision_error(review):
                raise ControlFlowSignal(PhaseEscalation(
                    PhaseName.EXPLORE_BUNDLE,
                    PhaseName.EXPLORE_BUNDLE,
                    "Explorer review found outcome drift or an incorrect decision.",
                ))
            if repaired:
                raise HarnessError("explorer artifact repair exhausted after review request changes")
            candidate = self._repair_explorer_artifact(self._markdown_section(review, "Findings"), candidate)
            bundle = self._explorer_candidate_bundle(candidate)
            review = self._invoke_explorer_review(candidate)
            if not self._review_approves_explorer(review):
                raise HarnessError("explorer review did not approve repaired artifact")

        try:
            distilled_bundle = self._distill_explorer_bundle(bundle)
        except HarnessError as exc:
            if repaired or not self._is_explorer_quality_error(exc):
                raise
            candidate = self._repair_explorer_artifact(str(exc), candidate)
            repaired = True
            bundle = self._explorer_candidate_bundle(candidate)
            review = self._invoke_explorer_review(candidate)
            if not self._review_approves_explorer(review):
                raise HarnessError("explorer review did not approve quality-repaired artifact")
            distilled_bundle = self._distill_explorer_bundle(bundle)
        context = self._explorer_context_from_discovery()
        self._publish_explorer_bundle(
            bundle,
            context,
            target_phase=PhaseName.EXPLORE_BUNDLE,
            split_bundle_rationale=self._make_decision_reader().split_bundle_rationale(),
            pre_distilled_content=distilled_bundle,
        )

    def _explorer(self) -> None:
        related_improvements = self._related_improvements()
        context = ExplorerContext(
            related_improvements=list(related_improvements),
            repository_observations=self._repository_observations(related_improvements),
        )
        self.repository_observations = context.repository_observations
        output = self._invoke_with_repair("explorer", self._explorer_inputs(context))
        self._publish_explorer_output_with_repair(output, context)
