from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from harness_v2.adapters.models import CliModelProvider
from harness_v2.backend.ports.model_provider import (
    CapabilityProjection,
    CapabilityProjectionError,
    McpToolCapability,
    ModelProviderError,
    ModelProviderRequest,
    ModelSelection,
    OutputSchema,
    PathCapability,
    TimeoutPolicy,
    TruncationPolicy,
)

ROOT = Path(__file__).resolve().parents[2]


def pipe_reader(payload: bytes = b""):
    read_fd, write_fd = os.pipe()
    if payload:
        os.write(write_fd, payload)
    os.close(write_fd)
    return os.fdopen(read_fd, "rb", buffering=0)


class CompletedPopen:
    def __init__(self, stdout: bytes = b"ok", stderr: bytes = b"", returncode: int = 0) -> None:
        self.stdout = pipe_reader(stdout)
        self.stderr = pipe_reader(stderr)
        self.stdin = io.BytesIO()
        self.returncode = returncode
        self.wait_timeout = None
        self.killed = False

    def wait(self, timeout=None):
        self.wait_timeout = timeout
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True


def permissions(mode: str = "read", **overrides: object) -> CapabilityProjection:
    data = {
        "paths": (PathCapability("**", mode),),
        "commands": (),
        "skills": ("explore-playbook",),
        "mcp_tools": (),
    }
    data.update(overrides)
    return CapabilityProjection(**data)


def request(
    prompt: str = "inspect",
    *,
    provider: str = "codex",
    model: str | None = None,
    reasoning_effort: str | None = "medium",
    capabilities: CapabilityProjection | None = None,
    output_schema: OutputSchema | None = None,
    timeout: float | None = 17,
    output_bytes: int = 2048,
) -> ModelProviderRequest:
    return ModelProviderRequest(
        prompt=prompt,
        working_directory=ROOT,
        model=ModelSelection(provider, model, reasoning_effort),
        capabilities=permissions() if capabilities is None else capabilities,
        output_schema=output_schema,
        timeout=TimeoutPolicy(timeout),
        truncation=TruncationPolicy(output_bytes),
    )


class CliModelProviderIntegrationTests(unittest.TestCase):
    def test_custom_command_runs_with_stdin_reduced_environment_and_no_shell(self) -> None:
        script = "import json, os, sys; print(json.dumps({'prompt': sys.stdin.read(), 'env': dict(os.environ)}, sort_keys=True))"
        environment = {"PATH": os.environ.get("PATH", ""), "HOME": "/safe-home", "SECRET_TOKEN": "hidden"}
        result = CliModelProvider(
            (sys.executable, "-c", script),
            environment=environment,
        ).run(request("hello", provider="custom", capabilities=CapabilityProjection()))

        payload = json.loads(result.stdout)
        self.assertTrue(result.succeeded)
        self.assertEqual("hello", payload["prompt"])
        self.assertEqual("/safe-home", payload["env"]["HOME"])
        self.assertNotIn("SECRET_TOKEN", payload["env"])

    def test_timeout_and_output_bound_are_enforced(self) -> None:
        timeout_script = "import time; print('partial', flush=True); time.sleep(5)"
        timed_out = CliModelProvider((sys.executable, "-c", timeout_script), timeout_seconds=0.3).run(
            request("ignored", provider="custom", capabilities=CapabilityProjection(), timeout=1)
        )
        self.assertTrue(timed_out.timed_out)
        self.assertIn("partial", timed_out.stdout)

        large_script = "print('x' * 4096)"
        large = CliModelProvider((sys.executable, "-c", large_script), output_limit=32).run(
            request("ignored", provider="custom", capabilities=CapabilityProjection(), output_bytes=128)
        )
        self.assertTrue(large.truncated)
        self.assertIn("[output truncated]", large.stdout)

    @mock.patch("harness_v2.adapters.models.cli.subprocess.Popen")
    def test_claude_projection_limits_tools_adds_json_schema_and_uses_shell_false(self, popen) -> None:
        process = CompletedPopen()
        popen.return_value = process
        schema = OutputSchema("request_profile", {"type": "object", "required": ["schema_version"]})

        CliModelProvider(("claude", "--print"), timeout_seconds=30).run(
            request("inspect", provider="claude", model="sonnet", capabilities=permissions("read"), output_schema=schema)
        )

        argv = popen.call_args.args[0]
        self.assertEqual("claude", argv[0])
        self.assertIn("--model", argv)
        self.assertIn("sonnet", argv)
        self.assertIn("Read,Glob,Grep", argv)
        self.assertEqual(schema.schema, json.loads(argv[argv.index("--json-schema") + 1]))
        self.assertNotIn("Bash", argv)
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(17, process.wait_timeout)

    @mock.patch("harness_v2.adapters.models.cli.subprocess.Popen")
    def test_codex_write_projection_passes_workspace_sandbox_prompt_schema_file_and_uses_shell_false(self, popen) -> None:
        captured_schema = {}
        process = CompletedPopen()

        def start(argv, **kwargs):
            schema_path = Path(argv[argv.index("--output-schema") + 1])
            captured_schema.update(json.loads(schema_path.read_text(encoding="utf-8")))
            return process

        popen.side_effect = start
        schema = OutputSchema("request_profile", {"type": "object", "required": ["schema_version"]})

        CliModelProvider.for_name("codex", timeout_seconds=30).run(
            request("inspect", provider="codex", model="gpt-5", reasoning_effort="low", capabilities=permissions("write"), output_schema=schema)
        )

        argv = popen.call_args.args[0]
        self.assertEqual("codex", argv[0])
        self.assertIn("--model", argv)
        self.assertIn("gpt-5", argv)
        self.assertIn('model_reasoning_effort="low"', argv)
        self.assertEqual("workspace-write", argv[argv.index("--sandbox") + 1])
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertEqual(schema.schema, captured_schema)
        self.assertFalse(Path(argv[argv.index("--output-schema") + 1]).exists())
        self.assertEqual("inspect", argv[-1])
        self.assertEqual(subprocess.DEVNULL, popen.call_args.kwargs["stdin"])
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(17, process.wait_timeout)

    @mock.patch("harness_v2.adapters.models.cli.subprocess.Popen")
    def test_codex_read_projection_passes_read_only_sandbox_and_schema(self, popen) -> None:
        captured_schema = {}
        process = CompletedPopen()

        def start(argv, **kwargs):
            schema_path = Path(argv[argv.index("--output-schema") + 1])
            captured_schema.update(json.loads(schema_path.read_text(encoding="utf-8")))
            return process

        popen.side_effect = start
        schema = OutputSchema("request_profile", {"type": "object", "required": ["schema_version"]})

        CliModelProvider.for_name("codex", timeout_seconds=30).run(
            request("inspect", provider="codex", model="gpt-5", capabilities=permissions("read"), output_schema=schema)
        )

        argv = popen.call_args.args[0]
        self.assertEqual("read-only", argv[argv.index("--sandbox") + 1])
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertEqual(schema.schema, captured_schema)
        self.assertEqual("inspect", argv[-1])
        self.assertEqual(subprocess.DEVNULL, popen.call_args.kwargs["stdin"])
        self.assertFalse(popen.call_args.kwargs["shell"])

    def test_process_start_failures_are_model_provider_errors(self) -> None:
        with self.assertRaises(ModelProviderError):
            CliModelProvider(("/definitely/missing/provider",)).run(
                request(provider="custom", capabilities=CapabilityProjection())
            )
        with self.assertRaises(ModelProviderError):
            CliModelProvider((sys.executable, "-c", "print('ok')")).run(
                ModelProviderRequest(
                    prompt="inspect",
                    working_directory=ROOT / "missing-directory",
                    model=ModelSelection("custom"),
                    capabilities=CapabilityProjection(),
                )
            )

    def test_cli_projection_rejects_unenforceable_capabilities(self) -> None:
        with self.assertRaisesRegex(CapabilityProjectionError, "partial path"):
            CliModelProvider(("claude", "--print")).run(
                request(provider="claude", capabilities=permissions(paths=(PathCapability("src/**", "read"),)))
            )
        with self.assertRaisesRegex(CapabilityProjectionError, "argv"):
            CliModelProvider(("codex", "exec", "-")).run(
                request(provider="codex", capabilities=permissions("write", commands=(("git", "status"),)))
            )
        with self.assertRaisesRegex(CapabilityProjectionError, "MCP"):
            CliModelProvider(("claude", "--print")).run(
                request(provider="claude", capabilities=permissions("read", mcp_tools=(McpToolCapability("docs", "search", "read"),)))
            )
        with self.assertRaisesRegex(CapabilityProjectionError, "custom provider"):
            CliModelProvider((sys.executable, "-c", "print('ok')")).run(request(provider="custom"))
        with self.assertRaisesRegex(CapabilityProjectionError, "output schemas"):
            CliModelProvider((sys.executable, "-c", "print('ok')")).run(
                request(provider="custom", capabilities=CapabilityProjection(), output_schema=OutputSchema("schema", {"type": "object"}))
            )


if __name__ == "__main__":
    unittest.main()
