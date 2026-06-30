"""Synchronous backend client for the launcher UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


RunBackend = Callable[[list[str]], int]


@dataclass(frozen=True, slots=True)
class StartBackendRequest:
    provider: str
    model: str | None = None
    reasoning_effort: str | None = None
    github_ci_mode: str | None = None
    branch: str | None = None
    route: str | None = None
    flow: str | None = None
    source_run: str | None = None
    prompt_file: Path | None = None


@dataclass(frozen=True, slots=True)
class ResumeBackendRequest:
    provider: str
    run_id: str
    model: str | None = None
    reasoning_effort: str | None = None
    github_ci_mode: str | None = None
    answer: str | None = None
    selected_option: str | None = None


class BackendClient:
    """Small command builder around harness/run.py.

    The client is intentionally synchronous in this iteration. It centralizes
    the backend argument shape so the console controller does not need to know
    each backend flag for simple commands.
    """

    def __init__(self, repository: Path, run_backend: RunBackend) -> None:
        self._repository = repository
        self._run_backend = run_backend

    @property
    def repository(self) -> str:
        return str(self._repository.resolve())

    def run(self, args: list[str]) -> int:
        return self._run_backend(args)

    def status(self) -> int:
        return self.run(["--cwd", self.repository, "--status"])

    def runs(self) -> int:
        return self.run(["--cwd", self.repository, "--show-runs"])

    def archive(self, run_id: str) -> int:
        return self.run(["--cwd", self.repository, "--archive", run_id])

    def start_args(self, request: StartBackendRequest) -> list[str]:
        backend = ["--cwd", self.repository, "--provider", request.provider, "--activated"]
        if request.model:
            backend.extend(["--model", request.model])
        if request.reasoning_effort:
            backend.extend(["--reasoning-effort", request.reasoning_effort])
        if request.github_ci_mode:
            backend.extend(["--github-ci-mode", request.github_ci_mode])
        if request.prompt_file is not None:
            backend.extend(["--prompt-file", str(request.prompt_file.expanduser())])
        if request.branch:
            backend.extend(["--branch", request.branch])
        if request.route:
            backend.extend(["--route", request.route])
        if request.flow:
            backend.extend(["--flow", request.flow])
        if request.source_run:
            backend.extend(["--from-run", request.source_run])
        return backend

    def resume_args(self, request: ResumeBackendRequest) -> list[str]:
        backend = ["--cwd", self.repository, "--provider", request.provider, "--activated", "--resume", request.run_id]
        if request.model:
            backend.extend(["--model", request.model])
        if request.reasoning_effort:
            backend.extend(["--reasoning-effort", request.reasoning_effort])
        if request.github_ci_mode:
            backend.extend(["--github-ci-mode", request.github_ci_mode])
        if request.answer is not None:
            backend.extend(["--answer", request.answer])
        if request.selected_option is not None:
            backend.extend(["--selected-option", request.selected_option])
        return backend

    def install_ci(self, *, target: str | None = None, force: bool = False) -> int:
        backend = ["--cwd", self.repository, "--install-ci"]
        if target:
            backend.extend(["--ci-target", target])
        if force:
            backend.append("--force")
        return self.run(backend)

    def install_packages(
        self,
        *,
        optionals: list[str],
        all_optional: bool = False,
        dry_install: bool = False,
    ) -> int:
        backend = ["--cwd", self.repository, "--install-packages"]
        for optional in optionals:
            backend.extend(["--package", optional])
        if all_optional:
            backend.append("--all-packages")
        if dry_install:
            backend.append("--dry-install")
        return self.run(backend)

    def raw(self, args: list[str]) -> int:
        return self.run(args)
