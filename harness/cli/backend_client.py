"""Synchronous backend client for the launcher UI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


RunBackend = Callable[[list[str]], int]


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
