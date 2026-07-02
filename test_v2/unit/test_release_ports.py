from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from test_v2.support.release_fakes import FakeCIAdapter
from harness_v2.adapters.ci.local import LocalCIAdapter
from test_v2.support.release_fakes import FakeGitAdapter
from harness_v2.adapters.storage import InMemoryArtifactStore
from harness_v2.backend.application.release_context import ReleaseContextService, ReleaseRuntimeConfig
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.ci import CiInstallRequest, CiInstallResult, CiSignalRequest
from harness_v2.backend.ports.git import GitRunRequest, GitRunResult


class ReleasePortTests(unittest.TestCase):
    def test_git_and_ci_dtos_validate_modes_and_targets(self) -> None:
        GitRunRequest(Path.cwd(), "run-1", "Fix tests", "create-from-main")
        CiInstallRequest(Path.cwd(), "both", force=True)
        CiSignalRequest(Path.cwd(), "branch")

        with self.assertRaises(ValueError):
            GitRunRequest(Path.cwd(), "run-1", "Fix tests", "sideways")
        with self.assertRaises(ValueError):
            CiInstallRequest(Path.cwd(), "jenkins")
        with self.assertRaises(ValueError):
            CiSignalRequest(Path.cwd(), "always")

    def test_release_context_writes_initial_artifacts_once(self) -> None:
        artifacts = InMemoryArtifactStore()
        git = FakeGitAdapter(GitRunResult(is_git_repository=True, current_branch="main", head="abc123"))
        ci = FakeCIAdapter(
            status_payload={"schema_version": 1, "providers": [{"provider": "github"}], "warnings": []},
            signals_payload={"schema_version": 2, "status": "ready", "signals": [], "providers": {}, "summary": {}},
        )
        service = ReleaseContextService(
            artifacts,
            git,
            ci,
            ReleaseRuntimeConfig(Path.cwd(), branch_mode="current", ci_mode="baseline"),
        )
        run = RunRecord("run-1", "Fix tests", RunStatus.RUNNING, root_bundle=BundleName.EXPLORE_BUNDLE, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING)

        service.ensure_initial_context(run)
        service.ensure_initial_context(run)

        git_payload = json.loads(artifacts.read("run-1", "git-run.json"))
        ci_status = json.loads(artifacts.read("run-1", "ci-status.json"))
        ci_signals = json.loads(artifacts.read("run-1", "ci-signals.json"))
        self.assertEqual("abc123", git_payload["head"])
        self.assertEqual("github", ci_status["providers"][0]["provider"])
        self.assertEqual("ready", ci_signals["status"])
        self.assertEqual(1, len(git.requests))
        self.assertEqual(1, len(ci.status_repositories))
        self.assertEqual(1, len(ci.signal_requests))

    def test_release_context_installs_ci_through_ci_port(self) -> None:
        ci = FakeCIAdapter(install_result=CiInstallResult(installed=(".github/workflows/ai-harness-ci.yml",)))
        service = ReleaseContextService(InMemoryArtifactStore(), FakeGitAdapter(), ci, ReleaseRuntimeConfig(Path.cwd()))

        result = service.install_ci_templates("github", force=True)

        self.assertEqual((".github/workflows/ai-harness-ci.yml",), result.installed)
        self.assertEqual("github", ci.install_requests[0].target)
        self.assertTrue(ci.install_requests[0].force)

    def test_local_ci_adapter_installs_github_template_and_reports_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            adapter = LocalCIAdapter()

            result = adapter.install_templates(CiInstallRequest(repository, "github"))
            status = adapter.status(repository)

            self.assertEqual((".github/workflows/ai-harness-ci.yml",), result.installed)
            self.assertEqual("github", status["providers"][0]["provider"])
            self.assertTrue(status["providers"][0]["managed"])
            self.assertTrue(status["providers"][0]["in_sync"])


if __name__ == "__main__":
    unittest.main()
