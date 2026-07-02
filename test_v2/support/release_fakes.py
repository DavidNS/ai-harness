"""Release-port test doubles for v2."""

from __future__ import annotations

from pathlib import Path

from harness_v2.backend.ports.ci import CIPort, CiInstallRequest, CiInstallResult, CiSignalRequest


class FakeCIAdapter(CIPort):
    def __init__(
        self,
        *,
        status_payload: dict[str, object] | None = None,
        signals_payload: dict[str, object] | None = None,
        install_result: CiInstallResult | None = None,
    ) -> None:
        self.status_payload = status_payload or {"schema_version": 1, "providers": [], "warnings": []}
        self.signals_payload = signals_payload or {
            "schema_version": 2,
            "kind": "ai_harness_ci_signals",
            "status": "ready",
            "providers": {"fake": {"status": "ready", "signal_count": 0}},
            "summary": {"status": "ready", "signal_count": 0, "provider_count": 1},
            "warnings": [],
            "path_index": [],
            "signals": [],
        }
        self.install_result = install_result or CiInstallResult(installed=("ci.yml",))
        self.status_repositories: list[Path] = []
        self.signal_requests: list[CiSignalRequest] = []
        self.install_requests: list[CiInstallRequest] = []

    def install_templates(self, request: CiInstallRequest) -> CiInstallResult:
        self.install_requests.append(request)
        return self.install_result

    def status(self, repository: Path) -> dict[str, object]:
        self.status_repositories.append(Path(repository))
        return dict(self.status_payload)

    def collect_signals(self, request: CiSignalRequest) -> dict[str, object]:
        self.signal_requests.append(request)
        payload = dict(self.signals_payload)
        payload.setdefault("scope", request.scope)
        payload.setdefault("ref", request.ref)
        return payload


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
