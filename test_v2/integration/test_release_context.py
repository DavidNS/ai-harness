from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from harness_v2.adapters.storage import FileArtifactStore
from harness_v2.backend.application.contracts import InstallCiTemplates, ResumeRun, StartRun
from harness_v2.hosts.in_process.host import InProcessHost


class ReleaseContextIntegrationTests(unittest.TestCase):
    def test_in_process_explore_materializes_release_artifacts_for_context_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            repository = Path(directory) / "repo"
            repository.mkdir()
            host = InProcessHost(state_root=root, working_directory=repository, branch_mode="current", github_ci_mode="baseline")

            started = host.execute(StartRun("Fix tests", strategy="EXPLORE_BUNDLE"))
            resumed = host.execute(ResumeRun(started.run.run_id))

            artifacts = FileArtifactStore(root)
            git = json.loads(artifacts.read(started.run.run_id, "git-run.json"))
            ci_status = json.loads(artifacts.read(started.run.run_id, "ci-status.json"))
            ci_signals = json.loads(artifacts.read(started.run.run_id, "ci-signals.json"))
            context_pack = json.loads(artifacts.read(started.run.run_id, "explore/context_pack.json"))

            self.assertEqual("COMPLETED", resumed.run.status)
            self.assertFalse(git["is_git_repository"])
            self.assertEqual([], ci_status["providers"])
            self.assertEqual("unavailable", ci_signals["status"])
            self.assertEqual(git["is_git_repository"], context_pack["git"]["is_git_repository"])
            self.assertEqual("unavailable", context_pack["ci_digest"]["health"])

    def test_install_ci_command_delegates_through_host(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            repository = Path(directory) / "repo"
            repository.mkdir()
            host = InProcessHost(state_root=root, working_directory=repository)

            result = host.execute(InstallCiTemplates("github"))

            self.assertEqual((".github/workflows/ai-harness-ci.yml",), result.installed)
            self.assertTrue((repository / ".github" / "workflows" / "ai-harness-ci.yml").is_file())


if __name__ == "__main__":
    unittest.main()
