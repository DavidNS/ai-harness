"""Fake CI adapter for v2 tests."""

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
        return dict(self.signals_payload)
