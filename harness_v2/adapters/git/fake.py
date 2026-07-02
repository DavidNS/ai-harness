"""Fake Git adapters for v2 tests."""

from __future__ import annotations

from harness_v2.backend.ports.git import GitPort, GitRunRequest, GitRunResult


class FakeGitAdapter(GitPort):
    def __init__(self, result: GitRunResult | None = None) -> None:
        self.result = result or GitRunResult(
            is_git_repository=True,
            current_branch="main",
            head="abc123",
            origin_main="abc123",
            branch_mode="current",
        )
        self.requests: list[GitRunRequest] = []

    def prepare_run(self, request: GitRunRequest) -> GitRunResult:
        self.requests.append(request)
        return GitRunResult(
            is_git_repository=self.result.is_git_repository,
            current_branch=self.result.current_branch,
            head=self.result.head,
            origin_url=self.result.origin_url,
            origin_main=self.result.origin_main,
            dirty=self.result.dirty,
            branch_mode=request.branch_mode,
            created_branch=self.result.created_branch,
            branch_base_ref=self.result.branch_base_ref,
            warnings=self.result.warnings,
        )
