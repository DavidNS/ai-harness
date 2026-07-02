from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from harness_v2.backend.application.contracts import InstallCiTemplates, ResumeRun, StartRun
from harness_v2.hosts.in_process.host import InProcessHost
from test_v2.support.model_providers import ScriptedModelProvider


class ReleaseContextIntegrationTests(unittest.TestCase):
    def test_in_process_explore_starts_at_request_understanding_with_release_runtime_configured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            repository = Path(directory) / "repo"
            repository.mkdir()
            host = InProcessHost(state_root=root, working_directory=repository, branch_mode="current", github_ci_mode="baseline", model_provider=ScriptedModelProvider())

            started = host.execute(StartRun("Fix tests", root_bundle="EXPLORE_BUNDLE"))
            resumed = host.execute(ResumeRun(started.run.run_id))

            self.assertEqual("EXPLORE_BUNDLE", resumed.run.current_bundle)
            self.assertEqual("EXPLORE_CONTEXT_PACK", resumed.run.current_phase)

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
