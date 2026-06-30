"""Generic one-shot repair support for phase validation failures."""

from __future__ import annotations

from typing import Callable, Mapping, Protocol

from ..contracts.limits import LEARNING as _LEARNING_LIMITS
from ..phases import PhaseRepairExhaustedError, PhaseValidationError, get_phase

_GENERIC_REPAIR_PHASES = frozenset({
    "explore", "explore_request_profile", "explore_evidence_digest", "explore_delta",
    "explore_outcome_synthesis", "purpose", "spec", "design", "tasks", "test", "implement", "review",
    "explorer", "explorer_intake", "explorer_discovery",
    "explorer_decision", "explorer_artifact", "explorer_distill",
    "explorer_review", "knowledge_synthesis", "knowledge_review",
})
_PHASE_REPAIR_REJECTED_LIMIT = _LEARNING_LIMITS.rejected
_TASKS_CONTRACT_SUMMARY = {
    "format": "json",
    "required_document_fields": ["schema_version", "phase", "tasks"],
    "optional_document_fields": ["deferrals"],
    "required_task_fields": [
        "id", "title", "depends_on", "acceptance_criteria", "touched_paths",
        "focused_tests", "broader_tests", "status",
    ],
    "optional_task_fields": ["source_artifacts"],
    "required_values": {"schema_version": 1, "phase": "tasks", "task.status": "pending"},
    "command_shape": "focused_tests and broader_tests contain argument-vector arrays of nonempty strings",
}



def _compact_sequence(value: object, limit: int) -> object:
    if isinstance(value, list):
        return value[:limit]
    if isinstance(value, tuple):
        return list(value[:limit])
    return value


def _compact_context_pack(value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    compact: dict[str, object] = {
        "schema_version": value.get("schema_version"),
        "kind": value.get("kind"),
        "request": value.get("request"),
        "profile": value.get("profile"),
        "ci_digest": value.get("ci_digest"),
        "git": value.get("git"),
        "explorer_scope": value.get("explorer_scope"),
    }
    compact["knowledge"] = _compact_sequence(value.get("knowledge", []), 3)
    compact["related_improvements"] = _compact_sequence(value.get("related_improvements", []), 5)
    compact["repository_observations"] = _compact_sequence(value.get("repository_observations", []), 8)
    if "evidence_request" in value:
        compact["evidence_request"] = value.get("evidence_request")
    return {key: item for key, item in compact.items() if item not in (None, [], {})}


def _compact_repair_inputs(inputs: Mapping[str, object]) -> dict[str, object]:
    compact = dict(inputs)
    if "context_pack" in compact:
        compact["context_pack"] = _compact_context_pack(compact["context_pack"])
    if "controller_evidence" in compact:
        compact["controller_evidence"] = _compact_sequence(compact["controller_evidence"], 8)
    if "evidence" in compact:
        compact["evidence"] = _compact_sequence(compact["evidence"], 16)
    return compact

class _ArtifactRecorder(Protocol):
    def write_json(self, path: str, data: object) -> None:
        ...


class _StateRecorder(Protocol):
    def load(self) -> object:
        ...

    def record_artifact(self, path: str, phase: str) -> None:
        ...


def phase_contract_summary(definition) -> dict[str, object]:
    """Return a structured contract summary for error reporting."""
    summary: dict[str, object] = {"artifact": definition.artifact}

    if definition.name == "explore_outcome_synthesis":
        summary.update({
            "format": "json",
            "required_document_fields": [
                "schema_version", "kind", "status", "normalized_request",
                "triage", "entries",
            ],
            "optional_document_fields": ["clarification_questions", "operational_blockers"],
            "forbidden_document_fields": ["evidence", "exploration_map"],
            "required_values": {"schema_version": 1, "kind": "explore_outcome_synthesis"},
            "status": ["ready_for_purpose", "needs_clarification", "problem_gathering_info"],
            "classification": ["improvement", "limitation", "bullshit"],
            "note": "Controller injects evidence and exploration_map into the final explore_outcome_bundle.",
        })
        return summary
    if definition.name == "purpose":
        summary.update({
            "format": "json",
            "required_document_fields": [
                "schema_version", "kind", "summary", "selected_entries", "implementation_mode",
                "problem", "scope", "approach", "structural_work", "exclusions",
                "acceptance_outline", "evidence_refs",
            ],
            "required_values": {"schema_version": 1, "kind": "purpose_bundle"},
            "implementation_mode": [
                "direct_patch", "patch_with_local_refactor", "refactor_first_then_patch",
                "security_patch", "existing_functionality", "documentation_only", "blocked",
            ],
        })
        return summary
    if definition.name.startswith("explore_") or definition.name == "explore":
        summary.update({
            "format": "json",
            "artifact": definition.artifact,
            "evidence_item_fields": ["id", "kind", "claim", "status", "confidence", "severity", "sources"],
            "source_requires_one_of": ["path", "artifact", "url", "description"],
            "allowed_source_types": ["file", "artifact", "git", "gitlab", "web", "knowledge", "ci"],
        })
        return summary
    if definition.name == "tasks":
        summary.update(_TASKS_CONTRACT_SUMMARY)
        return summary
    if definition.name in {"learning", "knowledge_synthesis"}:
        summary.update({
            "format": "json",
            "required_document_fields": ["schema_version", "phase", "proposal_manifest", "proposed_claims"],
            "optional_document_fields": ["proposed_relations"],
            "required_values": {"schema_version": 1, "phase": "learning"},
            "proposal_manifest_fields": ["schema_version", "proposal_id", "summary", "source_artifacts"],
            "claim_required_fields": [
                "id", "domain", "subjects", "files", "symbols", "claim_type", "text",
                "status", "evidence", "valid_from", "valid_until", "last_verified",
            ],
            "claim_id_format": "lowercase knowledge-source ID, e.g. claim.cli-ui.001; discovery IDs like C1 are invalid",
            "evidence_required_fields": ["type", "file|artifact|url"],
            "relation_required_fields": ["id", "domain", "source", "target", "relation_type", "status", "evidence"],
            "supported_statuses": ["active", "deprecated", "superseded", "conflicted", "unverified", "stale"],
        })
        return summary
    if definition.name == "knowledge_review":
        summary.update({
            "format": "json",
            "required_document_fields": ["schema_version", "phase", "proposal_id", "claim_reviews"],
            "optional_document_fields": ["relation_reviews"],
            "required_values": {"schema_version": 1, "phase": "knowledge_review"},
            "claim_review_fields": ["claim_id", "decision", "reason", "suggested_text", "status_override", "metadata"],
            "supported_decisions": ["accept", "downgrade", "reject_for_repair", "fail_review"],
        })
        return summary
    summary.update({
        "format": "markdown",
        "required_heading": definition.heading,
        "required_sections": list(definition.sections),
    })
    if definition.name == "review":
        summary["verdict"] = "APPROVE or REQUEST_CHANGES exactly"
    return summary


class PhaseRepairRunner:
    """Own generic phase repair retries without owning phase execution."""

    def __init__(
        self,
        *,
        invoke: Callable[..., str],
        artifacts: _ArtifactRecorder,
        state: _StateRecorder,
        progress: Callable[[str], None],
        clip_text: Callable[[str, int], str],
    ) -> None:
        self._invoke = invoke
        self._artifacts = artifacts
        self._state = state
        self._progress = progress
        self._clip_text = clip_text

    def _generic_repair_payload(self, name: str, exc: PhaseValidationError) -> dict[str, object]:
        definition = get_phase(name)
        contract = phase_contract_summary(definition)
        payload: dict[str, object] = {
            "phase": name,
            "artifact": definition.artifact,
            "validation_error": str(exc),
            "required_contract": contract,
            "original_input_keys": list(definition.required_inputs),
            "rejected_candidate_excerpt": self._clip_text(
                getattr(exc, "candidate_stdout", ""),
                _PHASE_REPAIR_REJECTED_LIMIT,
            ),
        }
        job_id = getattr(exc, "candidate_job_id", None)
        if job_id is not None:
            payload["rejected_job_result"] = f"jobs/{job_id}/result.json"
        if contract.get("required_heading") is not None:
            payload["required_heading"] = contract["required_heading"]
        if contract.get("required_sections"):
            payload["required_sections"] = contract["required_sections"]
        if contract.get("format") == "json":
            payload["json_schema_summary"] = {key: value for key, value in contract.items() if key != "artifact"}
        control_contract = getattr(exc, "control_output_contract", None)
        if control_contract is not None:
            payload["control_output_contract"] = dict(control_contract)
        return payload

    def _record_phase_validation_exhaustion(
        self,
        name: str,
        first: PhaseValidationError,
        second: PhaseValidationError,
    ) -> None:
        definition = get_phase(name)
        attempts = []
        for label, exc in (("original", first), ("repair", second)):
            job_id = getattr(exc, "candidate_job_id", None)
            attempts.append({
                "attempt": label,
                "job_result": None if job_id is None else f"jobs/{job_id}/result.json",
                "validation_error": str(exc),
            })
        artifact = f"validation/{name}-failure.json"
        self._artifacts.write_json(artifact, {
            "schema_version": 1,
            "phase": name,
            "artifact": definition.artifact,
            "contract": phase_contract_summary(definition),
            "attempts": attempts,
        })
        current_phase = getattr(self._state.load(), "current_phase")
        self._state.record_artifact(artifact, current_phase)

    def invoke(self, name: str, inputs: Mapping[str, object], *, parse_control: bool = True) -> str:
        if name not in _GENERIC_REPAIR_PHASES:
            return self._invoke(name, inputs, parse_control=parse_control)
        try:
            return self._invoke(name, inputs, parse_control=parse_control)
        except PhaseValidationError as first:
            repair = self._generic_repair_payload(name, first)
            self._progress(f"{name.title()} candidate failed contract validation; invoking one repair attempt")
            try:
                return self._invoke(name, _compact_repair_inputs(inputs), repair=repair, parse_control=parse_control)
            except PhaseValidationError as second:
                self._record_phase_validation_exhaustion(name, first, second)
                raise PhaseRepairExhaustedError(f"{name} repair exhausted: {second}") from second
