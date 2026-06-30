from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "ai-harness"


def run_launcher(*arguments: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if env:
        environment.update(env)
    return subprocess.run(
        [str(LAUNCHER), *arguments],
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RootLauncherIntegrationTests(unittest.TestCase):
    def test_positional_request_dry_run_delegates_current_cwd_provider_and_activated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            completed = run_launcher("--dry-run", "--cwd", str(repository), "--provider", "local", "Fix tests", cwd=repository)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("", completed.stdout)
            self.assertIn("harness/run.py", completed.stderr)
            self.assertIn(f"--cwd {repository}", completed.stderr)
            self.assertIn("--provider local", completed.stderr)
            self.assertIn("--activated", completed.stderr)
            self.assertFalse((repository / ".ai-harness").exists())

    def test_positional_request_dry_run_includes_model_when_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            completed = run_launcher(
                "--dry-run",
                "--cwd", str(repository),
                "--provider", "codex",
                "--model", "gpt-5",
                "Fix tests",
                cwd=repository,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("--model gpt-5", completed.stderr)


    def test_positional_request_dry_run_includes_codex_reasoning_effort(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            completed = run_launcher(
                "--dry-run",
                "--cwd", str(repository),
                "--provider", "codex",
                "--reasoning-effort", "xhigh",
                "Fix tests",
                cwd=repository,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("--reasoning-effort xhigh", completed.stderr)

    def test_file_request_dry_run_delegates_prompt_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            request = repository / "request.md"
            request.write_text("Fix tests\n", encoding="utf-8")

            completed = run_launcher("--dry-run", "--cwd", str(repository), "--provider", "local", "--file", str(request), cwd=repository)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("--prompt-file", completed.stderr)
            self.assertIn(str(request), completed.stderr)

    def test_status_and_runs_delegate_without_request_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            status = run_launcher("--cwd", str(repository), "status", cwd=repository)
            runs = run_launcher("--cwd", str(repository), "runs", cwd=repository)

            self.assertEqual(0, status.returncode, status.stderr)
            self.assertIn("Status: no run", status.stdout)
            self.assertNotIn("harness/run.py", status.stderr)
            self.assertEqual(0, runs.returncode, runs.stderr)
            self.assertIn("No live runs found", runs.stdout)

    def test_verbose_and_dry_run_expose_backend_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            verbose = run_launcher("--verbose", "--cwd", str(repository), "status", cwd=repository)
            dry = run_launcher("--dry-run", "--cwd", str(repository), "runs", cwd=repository)

            self.assertEqual(0, verbose.returncode, verbose.stderr)
            self.assertIn("harness/run.py", verbose.stderr)
            self.assertEqual(0, dry.returncode, dry.stderr)
            self.assertIn("--show-runs", dry.stderr)
            self.assertEqual("", dry.stdout)

    def test_resume_and_archive_dry_run_delegate_to_backend_recovery_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            current = repository / ".ai-harness" / "artifacts" / "current-run-a"
            current.mkdir(parents=True)
            (current / "state.json").write_text('{"run_id":"run-a","status":"active"}\n', encoding="utf-8")

            resume = run_launcher("--dry-run", "--cwd", str(repository), "--provider", "local", "resume", "run-a", cwd=repository)
            archive = run_launcher("--dry-run", "--cwd", str(repository), "archive", "run-a", cwd=repository)

            self.assertEqual(0, resume.returncode, resume.stderr)
            self.assertIn("--resume run-a", resume.stderr)
            self.assertIn("--provider local", resume.stderr)
            self.assertEqual(0, archive.returncode, archive.stderr)
            self.assertIn("--archive run-a", archive.stderr)

    def test_provider_default_prefers_environment_before_detected_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            fake_bin = repository / "bin"
            fake_bin.mkdir()
            codex = fake_bin / "codex"
            codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            codex.chmod(0o755)
            env = {"AI_HARNESS_PROVIDER": "local", "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"}

            completed = run_launcher("--dry-run", "--cwd", str(repository), "Fix tests", cwd=repository, env=env)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("--provider local", completed.stderr)


    def test_github_ci_mode_flag_delegates_to_backend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            completed = run_launcher(
                "--dry-run", "--cwd", str(repository), "--provider", "local",
                "--github-ci-mode", "branch", "Fix tests", cwd=repository,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("--github-ci-mode branch", completed.stderr)


    def test_positional_exit_is_normal_request_not_launcher_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            completed = run_launcher("--dry-run", "--cwd", str(repository), "--provider", "local", "/exit", cwd=repository)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("harness/run.py", completed.stderr)
            self.assertIn("--activated", completed.stderr)
            self.assertNotIn("Unknown slash command", completed.stderr)



    def test_interactive_cli_start_shows_ci_preflight_before_delegating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            master, slave = pty.openpty()
            try:
                process = subprocess.Popen(
                    [str(LAUNCHER), "--dry-run", "--cwd", str(repository), "--provider", "local", "Fix tests"],
                    cwd=repository,
                    stdin=slave,
                    stdout=subprocess.PIPE,
                    stderr=slave,
                    text=False,
                    close_fds=True,
                )
                os.close(slave)
                output = bytearray()
                sent_continue = False
                sent_branch = False
                selected_route = False
                selected_flow = False
                deadline = time.time() + 5
                while time.time() < deadline and process.poll() is None:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if not ready:
                        continue
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    output.extend(chunk)
                    if not sent_continue and b"CI setup check" in output:
                        os.write(master, b"c")
                        sent_continue = True
                    elif sent_continue and not sent_branch and b"Git branch" in output:
                        os.write(master, b"c")
                        sent_branch = True
                    elif sent_branch and not selected_route and b"Request route" in output:
                        os.write(master, b"c")
                        selected_route = True
                    elif selected_route and not selected_flow and b"Code flow" in output:
                        os.write(master, b"f")
                        selected_flow = True
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()

                decoded = output.decode("utf-8", errors="replace")
                self.assertTrue(sent_continue, decoded)
                self.assertEqual(0, process.returncode, decoded)
                self.assertIn("CI setup check", decoded)
                self.assertIn("harness/run.py", decoded)
            finally:
                try:
                    os.close(master)
                except OSError:
                    pass

    def test_interactive_cli_skip_warnings_delegates_without_ci_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            master, slave = pty.openpty()
            try:
                process = subprocess.Popen(
                    [str(LAUNCHER), "--skip-warnings", "--dry-run", "--cwd", str(repository), "--provider", "local", "Fix tests"],
                    cwd=repository,
                    stdin=slave,
                    stdout=subprocess.PIPE,
                    stderr=slave,
                    text=False,
                    close_fds=True,
                )
                os.close(slave)
                output = bytearray()
                sent_branch = False
                selected_route = False
                selected_flow = False
                deadline = time.time() + 5
                while time.time() < deadline and process.poll() is None:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if not ready:
                        continue
                    try:
                        output.extend(os.read(master, 4096))
                    except OSError:
                        break
                    if not sent_branch and b"Git branch" in output:
                        os.write(master, b"c")
                        sent_branch = True
                    elif sent_branch and not selected_route and b"Request route" in output:
                        os.write(master, b"c")
                        selected_route = True
                    elif selected_route and not selected_flow and b"Code flow" in output:
                        os.write(master, b"f")
                        selected_flow = True
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()

                decoded = output.decode("utf-8", errors="replace")
                self.assertEqual(0, process.returncode, decoded)
                self.assertNotIn("CI setup check", decoded)
                self.assertIn("harness/run.py", decoded)
            finally:
                try:
                    os.close(master)
                except OSError:
                    pass


    def test_install_ci_dry_run_delegates_backend_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            completed = run_launcher("--dry-run", "--cwd", str(repository), "install-ci", "github", cwd=repository)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("--install-ci", completed.stderr)
            self.assertIn("--ci-target github", completed.stderr)

    def test_install_ci_accepts_force_before_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            completed = run_launcher("--dry-run", "--cwd", str(repository), "install-ci", "--force", "github", cwd=repository)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("--install-ci", completed.stderr)
            self.assertIn("--ci-target github", completed.stderr)
            self.assertIn("--force", completed.stderr)



    def test_install_packages_dry_run_delegates_backend_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            completed = run_launcher("--dry-run", "--cwd", str(repository), "install-packages", "security", "github", "--dry-install", cwd=repository)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("--install-packages", completed.stderr)
            self.assertIn("--package security", completed.stderr)
            self.assertIn("--package github", completed.stderr)
            self.assertIn("--dry-install", completed.stderr)

    def test_interactive_console_status_returns_to_prompt_then_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            master, slave = pty.openpty()
            try:
                process = subprocess.Popen(
                    [str(LAUNCHER), "--cwd", str(repository), "--provider", "local"],
                    cwd=repository,
                    stdin=slave,
                    stdout=subprocess.PIPE,
                    stderr=slave,
                    text=False,
                    close_fds=True,
                )
                os.close(slave)
                output = bytearray()
                sent_status = False
                sent_exit = False
                deadline = time.time() + 5
                while time.time() < deadline and process.poll() is None:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if not ready:
                        continue
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    output.extend(chunk)
                    prompts = output.count(b"aih>")
                    if not sent_status and prompts >= 1:
                        os.write(master, b"status\r")
                        sent_status = True
                    elif sent_status and not sent_exit and prompts >= 2:
                        os.write(master, b"exit\r")
                        sent_exit = True
                try:
                    stdout, _ = process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, _ = process.communicate()

                decoded = output.decode("utf-8", errors="replace")
                self.assertTrue(sent_status, decoded)
                self.assertTrue(sent_exit, decoded)
                self.assertEqual(0, process.returncode, decoded)
                self.assertIn(b"Status: no run", stdout)
                self.assertIn("AI Code Harness console", decoded)
            finally:
                try:
                    os.close(master)
                except OSError:
                    pass

    def test_interactive_console_code_route_continues_to_explorer_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider_script = repository / "codex"
            provider_script.write_text("#!/bin/sh\ncat >/dev/null\n", encoding="utf-8")
            provider_script.chmod(0o755)
            env = os.environ.copy()
            env["AI_HARNESS_PROVIDER_COMMAND"] = str(provider_script)
            master, slave = pty.openpty()
            try:
                process = subprocess.Popen(
                    [str(LAUNCHER), "--cwd", str(repository), "--provider", "codex"],
                    cwd=repository,
                    env=env,
                    stdin=slave,
                    stdout=subprocess.PIPE,
                    stderr=slave,
                    text=False,
                    close_fds=True,
                )
                os.close(slave)
                output = bytearray()
                sent_request = False
                sent_ci_continue = False
                sent_branch = False
                selected_code = False
                sent_exit = False
                deadline = time.time() + 8
                while time.time() < deadline and process.poll() is None:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if not ready:
                        continue
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    output.extend(chunk)
                    if not sent_request and b"aih>" in output:
                        os.write(master, b"I want to add autocompletion to console\r")
                        sent_request = True
                    if sent_request and not sent_ci_continue and b"CI setup check" in output:
                        os.write(master, b"c")
                        sent_ci_continue = True
                    if sent_ci_continue and not sent_branch and b"Git branch" in output:
                        os.write(master, b"c")
                        sent_branch = True
                    if sent_branch and not selected_code and b"Request route" in output:
                        os.write(master, b"c")
                        selected_code = True
                    if selected_code and not sent_exit and b"Code flow" in output:
                        os.write(master, b"/exit\r")
                        sent_exit = True
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()

                decoded = output.decode("utf-8", errors="replace")
                self.assertTrue(sent_request, decoded)
                self.assertTrue(sent_ci_continue, decoded)
                self.assertTrue(selected_code, decoded)
                self.assertTrue(sent_exit, decoded)
                self.assertEqual(0, process.returncode, decoded)
                self.assertIn("EXPLORE_BUNDLE", decoded)
                self.assertIn("Full SDD", decoded)
                self.assertIn("TDD_BUNDLE", decoded)
            finally:
                try:
                    os.close(master)
                except OSError:
                    pass

    def test_interactive_console_recovery_offers_single_unfinished_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            current = repository / ".ai-harness" / "artifacts" / "current-run-a"
            current.mkdir(parents=True)
            (current / "state.json").write_text('{"run_id":"run-a","status":"waiting_for_user","current_phase":"DESIGN"}\n', encoding="utf-8")
            master, slave = pty.openpty()
            try:
                process = subprocess.Popen(
                    [str(LAUNCHER), "--cwd", str(repository), "--provider", "local"],
                    cwd=repository,
                    stdin=slave,
                    stdout=subprocess.PIPE,
                    stderr=slave,
                    text=False,
                    close_fds=True,
                )
                os.close(slave)
                output = bytearray()
                sent_new = False
                sent_exit = False
                deadline = time.time() + 5
                while time.time() < deadline and process.poll() is None:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if not ready:
                        continue
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    output.extend(chunk)
                    if not sent_new and b"Start a new request" in output:
                        os.write(master, b"n")
                        sent_new = True
                    elif sent_new and not sent_exit and b"aih>" in output:
                        os.write(master, b"exit\r")
                        sent_exit = True
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()

                decoded = output.decode("utf-8", errors="replace")
                self.assertTrue(sent_new, decoded)
                self.assertTrue(sent_exit, decoded)
                self.assertEqual(0, process.returncode, decoded)
                self.assertIn("Unfinished run found", decoded)
                self.assertIn("Resume run-a", decoded)
                self.assertIn("phase=DESIGN", decoded)
            finally:
                try:
                    os.close(master)
                except OSError:
                    pass

    def test_interactive_console_full_implementation_lists_scope_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs" / "explorer" / "improvements" / "console" / "improvement.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("# Improvement: Console Flow\n", encoding="utf-8")
            master, slave = pty.openpty()
            try:
                process = subprocess.Popen(
                    [str(LAUNCHER), "--dry-run", "--cwd", str(repository), "--provider", "local"],
                    cwd=repository,
                    stdin=slave,
                    stdout=subprocess.PIPE,
                    stderr=slave,
                    text=False,
                    close_fds=True,
                )
                os.close(slave)
                output = bytearray()
                sent_request = False
                sent_ci_continue = False
                sent_branch = False
                sent_scope = False
                selected_route = False
                selected_flow = False
                sent_exit = False
                deadline = time.time() + 5
                while time.time() < deadline and process.poll() is None:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if not ready:
                        continue
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    output.extend(chunk)
                    if not sent_request and b"aih>" in output:
                        os.write(master, b"Full implementation for console flow\r")
                        sent_request = True
                    if sent_request and not sent_ci_continue and b"CI setup check" in output:
                        os.write(master, b"c")
                        sent_ci_continue = True
                    if sent_ci_continue and not sent_branch and b"Git branch" in output:
                        os.write(master, b"c")
                        sent_branch = True
                    if sent_branch and not sent_scope and b"Explorer scope" in output:
                        os.write(master, b"1\r")
                        sent_scope = True
                    if sent_scope and not selected_route and b"Request route" in output:
                        os.write(master, b"c")
                        selected_route = True
                    if selected_route and not selected_flow and b"Code flow" in output:
                        os.write(master, b"f")
                        selected_flow = True
                    if selected_flow and not sent_exit and output.count(b"aih>") >= 2:
                        os.write(master, b"exit\r")
                        sent_exit = True
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()

                decoded = output.decode("utf-8", errors="replace")
                self.assertTrue(sent_request, decoded)
                self.assertTrue(sent_ci_continue, decoded)
                self.assertTrue(sent_scope, decoded)
                self.assertTrue(sent_exit, decoded)
                self.assertEqual(0, process.returncode, decoded)
                self.assertIn("Available improvement artifacts", decoded)
                self.assertIn("Console Flow", decoded)
                self.assertIn("Selected explorer scope docs/explorer/improvements/console/improvement.md", decoded)
            finally:
                try:
                    os.close(master)
                except OSError:
                    pass

if __name__ == "__main__":
    unittest.main()
