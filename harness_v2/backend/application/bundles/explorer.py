"""Explorer workflow bundle definitions for the v2 skeleton."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.bundle_orchestration import BundleContext, BundleExecutionResult
from harness_v2.backend.application.bundles.explorer_recovery import ensure_refinement_artifact, handle_explorer_decision
from harness_v2.backend.domain.lifecycle import PhaseName

JsonValidator = Callable[[dict[str, Any]], None]
TextValidator = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ExplorerStageSpec:
    phase: PhaseName
    task_id: str
    artifact_id: str
    output: str
    validator: JsonValidator | TextValidator


EXPLORER_STAGE_SPECS: tuple[ExplorerStageSpec, ...] = (
    ExplorerStageSpec(
        PhaseName.EXPLORER_INTAKE,
        "explorer_intake",
        "explorer/intake.json",
        "json",
        lambda value: validate_explorer_intake(value),
    ),
    ExplorerStageSpec(
        PhaseName.EXPLORER_DISCOVERY,
        "explorer_discovery",
        "explorer/discovery.json",
        "json",
        lambda value: validate_explorer_discovery(value),
    ),
    ExplorerStageSpec(
        PhaseName.EXPLORER_DECISION,
        "explorer_decision",
        "explorer/decision.json",
        "json",
        lambda value: validate_explorer_decision(value),
    ),
    ExplorerStageSpec(
        PhaseName.EXPLORER_ARTIFACT,
        "explorer_artifact",
        "explorer/artifact-candidate.txt",
        "text",
        lambda value: validate_explorer_artifact(value),
    ),
    ExplorerStageSpec(
        PhaseName.EXPLORER_REVIEW,
        "explorer_review",
        "explorer/review.md",
        "text",
        lambda value: validate_explorer_review(value),
    ),
    ExplorerStageSpec(
        PhaseName.EXPLORER_DISTILL,
        "explorer_distill",
        "explorer/distilled-candidate.md",
        "text",
        lambda value: validate_explorer_distill(value),
    ),
)


@dataclass(frozen=True, slots=True)
class ExplorerStageBundleDefinition:
    spec: ExplorerStageSpec

    @property
    def phase(self) -> PhaseName:
        return self.spec.phase

    @property
    def failure_code(self) -> str:
        return f"{self.phase.value}_FAILED"

    @property
    def produced_artifacts(self) -> tuple[str, ...]:
        return (self.spec.artifact_id,)

    @property
    def produced_prefixes(self) -> tuple[str, ...]:
        return ()

    def execute(self, context: BundleContext) -> BundleExecutionResult:
        run = context.run
        if self.phase is PhaseName.EXPLORER_DISCOVERY:
            ensure_refinement_artifact(context)
        inputs = build_explorer_inputs(context)
        if self.spec.output == "json":
            value = context.artifacts.ensure_worker_json(
                run,
                self.phase,
                self.spec.task_id,
                self.spec.artifact_id,
                inputs,
                self.spec.validator,  # type: ignore[arg-type]
            )
            if self.phase is PhaseName.EXPLORER_DECISION:
                recovery = handle_explorer_decision(context, value)
                if recovery is not None:
                    return recovery
        else:
            context.artifacts.ensure_worker_text(
                run,
                self.phase,
                self.spec.task_id,
                self.spec.artifact_id,
                inputs,
                self.spec.validator,  # type: ignore[arg-type]
            )
        return BundleExecutionResult()


def explorer_bundle_definitions() -> tuple[ExplorerStageBundleDefinition, ...]:
    return tuple(ExplorerStageBundleDefinition(spec) for spec in EXPLORER_STAGE_SPECS)


def build_explorer_inputs(context: BundleContext) -> dict[str, object]:
    run_id = context.run.run_id
    related = _artifact_list(context, "explorer/related_improvements.json", keys=("related_improvements", "items"))
    observations = _artifact_list(context, "explorer/repository_observations.json", keys=("repository_observations", "observations", "items"))
    inputs: dict[str, object] = {
        "request": context.run.request,
        "knowledge": [],
        "repository": str(context.runtime.working_directory),
        "runtime_context": _artifact_json(context, "runtime/context.json") or {},
        "related_improvements": related,
        "repository_observations": observations,
        "refinement": _artifact_json(context, "explorer/refinement.json"),
        "repair": _artifact_json(context, "explorer/repair.json") or {},
    }
    for key, artifact_id in (
        ("intake", "explorer/intake.json"),
        ("discovery", "explorer/discovery.json"),
        ("decision", "explorer/decision.json"),
    ):
        value = _artifact_json(context, artifact_id)
        if value is not None:
            inputs[key] = value
    candidate = context.artifacts.read_text(run_id, "explorer/artifact-candidate.txt")
    if candidate is not None:
        inputs["artifact_candidate"] = candidate
    review = context.artifacts.read_text(run_id, "explorer/review.md")
    if review is not None:
        inputs["review"] = review
    return inputs


def validate_explorer_intake(value: dict[str, Any]) -> None:
    _require_document(value, "explorer_intake")
    claims = _object_list(value.get("claims"), "claims", allow_empty=False)
    seen: set[str] = set()
    for claim in claims:
        claim_id = _text(claim.get("id"), "claim id")
        if claim_id in seen:
            raise BundleValidationError("claim IDs must be unique")
        seen.add(claim_id)
        claim_class = _text(claim.get("class"), "claim class")
        if claim_class not in {"repository-factual", "duplicate-check", "product-tradeoff", "artifact-synthesis"}:
            raise BundleValidationError("claim class is invalid")
        _text(claim.get("text"), "claim text")
        _string_list(claim.get("evidence_targets", []), "evidence_targets")
    framing = value.get("strategic_framing")
    if framing is not None and not isinstance(framing, dict):
        raise BundleValidationError("strategic_framing must be an object")
    _string_list(value.get("synthesis_notes", []), "synthesis_notes")


def validate_explorer_discovery(value: dict[str, Any]) -> None:
    _require_document(value, "explorer_discovery")
    claims = _object_list(value.get("claims"), "claims", allow_empty=False)
    claim_ids: set[str] = set()
    for claim in claims:
        claim_id = _text(claim.get("id"), "claim id")
        if claim_id in claim_ids:
            raise BundleValidationError("discovery claim IDs must be unique")
        claim_ids.add(claim_id)
        status = _text(claim.get("status"), "claim status")
        if status not in {"resolved", "unresolved", "not_applicable"}:
            raise BundleValidationError("claim status is invalid")
        evidence = _string_list(claim.get("evidence", []), "evidence")
        if status == "resolved" and not evidence:
            raise BundleValidationError("resolved claims require evidence")
        if status == "unresolved":
            _text(claim.get("unresolved_reason"), "unresolved_reason")
    for trace in _object_list(value.get("evidence_trace", []), "evidence_trace"):
        _text(trace.get("id"), "evidence_trace id")
        if _text(trace.get("claim_id"), "evidence_trace claim_id") not in claim_ids:
            raise BundleValidationError("evidence_trace claim_id must reference a discovery claim")
        _text(trace.get("source"), "evidence_trace source")
        _text(trace.get("path"), "evidence_trace path")
        _text(trace.get("excerpt"), "evidence_trace excerpt")
        confidence = _text(trace.get("confidence"), "evidence_trace confidence")
        if confidence not in {"low", "medium", "high", "critical"}:
            raise BundleValidationError("evidence_trace confidence is invalid")
    duplicate = value.get("duplicate_search")
    if duplicate is not None and not isinstance(duplicate, dict):
        raise BundleValidationError("duplicate_search must be an object")
    _object_list(value.get("candidate_directions", []), "candidate_directions")
    _object_list(value.get("critic_findings", []), "critic_findings")
    _list(value.get("related_improvements", []), "related_improvements")
    _list(value.get("repository_observations", []), "repository_observations")


def validate_explorer_decision(value: dict[str, Any]) -> None:
    _require_document(value, "explorer_decision")
    outcome = _text(value.get("outcome"), "outcome")
    if outcome not in {
        "new_improvement",
        "split_bundle",
        "update_existing",
        "duplicate_noop",
        "existing_functionality",
        "limitation",
        "not_worth_it",
        "needs_user_decision",
        "escalate_discovery",
    }:
        raise BundleValidationError("explorer decision outcome is invalid")
    _text(value.get("rationale"), "rationale")
    _string_list(value.get("evidence"), "evidence", allow_empty=False)
    for field in ("selected_direction", "value_hypothesis", "behavioral_delta", "minimum_verification"):
        if value.get(field) is not None:
            _text(value.get(field), field)
    _object_list(value.get("rejected_alternatives", []), "rejected_alternatives")
    _string_list(value.get("counterevidence", []), "counterevidence")
    _string_list(value.get("falsifying_conditions", []), "falsifying_conditions")


def validate_explorer_artifact(value: str) -> None:
    _nonempty_text(value, "explorer artifact candidate")


def validate_explorer_review(value: str) -> None:
    text = _nonempty_text(value, "explorer review")
    if "## Verdict" not in text or "## Findings" not in text:
        raise BundleValidationError("explorer review must include Verdict and Findings sections")


def validate_explorer_distill(value: str) -> None:
    text = _nonempty_text(value, "explorer distilled candidate")
    if not text.startswith("#"):
        raise BundleValidationError("explorer distilled candidate must be markdown")


def _artifact_json(context: BundleContext, artifact_id: str) -> dict[str, Any] | None:
    return context.artifacts.read_json(context.run.run_id, artifact_id)


def _artifact_list(context: BundleContext, artifact_id: str, *, keys: tuple[str, ...]) -> list[dict[str, object]]:
    value = _artifact_json(context, artifact_id)
    if value is None:
        return []
    for key in keys:
        items = value.get(key)
        if isinstance(items, list):
            return [dict(item) for item in items if isinstance(item, Mapping)]
    if isinstance(value.get("schema_version"), int):
        return [value]
    return []


def _require_document(value: dict[str, Any], phase: str) -> None:
    if value.get("schema_version") != 1 or value.get("phase") != phase:
        raise BundleValidationError(f"{phase} document version or phase is invalid")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BundleValidationError(f"{field} must be a nonempty string")
    return value.strip()


def _nonempty_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BundleValidationError(f"{field} must be nonempty")
    return value.strip()


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise BundleValidationError(f"{field} must be a list")
    return value


def _object_list(value: object, field: str, *, allow_empty: bool = True) -> list[Mapping[str, object]]:
    items = _list(value, field)
    if not allow_empty and not items:
        raise BundleValidationError(f"{field} must not be empty")
    result: list[Mapping[str, object]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise BundleValidationError(f"{field} entries must be objects")
        result.append(item)
    return result


def _string_list(value: object, field: str, *, allow_empty: bool = True) -> list[str]:
    items = _list(value, field)
    if not allow_empty and not items:
        raise BundleValidationError(f"{field} must not be empty")
    result: list[str] = []
    for item in items:
        result.append(_text(item, field))
    return result
