"""Shared bundle artifact and worker-step helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable

from harness_v2.backend.application.worker_service import WorkerTaskRequest, WorkerTaskService
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactNotFoundError, ArtifactStorePort
from harness_v2.backend.ports.model_provider import (
    ModelSelection,
    TimeoutPolicy,
    TruncationPolicy,
)
from harness_v2.backend.ports.repository import RepositoryRollbackPort, RepositorySnapshotPort
from harness_v2.backend.ports.tool_runner import ToolRunnerPort

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
    tdd_max_attempts: int = 3
    repository: RepositorySnapshotPort | None = None
    rollback: RepositoryRollbackPort | None = None
    tool_runner: ToolRunnerPort | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "working_directory", Path(self.working_directory))
        if not isinstance(self.allow_repository_mutation, bool):
            raise TypeError("allow_repository_mutation must be bool")
        if isinstance(self.tdd_command_timeout_seconds, bool) or self.tdd_command_timeout_seconds <= 0:
            raise ValueError("tdd_command_timeout_seconds must be positive")
        if isinstance(self.tdd_max_attempts, bool) or self.tdd_max_attempts <= 0:
            raise ValueError("tdd_max_attempts must be positive")


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

    def list_artifacts(self, run_id: str) -> tuple[str, ...]:
        return tuple(item.artifact_id for item in self._artifact_store.list(run_id))

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
        bundle: BundleName,
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
        stdout = self._worker_stdout(run, bundle, phase, task_id, inputs)
        value = loads_json(stdout, task_id)
        validator(value)
        self.write_json(run.run_id, artifact_id, value)
        return value

    def ensure_worker_json_candidate(
        self,
        run: RunRecord,
        bundle: BundleName,
        phase: PhaseName,
        task_id: str,
        artifact_id: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        existing = self.read_text(run.run_id, artifact_id)
        if existing is not None:
            try:
                return loads_json(existing, task_id)
            except BundleValidationError:
                return None
        stdout = self._worker_stdout(run, bundle, phase, task_id, inputs)
        try:
            value = loads_json(stdout, task_id)
        except BundleValidationError:
            self.write_text(run.run_id, artifact_id, stdout)
            return None
        self.write_json(run.run_id, artifact_id, value)
        return value

    def ensure_worker_json_with_repair(
        self,
        run: RunRecord,
        bundle: BundleName,
        phase: PhaseName,
        task_id: str,
        artifact_id: str,
        inputs: dict[str, Any],
        validator: JsonValidator,
        *,
        repair_task_id: str = "artifact_delta_repair",
        max_repairs: int = 2,
        schema_label: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(max_repairs, bool) or max_repairs < 0:
            raise ValueError("max_repairs must be non-negative")
        existing = self.read_json(run.run_id, artifact_id)
        if existing is not None:
            validator(existing)
            return existing

        stdout = self._worker_stdout(run, bundle, phase, task_id, inputs)
        value, error = _load_and_validate_json(stdout, task_id, validator)
        if error is None and value is not None:
            self.write_json(run.run_id, artifact_id, value)
            return value

        current = value
        raw_stdout = stdout
        attempts: list[dict[str, Any]] = []
        for attempt in range(1, max_repairs + 1):
            repair_inputs = {
                "target_artifact": artifact_id,
                "original_task_id": task_id,
                "original_inputs": inputs,
                "current_artifact": current,
                "raw_stdout": raw_stdout,
                "validation_error": error,
                "schema_label": schema_label or artifact_id,
                "repair_attempt": attempt,
            }
            repair_stdout = self._worker_stdout(run, bundle, phase, repair_task_id, repair_inputs)
            attempt_record: dict[str, Any] = {"attempt": attempt, "validation_error": error}
            try:
                from harness_v2.backend.application.json_delta import apply_json_artifact_delta

                delta = loads_json(repair_stdout, repair_task_id)
                attempt_record["delta"] = delta
                repaired = apply_json_artifact_delta(delta, target_artifact=artifact_id, current_artifact=current)
            except Exception as exc:
                error = str(exc) or type(exc).__name__
                attempt_record["repair_error"] = error
                attempts.append(attempt_record)
                self._write_repair_diagnostic(run, artifact_id, attempts)
                continue
            try:
                validator(repaired)
            except Exception as exc:
                current = repaired
                error = str(exc) or type(exc).__name__
                attempt_record["repair_error"] = error
                attempts.append(attempt_record)
                self._write_repair_diagnostic(run, artifact_id, attempts)
                continue
            attempt_record["status"] = "repaired"
            attempts.append(attempt_record)
            self.write_json(run.run_id, artifact_id, repaired)
            self._write_repair_diagnostic(run, artifact_id, attempts)
            return repaired

        self._write_repair_diagnostic(run, artifact_id, attempts)
        raise BundleValidationError(f"artifact {artifact_id} could not be repaired: {error}")

    def ensure_worker_text(
        self,
        run: RunRecord,
        bundle: BundleName,
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
        value = self._worker_stdout(run, bundle, phase, task_id, inputs)
        validator(value)
        self.write_text(run.run_id, artifact_id, value)
        return value


    def _write_repair_diagnostic(self, run: RunRecord, artifact_id: str, attempts: list[dict[str, Any]]) -> None:
        safe_step = _safe_step_id(_require_current_step_id(run))
        diagnostic_id = f"validation/{safe_step}-{_safe_artifact_id(artifact_id)}-repair.json"
        self.write_json(run.run_id, diagnostic_id, {"schema_version": 1, "artifact_id": artifact_id, "attempts": attempts})


    def run_worker_text(
        self,
        run: RunRecord,
        bundle: BundleName,
        phase: PhaseName,
        task_id: str,
        inputs: dict[str, Any],
    ) -> str:
        return self._worker_stdout(run, bundle, phase, task_id, inputs)

    def _worker_stdout(self, run: RunRecord, bundle: BundleName, phase: PhaseName, task_id: str, inputs: dict[str, Any]) -> str:
        result = self._worker_service.execute(
            WorkerTaskRequest(
                run_id=run.run_id,
                bundle=bundle,
                phase=phase,
                step_id=_require_current_step_id(run),
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


def _load_and_validate_json(text: str, label: str, validator: JsonValidator) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = loads_json(text, label)
    except Exception as exc:
        return None, str(exc) or type(exc).__name__
    try:
        validator(value)
    except Exception as exc:
        return value, str(exc) or type(exc).__name__
    return value, None


def _safe_step_id(step_id: str) -> str:
    return step_id.replace(":", "_")


def _safe_artifact_id(artifact_id: str) -> str:
    return artifact_id.replace("/", "_").replace(":", "_")


def _require_current_step_id(run: RunRecord) -> str:
    if run.current_step_id is None:
        raise BundleValidationError("worker task requires an active step")
    return run.current_step_id
