from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "harness" / "run.py"


class LauncherIntegrationTests(unittest.TestCase):
    def test_bypass_preserves_stdin_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = "Preserve this original request exactly."
            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--bypass", "--activated"],
                input=request, text=True, capture_output=True, check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(request + "\n", completed.stdout)

    def test_bypass_accepts_prompt_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prompt = Path(directory) / "prompt.txt"
            prompt.write_text("Prompt file request\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory,
                 "--prompt-file", str(prompt), "--bypass"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("Prompt file request\n", completed.stdout)

    def test_non_code_request_completes_stub_without_routing_choice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = "Brainstorm market analysis ideas for a bakery"
            env = dict(os.environ)
            env["AI_HARNESS_PROVIDER"] = "local"
            env["AI_HARNESS_PROVIDER_COMMAND"] = f"{sys.executable} {ROOT / 'tests' / 'fixtures' / 'fake_provider.py'}"
            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory],
                input=request, text=True, capture_output=True, check=False, env=env,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertNotIn("## Decision Required", completed.stdout)
            self.assertIn("Status: non-code stub", completed.stdout)
            self.assertTrue((Path(directory) / ".ai-harness").exists())

    def test_code_request_requires_flow_selection_and_prints_scores_when_non_interactive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ)
            env["AI_HARNESS_PROVIDER"] = "local"
            env["AI_HARNESS_PROVIDER_COMMAND"] = f"{sys.executable} {ROOT / 'tests' / 'fixtures' / 'fake_provider.py'}"
            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory],
                input="Fix typo in README.md", text=True, capture_output=True, check=False, env=env,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("## Decision Required", completed.stdout)
            self.assertIn("Which bundle flow should the harness run for this request?", completed.stdout)
            self.assertIn("Scores:\n", completed.stdout)
            self.assertIn("- sdd:", completed.stdout)
            self.assertIn("Signals:\n", completed.stdout)
            self.assertNotIn("Recommended strategy: SDD", completed.stderr)
            self.assertNotIn("Press Enter to accept", completed.stderr)

    def test_install_ci_backend_installs_github_template_without_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--install-ci", "--ci-target", "github"],
                text=True, capture_output=True, check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn(".github/workflows/ai-harness-ci.yml", completed.stdout)
            self.assertTrue((Path(directory) / ".github" / "workflows" / "ai-harness-ci.yml").is_file())


    def test_install_packages_backend_dry_run_without_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--install-packages", "--package", "security", "--dry-install"],
                text=True, capture_output=True, check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("Recommended package groups: quality-core, security", completed.stdout)
            self.assertIn("Would run:", completed.stdout)
            self.assertIn("semgrep", completed.stdout)

    def test_non_code_run_records_ci_and_git_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = "Brainstorm market analysis ideas for a bakery"
            env = dict(os.environ)
            env["AI_HARNESS_PROVIDER"] = "local"
            env["AI_HARNESS_PROVIDER_COMMAND"] = f"{sys.executable} {ROOT / 'tests' / 'fixtures' / 'fake_provider.py'}"
            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory],
                input=request, text=True, capture_output=True, check=False, env=env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("ci-status.json", completed.stdout)
            self.assertIn("git-run.json", completed.stdout)
            self.assertIn("No CI pipeline", completed.stdout)


if __name__ == "__main__":
    unittest.main()
