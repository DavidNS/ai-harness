import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
from ai_harness.providers.cli_provider import CapabilityProjectionError, CliProvider
FIXTURE = ROOT / "tests" / "fixtures" / "fake_provider.py"


def pipe_reader(payload: bytes = b""):
    read_fd, write_fd = os.pipe()
    if payload:
        os.write(write_fd, payload)
    os.close(write_fd)
    return os.fdopen(read_fd, "rb", buffering=0)


class CompletedPopen:
    def __init__(self, stdout: bytes = b"ok", stderr: bytes = b"", returncode: int = 0):
        self.stdout = pipe_reader(stdout)
        self.stderr = pipe_reader(stderr)
        self.stdin = io.BytesIO()
        self.returncode = returncode
        self.wait_timeout = None
        self.killed = False
        self.terminated = False

    def wait(self, timeout=None):
        self.wait_timeout = timeout
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True

    def terminate(self):
        self.terminated = True


class CliProviderTests(unittest.TestCase):
    def provider(self, **kwargs):
        return CliProvider((sys.executable, str(FIXTURE)), **kwargs)

    def test_stdin_and_explicit_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.provider().run_prompt('{"ok": true}', cwd=Path(directory))
        self.assertTrue(result.succeeded)
        self.assertEqual('{"ok": true}', result.stdout.strip())
        self.assertGreaterEqual(result.duration_seconds, 0)

    def test_reduced_environment(self):
        environment = {"HOME": "/safe-home", "PATH": "/safe-path", "SECRET_TOKEN": "must-not-leak"}
        result = self.provider(environment=environment).run_prompt("ENV", cwd=ROOT)
        captured = json.loads(result.stdout)
        self.assertEqual("/safe-home", captured["HOME"])
        self.assertEqual("/safe-path", captured["PATH"])
        self.assertNotIn("SECRET_TOKEN", captured)
        self.assertNotIn("TMPDIR", captured)

    def test_temp_dir_overrides_environment_tmpdir(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory) / "harness-tmp"
            temp_dir.mkdir()
            environment = {"PATH": os.environ["PATH"], "TMPDIR": "/wrong-tmp"}
            result = self.provider(environment=environment).run_prompt("ENV", cwd=ROOT, temp_dir=temp_dir)
        captured = json.loads(result.stdout)
        self.assertEqual(str(temp_dir), captured["TMPDIR"])

    def test_nonzero_exit_and_stderr(self):
        events = []
        result = self.provider().run_prompt(
            "FAIL", cwd=ROOT, progress=lambda stream, text: events.append((stream, text))
        )
        self.assertFalse(result.succeeded)
        self.assertEqual(7, result.exit_code)
        self.assertIn("fake provider failure", result.stderr)
        self.assertTrue(any(stream == "stderr" and "fake provider failure" in text for stream, text in events))

    def test_timeout(self):
        result = self.provider(timeout_seconds=0.05).run_prompt("TIMEOUT", cwd=ROOT)
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.exit_code)

    def test_timeout_preserves_partial_streamed_output(self):
        script = (
            "import sys, time; "
            "print('partial stdout', flush=True); "
            "print('partial stderr', file=sys.stderr, flush=True); "
            "time.sleep(5)"
        )
        events = []
        result = CliProvider((sys.executable, "-c", script), timeout_seconds=0.3).run_prompt(
            "", cwd=ROOT, progress=lambda stream, text: events.append((stream, text))
        )
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.exit_code)
        self.assertIn("partial stdout", result.stdout)
        self.assertIn("partial stderr", result.stderr)
        self.assertTrue(any(stream == "stdout" and "partial stdout" in text for stream, text in events))
        self.assertTrue(any(stream == "stderr" and "partial stderr" in text for stream, text in events))

    def test_streams_stdout_and_stderr_before_process_exit(self):
        script = (
            "import sys, time; "
            "print('stdout ready', flush=True); "
            "print('stderr ready', file=sys.stderr, flush=True); "
            "time.sleep(1); "
            "print('stdout done', flush=True)"
        )
        events = []
        holder = {}

        def run_provider():
            holder["result"] = CliProvider((sys.executable, "-c", script), timeout_seconds=5).run_prompt(
                "", cwd=ROOT, progress=lambda stream, text: events.append((stream, text, time.monotonic()))
            )

        thread = threading.Thread(target=run_provider)
        thread.start()
        deadline = time.monotonic() + 2
        while {stream for stream, _, _ in events} != {"stdout", "stderr"} and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual({"stdout", "stderr"}, {stream for stream, _, _ in events})
        self.assertTrue(thread.is_alive())
        thread.join(3)
        self.assertFalse(thread.is_alive())
        result = holder["result"]
        self.assertTrue(result.succeeded)
        self.assertIn("stdout ready", result.stdout)
        self.assertIn("stdout done", result.stdout)
        self.assertIn("stderr ready", result.stderr)

    def test_inherited_pipe_descendant_does_not_block_provider_return(self):
        script = (
            "import subprocess, sys; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'], "
            "stdout=sys.stdout, stderr=sys.stderr); "
            "print('parent done', flush=True)"
        )
        started = time.monotonic()
        result = CliProvider((sys.executable, "-c", script), timeout_seconds=5).run_prompt("", cwd=ROOT)

        self.assertLess(time.monotonic() - started, 1.8)
        self.assertTrue(result.succeeded)
        self.assertIn("parent done", result.stdout)

    def test_output_bound(self):
        result = self.provider(output_limit=32).run_prompt("LARGE", cwd=ROOT)
        self.assertTrue(result.truncated)
        self.assertLess(len(result.stdout), 64)
        self.assertTrue(result.stdout.endswith("[output truncated]"))

    def permissions(self, mode="read", **overrides):
        value = {
            "paths": [{"pattern": "**", "mode": mode}],
            "commands": [],
            "skills": ["explore-playbook"],
            "mcp_tools": [],
            "timeout_seconds": 17,
            "output_bytes": 2048,
        }
        value.update(overrides)
        return value

    @mock.patch("ai_harness.providers._cli_process.subprocess.Popen")
    def test_claude_read_only_projection_disables_shell_writes_and_mcp(self, popen):
        process = CompletedPopen()
        popen.return_value = process
        CliProvider(("claude", "--print"), timeout_seconds=30).run_prompt(
            "inspect", cwd=ROOT, permissions=self.permissions()
        )
        argv = popen.call_args.args[0]
        self.assertEqual(
            [
                "claude", "--print", "--tools", "Read,Glob,Grep",
                "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            ],
            argv,
        )
        self.assertNotIn("Bash", argv)
        self.assertEqual(17, process.wait_timeout)

    @mock.patch("ai_harness.providers._cli_process.subprocess.Popen")
    def test_claude_write_projection_allows_only_file_tools(self, popen):
        popen.return_value = CompletedPopen()
        CliProvider(("claude", "--print")).run_prompt(
            "change", cwd=ROOT, permissions=self.permissions("write")
        )
        argv = popen.call_args.args[0]
        self.assertIn("Read,Glob,Grep,Edit,Write", argv)
        self.assertEqual("acceptEdits", argv[-1])
        self.assertNotIn("Bash", argv)

    def test_claude_rejects_worker_commands_and_mcp_tools(self):
        provider = CliProvider(("claude", "--print"))
        with self.assertRaisesRegex(CapabilityProjectionError, "argv"):
            provider.run_prompt(
                "run", cwd=ROOT,
                permissions=self.permissions(commands=[["git", "status"]]),
            )
        with self.assertRaisesRegex(CapabilityProjectionError, "MCP"):
            provider.run_prompt(
                "search", cwd=ROOT,
                permissions=self.permissions(
                    mcp_tools=[{"server": "docs", "name": "search", "access": "read"}]
                ),
            )

    @mock.patch("ai_harness.providers._cli_process.subprocess.Popen")
    def test_worker_permissions_can_disable_provider_timeout(self, popen):
        process = CompletedPopen()
        popen.return_value = process
        CliProvider.for_name("codex", timeout_seconds=30).run_prompt(
            "inspect", cwd=ROOT, permissions=self.permissions(timeout_seconds=None)
        )
        self.assertIsNone(process.wait_timeout)

    @mock.patch("ai_harness.providers._cli_process.subprocess.Popen")
    def test_codex_read_projection_bypasses_nested_sandbox_and_passes_prompt_as_argument(self, popen):
        process = CompletedPopen()
        popen.return_value = process
        CliProvider.for_name("codex", timeout_seconds=30).run_prompt(
            "inspect", cwd=ROOT, permissions=self.permissions()
        )
        self.assertEqual(
            [
                "codex",
                "exec",
                "-c",
                'model_reasoning_effort="medium"',
                "--dangerously-bypass-approvals-and-sandbox",
                "--dangerously-bypass-hook-trust",
                "inspect",
            ],
            popen.call_args.args[0],
        )
        self.assertEqual(subprocess.DEVNULL, popen.call_args.kwargs["stdin"])
        self.assertEqual(17, process.wait_timeout)


    @mock.patch("ai_harness.providers._cli_process.subprocess.Popen")
    def test_codex_model_can_be_overridden(self, popen):
        popen.return_value = CompletedPopen()
        CliProvider.for_name(
            "codex",
            timeout_seconds=30,
            environment={"AI_HARNESS_CODEX_MODEL": "gpt-5"},
        ).run_prompt("inspect", cwd=ROOT, permissions=self.permissions())
        self.assertIn("--model", popen.call_args.args[0])
        self.assertIn("gpt-5", popen.call_args.args[0])

    @mock.patch("ai_harness.providers._cli_process.subprocess.Popen")
    def test_claude_model_can_be_overridden(self, popen):
        popen.return_value = CompletedPopen()
        CliProvider.for_name(
            "claude",
            timeout_seconds=30,
            environment={"AI_HARNESS_CLAUDE_MODEL": "sonnet"},
        ).run_prompt("inspect", cwd=ROOT, permissions=self.permissions())
        argv = popen.call_args.args[0]
        self.assertEqual("claude", argv[0])
        self.assertIn("--model", argv)
        self.assertIn("sonnet", argv)

    @mock.patch("ai_harness.providers._cli_process.subprocess.Popen")
    def test_generic_model_env_takes_precedence_for_cli_providers(self, popen):
        popen.return_value = CompletedPopen()
        CliProvider.for_name(
            "codex",
            timeout_seconds=30,
            environment={"AI_HARNESS_MODEL": "gpt-5.5", "AI_HARNESS_CODEX_MODEL": "gpt-5"},
        ).run_prompt("inspect", cwd=ROOT, permissions=self.permissions())
        argv = popen.call_args.args[0]
        self.assertIn("--model", argv)
        self.assertIn("gpt-5.5", argv)
        self.assertNotIn("gpt-5", argv)

    @mock.patch("ai_harness.providers._cli_process.subprocess.Popen")
    def test_codex_write_projection_bypasses_nested_sandbox(self, popen):
        popen.return_value = CompletedPopen()
        CliProvider.for_name("codex", timeout_seconds=30).run_prompt(
            "implement", cwd=ROOT, permissions=self.permissions("write")
        )
        self.assertEqual(
            [
                "codex",
                "exec",
                "-c",
                'model_reasoning_effort="medium"',
                "--dangerously-bypass-approvals-and-sandbox",
                "--dangerously-bypass-hook-trust",
                "implement",
            ],
            popen.call_args.args[0],
        )
        self.assertEqual(subprocess.DEVNULL, popen.call_args.kwargs["stdin"])

    @mock.patch("ai_harness.providers._cli_process.subprocess.Popen")
    def test_codex_reasoning_effort_can_be_overridden(self, popen):
        popen.return_value = CompletedPopen()
        CliProvider(
            ("codex", "exec", "-"),
            environment={"AI_HARNESS_CODEX_REASONING_EFFORT": "low"},
        ).run_prompt("inspect", cwd=ROOT, permissions=self.permissions())
        self.assertIn('model_reasoning_effort="low"', popen.call_args.args[0])

    def test_codex_rejects_worker_commands_and_mcp_tools(self):
        provider = CliProvider(("codex", "exec", "-"))
        with self.assertRaisesRegex(CapabilityProjectionError, "argv"):
            provider.run_prompt(
                "run", cwd=ROOT,
                permissions=self.permissions(commands=[["git", "status"]]),
            )
        with self.assertRaisesRegex(CapabilityProjectionError, "MCP"):
            provider.run_prompt(
                "search", cwd=ROOT,
                permissions=self.permissions(
                    mcp_tools=[{"server": "docs", "name": "search", "access": "read"}]
                ),
            )

    def test_custom_provider_rejects_permissions(self):
        with self.assertRaisesRegex(CapabilityProjectionError, "custom provider"):
            self.provider().run_prompt("inspect", cwd=ROOT, permissions=self.permissions())

    def test_invalid_or_partial_projection_fails_closed(self):
        provider = CliProvider(("claude", "--print"))
        with self.assertRaises(CapabilityProjectionError):
            provider.run_prompt("inspect", cwd=ROOT, permissions={})
        with self.assertRaisesRegex(CapabilityProjectionError, "partial path"):
            provider.run_prompt(
                "inspect", cwd=ROOT,
                permissions=self.permissions(paths=[{"pattern": "src/**", "mode": "read"}]),
            )

if __name__ == "__main__":
    unittest.main()
