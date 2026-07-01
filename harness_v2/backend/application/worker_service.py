"""Application service for bounded worker tasks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from harness_v2.backend.application.contracts import InvalidRunStateError, RunNotFoundError
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus
from harness_v2.backend.ports.artifact_store import ArtifactStorePort
from harness_v2.backend.ports.model_provider import (
    CapabilityProjection,
    ModelProviderPort,
    ModelProviderRequest,
    ModelProviderResult,
    ModelSelection,
    TimeoutPolicy,
    TruncationPolicy,
)
from harness_v2.backend.ports.state_store import StateNotFoundError, StateStorePort


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _safe_segment(value: str, field: str) -> str:
    normalized = _require_text(value, field)
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        raise ValueError(f"{field} must be a single safe path segment")
    return normalized


@dataclass(frozen=True, slots=True)
class WorkerTaskRequest:
    run_id: str
    phase: str | PhaseName
    task_id: str
    prompt: str
    working_directory: Path
    model: ModelSelection
    capabilities: CapabilityProjection
    timeout: TimeoutPolicy = TimeoutPolicy()
    truncation: TruncationPolicy = TruncationPolicy()

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "phase", PhaseName(_require_text(self.phase, "phase")))
        object.__setattr__(self, "task_id", _safe_segment(self.task_id, "task_id"))
        object.__setattr__(self, "prompt", _require_text(self.prompt, "prompt"))
        object.__setattr__(self, "working_directory", Path(self.working_directory))
        if not isinstance(self.model, ModelSelection):
            raise TypeError("model must be ModelSelection")
        if not isinstance(self.capabilities, CapabilityProjection):
            raise TypeError("capabilities must be CapabilityProjection")
        if not isinstance(self.timeout, TimeoutPolicy):
            raise TypeError("timeout must be TimeoutPolicy")
        if not isinstance(self.truncation, TruncationPolicy):
            raise TypeError("truncation must be TruncationPolicy")


@dataclass(frozen=True, slots=True)
class WorkerTaskResult:
    run_id: str
    phase: str
    task_id: str
    request_artifact_id: str
    result_artifact_id: str
    provider_succeeded: bool
    timed_out: bool
    exit_code: int | None
    truncated: bool


class WorkerTaskService:
    """Run one bounded worker task and record request/result artifacts."""

    def __init__(
        self,
        state_store: StateStorePort,
        artifact_store: ArtifactStorePort,
        model_provider: ModelProviderPort,
    ) -> None:
        self._state_store = state_store
        self._artifact_store = artifact_store
        self._model_provider = model_provider

    def execute(self, command: WorkerTaskRequest) -> WorkerTaskResult:
        try:
            run = self._state_store.get(command.run_id)
        except StateNotFoundError as exc:
            raise RunNotFoundError(command.run_id) from exc
        if run.status is not RunStatus.RUNNING or run.current_phase is None:
            raise InvalidRunStateError(f"run {run.run_id} cannot request a worker task from {run.status.value}")
        if run.current_phase != command.phase:
            raise InvalidRunStateError(f"run {run.run_id} is in phase {run.current_phase.value}, not {command.phase.value}")

        provider_request = ModelProviderRequest(
            prompt=command.prompt,
            working_directory=command.working_directory,
            model=command.model,
            capabilities=command.capabilities,
            timeout=command.timeout,
            truncation=command.truncation,
        )
        request_artifact_id = _artifact_id(command.phase, command.task_id, "request.json")
        result_artifact_id = _artifact_id(command.phase, command.task_id, "result.json")
        self._artifact_store.write(run.run_id, request_artifact_id, _json_bytes(_request_payload(provider_request)))
        provider_result = self._model_provider.run(provider_request)
        self._artifact_store.write(run.run_id, result_artifact_id, _json_bytes(_result_payload(provider_result)))
        return WorkerTaskResult(
            run_id=run.run_id,
            phase=command.phase.value,
            task_id=command.task_id,
            request_artifact_id=request_artifact_id,
            result_artifact_id=result_artifact_id,
            provider_succeeded=provider_result.succeeded,
            timed_out=provider_result.timed_out,
            exit_code=provider_result.exit_code,
            truncated=provider_result.truncated,
        )


def _artifact_id(phase: PhaseName, task_id: str, filename: str) -> str:
    return f"workers/{phase.value}/{task_id}/{filename}"


def _json_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _request_payload(request: ModelProviderRequest) -> dict[str, object]:
    data = asdict(request)
    data["working_directory"] = str(request.working_directory)
    return data


def _result_payload(result: ModelProviderResult) -> dict[str, object]:
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "duration_seconds": result.duration_seconds,
        "timed_out": result.timed_out,
        "truncated": result.truncated,
        "provider_succeeded": result.succeeded,
    }
