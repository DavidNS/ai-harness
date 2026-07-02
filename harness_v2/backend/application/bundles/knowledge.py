"""Knowledge extraction bundles for v2 candidate patches."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.bundle_orchestration import BundleContext, BundleExecutionResult
from harness_v2.backend.application.contracts import KnowledgePatchCreated
from harness_v2.backend.domain.errors import DomainValidationError
from harness_v2.backend.domain.knowledge import parse_learning_proposal
from harness_v2.backend.domain.lifecycle import PhaseName


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionBundleDefinition:
    phase: PhaseName
    source_phase: PhaseName
    required_artifacts: tuple[str, ...]
    failure_code: str
    produced_artifacts: tuple[str, ...] = ()
    produced_prefixes: tuple[str, ...] = ()

    def execute(self, context: BundleContext) -> BundleExecutionResult:
        if context.knowledge_patches is None:
            raise BundleValidationError(f"{self.phase.value} requires a knowledge patch store")
        inputs = {
            "run_id": context.run.run_id,
            "request": context.run.request,
            "source_phase": self.source_phase.value,
            "source_artifacts": self._source_artifacts(context),
        }
        output = context.artifacts.run_worker_text(context.run, self.phase, "knowledge_synthesis", inputs)
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise BundleValidationError("knowledge_synthesis output must be valid JSON") from exc
        try:
            proposal = parse_learning_proposal(payload)
        except DomainValidationError as exc:
            raise BundleValidationError(str(exc)) from exc
        patch = context.knowledge_patches.create_patch(
            context.run.run_id,
            self.source_phase,
            proposal,
            context.clock.now_iso(),
        )
        return BundleExecutionResult(
            events=(
                KnowledgePatchCreated(
                    run_id=context.run.run_id,
                    patch_id=patch.patch_id,
                    origin_phase=patch.origin_phase.value,
                    path=patch.path,
                ),
            )
        )

    def _source_artifacts(self, context: BundleContext) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for artifact_id in self.required_artifacts:
            if artifact_id.endswith(".json"):
                value = context.artifacts.read_json(context.run.run_id, artifact_id)
                if value is None:
                    raise BundleValidationError(f"required artifact {artifact_id} is missing")
                values[artifact_id] = value
            else:
                value = context.artifacts.read_text(context.run.run_id, artifact_id)
                if value is None:
                    raise BundleValidationError(f"required artifact {artifact_id} is missing")
                values[artifact_id] = value
        return values


def knowledge_bundle_definitions() -> tuple[KnowledgeExtractionBundleDefinition, ...]:
    return (
        KnowledgeExtractionBundleDefinition(
            phase=PhaseName.KNOWLEDGE_EXTRACT_EXPLORE,
            source_phase=PhaseName.EXPLORE_BUNDLE,
            required_artifacts=("explore/outcome_bundle.json", "published/explore-handoff.json"),
            failure_code="KNOWLEDGE_EXTRACT_EXPLORE_FAILED",
            produced_prefixes=("workers/KNOWLEDGE_EXTRACT_EXPLORE/",),
        ),
        KnowledgeExtractionBundleDefinition(
            phase=PhaseName.KNOWLEDGE_EXTRACT_TDD,
            source_phase=PhaseName.TDD_BUNDLE,
            required_artifacts=("published/tdd-results.json", "published/tdd-handoff.json"),
            failure_code="KNOWLEDGE_EXTRACT_TDD_FAILED",
            produced_prefixes=("workers/KNOWLEDGE_EXTRACT_TDD/",),
        ),
    )
