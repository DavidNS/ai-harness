"""Application service for release lifecycle context artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol

from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactNotFoundError, ArtifactStorePort
from harness_v2.backend.ports.ci import CIPort, CiInstallRequest, CiInstallResult, CiSignalRequest
from harness_v2.backend.ports.git import GitPort, GitRunRequest


class ReleaseContextPort(Protocol):
    def ensure_initial_context(self, run: RunRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class ReleaseRuntimeConfig:
    working_directory: Path
    branch_mode: str = "current"
    ci_mode: str = "baseline"
    refresh_existing: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "working_directory", Path(self.working_directory))
        if self.branch_mode not in {"off", "current", "create", "create-from-main"}:
            raise ValueError("branch_mode must be off, current, create, or create-from-main")
        if self.ci_mode not in {"off", "baseline", "branch"}:
            raise ValueError("ci_mode must be off, baseline, or branch")
        if not isinstance(self.refresh_existing, bool):
            raise TypeError("refresh_existing must be bool")


class ReleaseContextService(ReleaseContextPort):
    def __init__(
        self,
        artifact_store: ArtifactStorePort,
        git: GitPort,
        ci: CIPort,
        config: ReleaseRuntimeConfig,
    ) -> None:
        self._artifact_store = artifact_store
        self._git = git
        self._ci = ci
        self._config = config

    def ensure_initial_context(self, run: RunRecord) -> None:
        repository = self._config.working_directory
        if self._should_write(run.run_id, "ci-status.json"):
            self._write_json(run.run_id, "ci-status.json", self._ci.status(repository))
        if self._should_write(run.run_id, "git-run.json"):
            git_result = self._git.prepare_run(
                GitRunRequest(
                    repository=repository,
                    run_id=run.run_id,
                    request=run.request,
                    branch_mode=self._config.branch_mode,
                )
            )
            self._write_json(run.run_id, "git-run.json", git_result.to_artifact())
        if self._should_write(run.run_id, "ci-signals.json"):
            signals = self._ci.collect_signals(CiSignalRequest(repository=repository, ci_mode=self._config.ci_mode))
            self._write_json(run.run_id, "ci-signals.json", signals)

    def install_ci_templates(self, target: str, *, force: bool = False) -> CiInstallResult:
        return self._ci.install_templates(
            CiInstallRequest(repository=self._config.working_directory, target=target, force=force)
        )

    def _should_write(self, run_id: str, artifact_id: str) -> bool:
        if self._config.refresh_existing:
            return True
        try:
            self._artifact_store.read(run_id, artifact_id)
        except ArtifactNotFoundError:
            return True
        return False

    def _write_json(self, run_id: str, artifact_id: str, value: dict[str, object]) -> None:
        content = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")
        self._artifact_store.write(run_id, artifact_id, content)
