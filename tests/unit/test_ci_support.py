from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_harness.ci_support import (
    ci_observations_from_artifact,
    ci_preflight,
    ci_status,
    compare_ci_signals,
    detected_ci_providers,
    github_branch_ci_signals,
    github_ci_signals,
    gitlab_ci_signals,
    infer_github_project,
    infer_gitlab_project,
    install_ci_templates,
    maybe_create_run_branch,
    merged_ci_signals,
    normalize_ci_signal_paths,
    record_branch_ci_artifacts,
    record_ci_and_git_artifacts,
    repository_runtime_context,
)
from ai_harness.models import Complexity, Mode, RunState, Strategy
from ai_harness.stores.artifact import ArtifactStore
from ai_harness.stores.state import StateStore


class _Response:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


class CiSupportTests(unittest.TestCase):


    def test_infer_github_project_from_common_remote_urls(self) -> None:
        https = infer_github_project("https://github.com/owner/repo.git")
        ssh = infer_github_project("git@github.com:owner/repo.git")

        self.assertIsNotNone(https)
        self.assertEqual("owner/repo", https["project_path"])
        self.assertIsNotNone(ssh)
        self.assertEqual("owner", ssh["owner"])
        self.assertEqual("repo", ssh["repo"])

    def test_detected_ci_providers_can_include_both(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            workflows = repository / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("name: ci\n", encoding="utf-8")
            (repository / ".gitlab-ci.yml").write_text("stages: []\n", encoding="utf-8")

            self.assertEqual(("github", "gitlab"), detected_ci_providers(repository))

    def test_github_ci_signals_reports_missing_gh_as_problem_gathering_info(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            workflows = repository / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("name: ci\n", encoding="utf-8")

            signals = github_ci_signals(repository, which=lambda _cmd: None)

            self.assertEqual("problem_gathering_info", signals["status"])
            self.assertIn("gh", signals["reason"])

    def test_github_ci_signals_fetches_latest_main_artifact_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/owner/repo.git"], cwd=repository, check=True)
            payload = {
                "schema_version": 1,
                "kind": "ai_harness_ci_signals",
                "summary": {"status": "passed"},
                "path_index": [{"path": "harness/run.py", "signal_count": 1}],
                "signals": [{"tool": "pytest", "status": "passed", "path": "tests/test_run.py"}],
            }

            def runner(args, **_kwargs):
                if args[:3] == ["gh", "auth", "status"]:
                    return subprocess.CompletedProcess(args, 0, "", "")
                if args[:3] == ["gh", "run", "list"]:
                    return subprocess.CompletedProcess(args, 0, json.dumps([{
                        "databaseId": 11,
                        "headSha": "abc123",
                        "conclusion": "success",
                        "status": "completed",
                        "workflowName": "AI Harness CI",
                        "url": "https://github.com/owner/repo/actions/runs/11",
                        "event": "push",
                        "createdAt": "2026-06-29T00:00:00Z",
                    }]), "")
                if args[:3] == ["gh", "run", "download"]:
                    target = Path(args[args.index("--dir") + 1]) / "signals"
                    target.mkdir(parents=True)
                    (target / "ai-harness-signals.json").write_text(json.dumps(payload), encoding="utf-8")
                    return subprocess.CompletedProcess(args, 0, "", "")
                raise AssertionError(args)

            signals = github_ci_signals(repository, runner=runner, which=lambda _cmd: "/usr/bin/gh")

            self.assertEqual("ready", signals["status"])
            self.assertEqual("github", signals["provider"])
            self.assertEqual(11, signals["source"]["run_id"])
            self.assertEqual(1, len(signals["signals"]))

    def test_github_ci_signals_returns_partial_when_artifact_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/owner/repo.git"], cwd=repository, check=True)

            def runner(args, **_kwargs):
                if args[:3] == ["gh", "auth", "status"]:
                    return subprocess.CompletedProcess(args, 0, "", "")
                if args[:3] == ["gh", "run", "list"]:
                    return subprocess.CompletedProcess(args, 0, json.dumps([{"databaseId": 12, "headSha": "abc123"}]), "")
                if args[:3] == ["gh", "run", "download"]:
                    return subprocess.CompletedProcess(args, 1, "", "artifact not found")
                raise AssertionError(args)

            signals = github_ci_signals(repository, runner=runner, which=lambda _cmd: "/usr/bin/gh")

            self.assertEqual("partial", signals["status"])
            self.assertEqual(12, signals["source"]["run_id"])


    def test_github_branch_ci_signals_fetches_matching_head_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/owner/repo.git"], cwd=repository, check=True)
            payload = {
                "schema_version": 2,
                "kind": "ai_harness_ci_signals",
                "summary": {"status": "passed"},
                "path_index": [],
                "signals": [],
            }

            def runner(args, **_kwargs):
                if args[:3] == ["gh", "auth", "status"]:
                    return subprocess.CompletedProcess(args, 0, "", "")
                if args[:3] == ["gh", "run", "list"]:
                    return subprocess.CompletedProcess(args, 0, json.dumps([
                        {"databaseId": 21, "headSha": "old", "conclusion": "success", "status": "completed"},
                        {"databaseId": 22, "headSha": "abc123", "conclusion": "success", "status": "completed", "workflowName": "AI Harness CI"},
                    ]), "")
                if args[:3] == ["gh", "run", "download"]:
                    self.assertEqual("22", str(args[3]))
                    target = Path(args[args.index("--dir") + 1]) / "signals"
                    target.mkdir(parents=True)
                    (target / "ai-harness-signals.json").write_text(json.dumps(payload), encoding="utf-8")
                    return subprocess.CompletedProcess(args, 0, "", "")
                raise AssertionError(args)

            signals = github_branch_ci_signals(repository, "aih/run/feature", expected_head_sha="abc123", runner=runner, which=lambda _cmd: "/usr/bin/gh")

            self.assertEqual("ready", signals["status"])
            self.assertEqual("run_branch", signals["scope"])
            self.assertEqual("abc123", signals["head_sha"])
            self.assertEqual(22, signals["source"]["run_id"])

    def test_compare_ci_signals_classifies_new_existing_and_resolved(self) -> None:
        baseline = {"signals": [
            {"tool": "pytest", "category": "tests", "path": "a.py", "summary": "A", "severity": "error"},
            {"tool": "ruff", "category": "lint", "path": "b.py", "summary": "B", "severity": "warning"},
        ]}
        branch = {"status": "ready", "run": {"conclusion": "success"}, "signals": [
            {"tool": "pytest", "category": "tests", "path": "a.py", "summary": "A", "severity": "error"},
            {"tool": "mypy", "category": "typing", "path": "c.py", "summary": "C", "severity": "warning"},
        ]}

        comparison = compare_ci_signals(baseline, branch)

        self.assertEqual(1, comparison["summary"]["new_signal_count"])
        self.assertEqual(1, comparison["summary"]["existing_signal_count"])
        self.assertEqual(1, comparison["summary"]["resolved_signal_count"])
        self.assertTrue(comparison["summary"]["branch_passed"])

    def test_merged_ci_signals_prefers_ready_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/owner/repo.git"], cwd=repository, check=True)
            workflows = repository / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("name: ci\n", encoding="utf-8")

            with patch("ai_harness.ci_support.github_ci_signals", return_value={
                "status": "ready", "warnings": [], "summary": {"signal_count": 1},
                "path_index": [{"path": "a.py"}], "signals": [{"path": "a.py"}], "source": {"run_id": 1},
            }):
                signals = merged_ci_signals(repository)

            self.assertEqual("ready", signals["status"])
            self.assertIn("github", signals["providers"])
            self.assertEqual(1, signals["summary"]["signal_count"])

    def test_normalize_ci_signal_paths_relativizes_runner_paths_and_drops_unsafe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "ai-harness"
            repository.mkdir()
            (repository / "harness" / "cli").mkdir(parents=True)
            (repository / "harness" / "cli" / "commands.py").write_text("# cli\n", encoding="utf-8")
            payload = {
                "path_index": [
                    {"path": "/home/runner/work/ai-harness/ai-harness/harness/cli/commands.py", "signal_count": 1},
                    {"path": "/tmp/outside.py", "signal_count": 1},
                ],
                "signals": [{
                    "path": "/home/runner/work/ai-harness/ai-harness/harness/cli/commands.py",
                    "evidence": "/home/runner/work/ai-harness/ai-harness/harness/cli/commands.py:3",
                    "agent_hint": "Inspect /home/runner/work/ai-harness/ai-harness/harness/cli/commands.py",
                }],
            }

            normalized = normalize_ci_signal_paths(repository, payload)

            self.assertEqual(["harness/cli/commands.py"], [item["path"] for item in normalized["path_index"]])
            self.assertEqual("harness/cli/commands.py", normalized["signals"][0]["path"])
            self.assertEqual("harness/cli/commands.py:3", normalized["signals"][0]["evidence"])
            self.assertIn("harness/cli/commands.py", normalized["signals"][0]["agent_hint"])
            self.assertIn("raw_path", normalized["signals"][0])

    def test_repository_runtime_context_compacts_recorded_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifacts = ArtifactStore(repository)
            artifacts.write_json("git-run.json", {"is_git_repository": True, "current_branch": "main", "head": "abc", "dirty": False})
            artifacts.write_json("ci-status.json", {"providers": [{"provider": "github", "path": ".github/workflows/ci.yml"}], "warnings": []})
            artifacts.write_json("ci-signals.json", {"status": "partial", "providers": {"github": {"status": "partial"}}, "signals": [{"path": "a.py"}]})

            context = repository_runtime_context(artifacts)

            self.assertEqual("main", context["git"]["current_branch"])
            self.assertEqual("partial", context["ci_signals"]["status"])
            self.assertIn("github", context["ci_signals"]["providers"])

    def test_infer_gitlab_project_from_common_remote_urls(self) -> None:
        https = infer_gitlab_project("https://gitlab.com/group/sub/project.git")
        ssh = infer_gitlab_project("git@gitlab.example.com:group/project.git")

        self.assertIsNotNone(https)
        self.assertEqual("https://gitlab.com/api/v4", https["api_url"])
        self.assertEqual("group/sub/project", https["project_path"])
        self.assertEqual("group%2Fsub%2Fproject", https["project_id"])
        self.assertIsNotNone(ssh)
        self.assertEqual("https://gitlab.example.com/api/v4", ssh["api_url"])
        self.assertEqual("group/project", ssh["project_path"])

    def test_gitlab_ci_signals_fetches_latest_main_harness_quality_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "remote", "add", "origin", "https://gitlab.com/group/project.git"], cwd=repository, check=True)
            payload = {
                "schema_version": 1,
                "kind": "ai_harness_ci_signals",
                "commit": "abc123",
                "summary": {"status": "passed", "signal_count": 0},
                "path_index": [],
                "signals": [],
            }
            responses = [
                _Response([{"id": 7, "sha": "abc123"}]),
                _Response([{"id": 8, "name": "harness_quality"}]),
                _Response(json.dumps(payload).encode("utf-8")),
            ]

            with patch("urllib.request.urlopen", side_effect=responses):
                signals = gitlab_ci_signals(repository, environment={"AI_HARNESS_GITLAB_TOKEN": "token"})

            self.assertEqual("ready", signals["status"])
            self.assertEqual("gitlab", signals["provider"])
            self.assertEqual(7, signals["source"]["pipeline_id"])
            self.assertEqual(8, signals["source"]["job_id"])
            self.assertEqual([], signals["signals"])

    def test_gitlab_ci_signals_reports_unavailable_without_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "remote", "add", "origin", "https://gitlab.com/group/project.git"], cwd=repository, check=True)

            signals = gitlab_ci_signals(repository, environment={})

            self.assertEqual("problem_gathering_info", signals["status"])
            self.assertIn("AI_HARNESS_GITLAB_TOKEN", signals["reason"])

    def test_install_github_template_and_detects_managed_sync(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)

            result = install_ci_templates(repository, "github")
            status = ci_status(repository)

            self.assertEqual((".github/workflows/ai-harness-ci.yml",), result.installed)
            self.assertEqual([], status["warnings"])
            self.assertEqual("github", status["providers"][0]["provider"])
            self.assertTrue(status["providers"][0]["managed"])
            self.assertTrue(status["providers"][0]["in_sync"])

    def test_existing_unmanaged_ci_is_not_overwritten_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            workflow = repository / ".github" / "workflows" / "ai-harness-ci.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("name: custom\n", encoding="utf-8")

            result = install_ci_templates(repository, "github")
            status = ci_status(repository)

            self.assertEqual((), result.installed)
            self.assertEqual((".github/workflows/ai-harness-ci.yml",), result.skipped)
            self.assertIn("not managed", result.warnings[0])
            self.assertEqual("name: custom\n", workflow.read_text(encoding="utf-8"))
            self.assertIn("no sync status", status["warnings"][0])

    def test_ci_preflight_reports_missing_ci_before_signal_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            preflight = ci_preflight(Path(directory))

            self.assertFalse(preflight.ci_ok)
            self.assertEqual("skipped", preflight.signal_status)
            self.assertIn("No CI pipeline", preflight.ci_warnings[0])

    def test_ci_preflight_accepts_managed_ci_and_ready_signals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            install_ci_templates(repository, "github")
            with patch("ai_harness.ci_support.merged_ci_signals", return_value={
                "status": "ready",
                "warnings": [],
                "summary": {"signal_count": 0},
                "path_index": [],
                "signals": [],
            }):
                preflight = ci_preflight(repository)

            self.assertTrue(preflight.ci_ok)
            self.assertTrue(preflight.signal_ok)

    def test_no_ci_status_yields_warning_and_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifacts = ArtifactStore(repository)
            artifacts.write_json("ci-status.json", ci_status(repository))

            observations = ci_observations_from_artifact(artifacts)

            self.assertIn("No CI pipeline", artifacts.read_json("ci-status.json")["warnings"][0])
            self.assertEqual("ci", observations[0]["kind"])
            self.assertEqual("none", observations[0]["provider"])

    def test_ci_signal_paths_are_repository_observations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifacts = ArtifactStore(repository)
            artifacts.write_json("ci-status.json", {"providers": [{"provider": "github", "path": ".github/workflows/ci.yml", "managed": True, "in_sync": True}]})
            artifacts.write_json("ci-signals.json", {
                "path_index": [
                    {"path": "harness/cli/commands.py", "max_severity": "warning", "signal_count": 2},
                    {"path": "/runner/work/project/harness/cli/ui.py", "max_severity": "warning", "signal_count": 1},
                ],
                "signals": [{
                    "path": "harness/cli/commands.py",
                    "tool": "ruff",
                    "category": "lint",
                    "severity": "warning",
                    "status": "unknown",
                    "summary": "I001 import block is unsorted",
                    "evidence": "harness/cli/commands.py:3",
                    "agent_hint": "Inspect the launcher command module.",
                }],
            })

            observations = ci_observations_from_artifact(artifacts)

            ci_signal_paths = [item.get("path") for item in observations if item.get("kind") == "ci_signal"]
            self.assertEqual(["harness/cli/commands.py", "harness/cli/commands.py"], ci_signal_paths)
            self.assertEqual("warning", observations[1]["max_severity"])
            self.assertIn("I001 import block", observations[2]["matches"][0])

    def test_branch_creation_is_opt_in_and_skips_dirty_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=A", "commit", "--allow-empty", "-m", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL)
            (repository / "dirty.txt").write_text("dirty\n", encoding="utf-8")

            metadata = maybe_create_run_branch(repository, "abcdef123456", "Fix tests", "create")

            self.assertIsNone(metadata["created_branch"])
            self.assertTrue(metadata["dirty"])
            self.assertIn("skipped", metadata["warnings"][-1])

    def test_branch_creation_creates_remote_first_and_tracks_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "work"
            remote = root / "origin.git"
            repository.mkdir()
            subprocess.run(["git", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
            subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repository, check=True)
            subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=A", "commit", "--allow-empty", "-m", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL)
            (repository / ".ai-harness" / "artifacts").mkdir(parents=True)

            metadata = maybe_create_run_branch(repository, "abcdef123456", "Fix tests", "create")

            branch = "aih/abcdef12/fix-tests"
            self.assertEqual(branch, metadata["created_branch"])
            self.assertEqual(branch, metadata["current_branch"])
            self.assertFalse(metadata["dirty"])
            subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "--verify", f"refs/heads/{branch}"], check=True, stdout=subprocess.DEVNULL)
            upstream = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=repository, text=True).strip()
            self.assertEqual(f"origin/{branch}", upstream)

    def test_branch_creation_without_origin_does_not_create_local_branch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=A", "commit", "--allow-empty", "-m", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL)
            original_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repository, text=True).strip()

            metadata = maybe_create_run_branch(repository, "abcdef123456", "Fix tests", "create")

            self.assertIsNone(metadata["created_branch"])
            self.assertEqual(original_branch, subprocess.check_output(["git", "branch", "--show-current"], cwd=repository, text=True).strip())
            self.assertIn("could not be created on origin", metadata["warnings"][-1])

    def test_record_branch_ci_artifacts_records_comparison_and_passes_when_branch_ci_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=A", "commit", "--allow-empty", "-m", "init"], cwd=repository, check=True, stdout=subprocess.DEVNULL)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
            artifacts = ArtifactStore(repository)
            state = StateStore(repository, artifacts)
            state.save(RunState(
                "run", "request", "FINALIZING", Strategy.NON_CODE_STUB, Mode.NON_CODE,
                "ideation", Complexity.LOW, "local",
            ))
            artifacts.write_json("git-run.json", {"created_branch": "aih/run/request", "head": head})
            state.record_artifact("git-run.json", "INITIALIZING")
            artifacts.write_json("ci-signals.json", {"status": "ready", "signals": [], "summary": {"status": "passed"}})
            state.record_artifact("ci-signals.json", "INITIALIZING")
            branch_payload = {
                "status": "ready",
                "scope": "run_branch",
                "head_sha": head,
                "run": {"conclusion": "success"},
                "summary": {"status": "passed"},
                "signals": [],
                "warnings": [],
            }
            with patch("ai_harness.ci_support.github_branch_ci_signals", return_value=branch_payload):
                result = record_branch_ci_artifacts(repository, artifacts, state, github_ci_mode="branch", warnings=[])

            self.assertEqual("passed", result["status"])
            self.assertIn("ci/run-branch-signals.json", state.load().artifacts)
            self.assertIn("ci/comparison.json", state.load().artifacts)

    def test_recorded_ci_artifact_can_be_state_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifacts = ArtifactStore(repository)
            state = StateStore(repository, artifacts)
            state.save(RunState(
                "run", "request", "INITIALIZING", Strategy.NON_CODE_STUB, Mode.NON_CODE,
                "ideation", Complexity.LOW, "local",
            ))
            warnings: list[str] = []
            record_ci_and_git_artifacts(
                repository,
                artifacts,
                state,
                run_id="run",
                request="request",
                branch_mode="off",
                warnings=warnings,
            )

            self.assertIn("ci-status.json", state.load().artifacts)
            self.assertIn("git-run.json", state.load().artifacts)
            self.assertIn("ci-signals.json", state.load().artifacts)
            self.assertIn(artifacts.read_json("ci-signals.json")["status"], {"unavailable", "problem_gathering_info"})


if __name__ == "__main__":
    unittest.main()
