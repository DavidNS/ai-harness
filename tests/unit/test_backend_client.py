from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from harness.cli.backend_client import BackendClient, ResumeBackendRequest, StartBackendRequest


class BackendClientTests(unittest.TestCase):
    def client(self, repository: Path) -> BackendClient:
        return BackendClient(repository, lambda _args: 0)

    def test_start_args_include_selected_optional_flags_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prompt_file = Path("~/request.md")
            args = self.client(Path(directory)).start_args(
                StartBackendRequest(
                    provider="codex",
                    model="gpt-5",
                    reasoning_effort="high",
                    github_ci_mode="branch",
                    branch="create-from-main",
                    route="code",
                    flow="tdd",
                    source_run="run-1",
                    prompt_file=prompt_file,
                )
            )

        self.assertEqual(
            [
                "--cwd",
                str(Path(directory).resolve()),
                "--provider",
                "codex",
                "--activated",
                "--model",
                "gpt-5",
                "--reasoning-effort",
                "high",
                "--github-ci-mode",
                "branch",
                "--prompt-file",
                str(prompt_file.expanduser()),
                "--branch",
                "create-from-main",
                "--route",
                "code",
                "--flow",
                "tdd",
                "--from-run",
                "run-1",
            ],
            args,
        )

    def test_start_args_omit_none_optional_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = self.client(Path(directory)).start_args(StartBackendRequest(provider="local"))

        self.assertEqual(["--cwd", str(Path(directory).resolve()), "--provider", "local", "--activated"], args)

    def test_resume_args_include_decision_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = self.client(Path(directory)).resume_args(
                ResumeBackendRequest(
                    provider="local",
                    run_id="run-1",
                    model="gpt-5",
                    reasoning_effort="medium",
                    github_ci_mode="baseline",
                    answer="Use this answer",
                    selected_option="preserve",
                )
            )

        self.assertEqual(
            [
                "--cwd",
                str(Path(directory).resolve()),
                "--provider",
                "local",
                "--activated",
                "--resume",
                "run-1",
                "--model",
                "gpt-5",
                "--reasoning-effort",
                "medium",
                "--github-ci-mode",
                "baseline",
                "--answer",
                "Use this answer",
                "--selected-option",
                "preserve",
            ],
            args,
        )

    def test_resume_args_omit_none_optional_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = self.client(Path(directory)).resume_args(ResumeBackendRequest(provider="local", run_id="run-1"))

        self.assertEqual(
            ["--cwd", str(Path(directory).resolve()), "--provider", "local", "--activated", "--resume", "run-1"],
            args,
        )


if __name__ == "__main__":
    unittest.main()
