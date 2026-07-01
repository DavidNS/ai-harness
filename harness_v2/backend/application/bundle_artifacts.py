"""Shared bundle artifact and worker-step helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable

from harness_v2.backend.application.worker_service import WorkerTaskRequest, WorkerTaskService
from harness_v2.backend.domain.lifecycle import PhaseName
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactNotFoundError, ArtifactStorePort
from harness_v2.backend.ports.model_provider import (
    ModelSelection,
    TimeoutPolicy,
    TruncationPolicy,
)

JsonValidator = Callable[[dict[str, Any]], None]
JsonBuilder = Callable[[], dict[str, Any]]
TextValidator = Callable[[str], None]
TextBuilder = Callable[[], str]


class BundleValidationError(ValueError):
    """Raised when a bundle artifact, worker result, or validation step fails."""


@dataclass(frozen=True, slots=True)
class BundleRuntimeConfig:
    working_directory: Path
    model: ModelSelection = ModelSelection("scripted", "v2-sdd")
    timeout: TimeoutPolicy = TimeoutPolicy(30)
    truncation: TruncationPolicy = TruncationPolicy(100_000)
    allow_repository_mutation: bool = False
    tdd_command_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "working_directory", Path(self.working_directory))
        if not isinstance(self.allow_repository_mutation, bool):
            raise TypeError("allow_repository_mutation must be bool")
        if isinstance(self.tdd_command_timeout_seconds, bool) or self.tdd_command_timeout_seconds <= 0:
            raise ValueError("tdd_command_timeout_seconds must be positive")


class BundleArtifactGateway:
    def __init__(
        self,
        artifact_store: ArtifactStorePort,
        worker_service: WorkerTaskService,
        runtime: BundleRuntimeConfig,
    ) -> None:
        self._artifact_store = artifact_store
        self._worker_service = worker_service
        self._runtime = runtime

    def read_json(self, run_id: str, artifact_id: str) -> dict[str, Any] | None:
        content = self._read(run_id, artifact_id)
        if content is None:
            return None
        try:
            value = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise BundleValidationError(f"artifact {artifact_id} is not valid JSON") from exc
        if not isinstance(value, dict):
            raise BundleValidationError(f"artifact {artifact_id} must contain a JSON object")
        return value

    def write_json(self, run_id: str, artifact_id: str, value: dict[str, Any]) -> None:
        content = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")
        self._artifact_store.write(run_id, artifact_id, content)

    def read_text(self, run_id: str, artifact_id: str) -> str | None:
        content = self._read(run_id, artifact_id)
        return None if content is None else content.decode("utf-8")

    def write_text(self, run_id: str, artifact_id: str, value: str) -> None:
        self._artifact_store.write(run_id, artifact_id, value.encode("utf-8"))

    def ensure_controller_json(
        self,
        run_id: str,
        artifact_id: str,
        builder: JsonBuilder,
        validator: JsonValidator,
    ) -> dict[str, Any]:
        existing = self.read_json(run_id, artifact_id)
        if existing is not None:
            validator(existing)
            return existing
        value = builder()
        validator(value)
        self.write_json(run_id, artifact_id, value)
        return value

    def ensure_controller_text(
        self,
        run_id: str,
        artifact_id: str,
        builder: TextBuilder,
        validator: TextValidator,
    ) -> str:
        existing = self.read_text(run_id, artifact_id)
        if existing is not None:
            validator(existing)
            return existing
        value = builder()
        validator(value)
        self.write_text(run_id, artifact_id, value)
        return value

    def ensure_worker_json(
        self,
        run: RunRecord,
        phase: PhaseName,
        task_id: str,
        artifact_id: str,
        inputs: dict[str, Any],
        validator: JsonValidator,
    ) -> dict[str, Any]:
        existing = self.read_json(run.run_id, artifact_id)
        if existing is not None:
            validator(existing)
            return existing
        stdout = self._worker_stdout(run, phase, task_id, inputs)
        value = loads_json(stdout, task_id)
        validator(value)
        self.write_json(run.run_id, artifact_id, value)
        return value

    def ensure_worker_text(
        self,
        run: RunRecord,
        phase: PhaseName,
        task_id: str,
        artifact_id: str,
        inputs: dict[str, Any],
        validator: TextValidator,
    ) -> str:
        existing = self.read_text(run.run_id, artifact_id)
        if existing is not None:
            validator(existing)
            return existing
        value = self._worker_stdout(run, phase, task_id, inputs)
        validator(value)
        self.write_text(run.run_id, artifact_id, value)
        return value


    def run_worker_text(
        self,
        run: RunRecord,
        phase: PhaseName,
        task_id: str,
        inputs: dict[str, Any],
    ) -> str:
        return self._worker_stdout(run, phase, task_id, inputs)

    def _worker_stdout(self, run: RunRecord, phase: PhaseName, task_id: str, inputs: dict[str, Any]) -> str:
        result = self._worker_service.execute(
            WorkerTaskRequest(
                run_id=run.run_id,
                phase=phase,
                task_id=task_id,
                inputs=inputs,
                working_directory=self._runtime.working_directory,
                model=self._runtime.model,
                timeout=self._runtime.timeout,
                truncation=self._runtime.truncation,
            )
        )
        raw = self.read_json(run.run_id, result.result_artifact_id)
        if raw is None:
            raise BundleValidationError(f"worker result artifact missing for {task_id}")
        if not result.provider_succeeded:
            raise BundleValidationError(f"worker {task_id} failed")
        if result.truncated:
            raise BundleValidationError(f"worker {task_id} output was truncated")
        stdout = raw.get("stdout")
        if not isinstance(stdout, str):
            raise BundleValidationError(f"worker {task_id} result missing stdout")
        return stdout

    def _read(self, run_id: str, artifact_id: str) -> bytes | None:
        try:
            return self._artifact_store.read(run_id, artifact_id)
        except ArtifactNotFoundError:
            return None


def loads_json(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BundleValidationError(f"{label} output is not JSON") from exc
    if not isinstance(value, dict):
        raise BundleValidationError(f"{label} output must be a JSON object")
    return value
