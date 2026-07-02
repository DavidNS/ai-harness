"""Git adapter for release lifecycle context."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from harness_v2.backend.ports.git import GitPort, GitRunRequest, GitRunResult


class GitCommandAdapter(GitPort):
    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        if isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds

    def prepare_run(self, request: GitRunRequest) -> GitRunResult:
        repository = request.repository.resolve()
        metadata = self._metadata(repository, branch_mode=request.branch_mode)
        if request.branch_mode in {"off", "current"} or not metadata.is_git_repository:
            return metadata
        warnings = list(metadata.warnings)
        if metadata.dirty:
            warnings.append("Per-run git branch was skipped because the worktree has uncommitted changes.")
            return self._replace(metadata, warnings=tuple(warnings))
        branch = _run_branch_name(request.run_id, request.request)
        base_ref = "HEAD"
        if request.branch_mode == "create-from-main":
            base_ref = self._main_branch_ref(repository) or ""
            if not base_ref:
                warnings.append("Per-run git branch was skipped because main or origin/main could not be resolved.")
                return self._replace(metadata, warnings=tuple(warnings))
        checked_out = self._git(repository, "checkout", "-b", branch, base_ref)
        if checked_out is None:
            warnings.append(f"Per-run branch {branch} could not be checked out from {base_ref}.")
            return self._replace(metadata, branch_base_ref=base_ref, warnings=tuple(warnings))
        pushed = self._git(repository, "push", "-u", "origin", branch)
        if pushed is None:
            warnings.append(f"Per-run remote branch {branch} could not be pushed to origin.")
        return self._replace(
            metadata,
            current_branch=branch,
            created_branch=branch,
            branch_base_ref=base_ref,
            warnings=tuple(warnings),
        )

    def _metadata(self, repository: Path, *, branch_mode: str) -> GitRunResult:
        if self._git(repository, "rev-parse", "--is-inside-work-tree") != "true":
            return GitRunResult(
                is_git_repository=False,
                branch_mode=branch_mode,
                warnings=("Repository is not a git worktree.",),
            )
        origin_main = self._git(repository, "rev-parse", "--verify", "origin/main")
        warnings: list[str] = []
        if origin_main is None:
            warnings.append("origin/main is not available locally; remote sync freshness cannot be verified without fetching.")
        return GitRunResult(
            is_git_repository=True,
            current_branch=self._git(repository, "branch", "--show-current") or "",
            head=self._git(repository, "rev-parse", "HEAD"),
            origin_url=self._git(repository, "remote", "get-url", "origin"),
            origin_main=origin_main,
            dirty=self._dirty_excluding_harness_runtime(repository),
            branch_mode=branch_mode,
            warnings=tuple(warnings),
        )

    def _dirty_excluding_harness_runtime(self, repository: Path) -> bool:
        status = self._git(repository, "status", "--porcelain", "--untracked-files=all")
        if not status:
            return False
        for line in status.splitlines():
            path = line[3:].strip() if len(line) > 3 else line.strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip()
            path = path.strip('"')
            if not (path == ".ai-harness" or path.startswith(".ai-harness/")):
                return True
        return False

    def _main_branch_ref(self, repository: Path) -> str | None:
        if self._git(repository, "rev-parse", "--verify", "main") is not None:
            return "main"
        if self._git(repository, "rev-parse", "--verify", "origin/main") is not None:
            return "origin/main"
        return None

    def _git(self, repository: Path, *args: str) -> str | None:
        try:
            completed = subprocess.run(
                ["git", "-C", str(repository), *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except Exception:
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout.strip()

    @staticmethod
    def _replace(result: GitRunResult, **changes: object) -> GitRunResult:
        values = {
            "is_git_repository": result.is_git_repository,
            "current_branch": result.current_branch,
            "head": result.head,
            "origin_url": result.origin_url,
            "origin_main": result.origin_main,
            "dirty": result.dirty,
            "branch_mode": result.branch_mode,
            "created_branch": result.created_branch,
            "branch_base_ref": result.branch_base_ref,
            "warnings": result.warnings,
        }
        values.update(changes)
        return GitRunResult(**values)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:32] or "run"


def _run_branch_name(run_id: str, request: str) -> str:
    return f"aih/v2/{run_id[:12]}-{_slug(request)}"
