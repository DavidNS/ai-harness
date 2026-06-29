from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Mapping

from ai_harness.config import HarnessConfig
from ai_harness.errors import HarnessError
from ai_harness.orchestrator import Orchestrator
from ai_harness.output import render_result
from ai_harness.pipeline.non_code import PHASES
from ai_harness.providers.base import ProviderResult
from ai_harness.strategy import finalize_strategy_decision, select_strategy
from ai_harness.stores.runtime import RunLock
from tests.fixtures.flow import run_with_flow, run_with_route


class RejectingProvider:
    def run_prompt(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("the non-code pipeline must not invoke a provider")


class RoutingProvider:
    def __init__(self) -> None:
        self.permissions: Mapping[str, object] | None = None

    def run_prompt(self, prompt, *, cwd, permissions=None, progress=None):
        del prompt, cwd, progress
        self.permissions = permissions
        return ProviderResult(
            '{"mode":"non_code","intent":"unknown","confidence":0.8}',
            "", 0, 0.01,
        )


class FailingImplementProvider:
    def run_prompt(self, prompt, *, cwd, permissions=None, progress=None):
        del cwd, permissions
        if "# Implement Worker v1" in prompt:
            if progress is not None:
                progress("stderr", "codex auth failed\n")
            return ProviderResult("", "codex auth failed", 1, 0.01)
        return ProviderResult(
            '{"mode":"code","intent":"modify_code","confidence":0.8}',
            "",
            0,
            0.01,
        )


class LegacyFailingImplementProvider:
    def run_prompt(self, prompt, *, cwd, permissions=None):
        del cwd, permissions
        if "# Implement Worker v1" in prompt:
            return ProviderResult("", "legacy provider failed", 1, 0.01)
        return ProviderResult(
            '{"mode":"code","intent":"modify_code","confidence":0.8}',
            "",
            0,
            0.01,
        )


class CapturingImplementProvider:
    def __init__(self) -> None:
        self.implement_prompt = ""
        self.implement_permissions: Mapping[str, object] | None = None

    def run_prompt(self, prompt, *, cwd, permissions=None, progress=None):
        del cwd, progress
        if "# Implement Worker v1" in prompt:
            self.implement_prompt = prompt
            self.implement_permissions = permissions
            return ProviderResult("", "stop after capture", 1, 0.01)
        return ProviderResult(
            '{"mode":"code","intent":"modify_code","confidence":0.8}',
            "",
            0,
            0.01,
        )


class OrchestratorIntegrationTests(unittest.TestCase):
    def test_ambiguous_routing_waits_for_user_without_provider_classification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = RoutingProvider()
            result = Orchestrator(
                Path(directory),
                HarnessConfig(provider="local", timeout_seconds=17),
                provider,
            ).run("Make something useful")

            self.assertEqual("waiting_for_user", result.outcome)
            assert result.control is not None
            self.assertEqual("ROUTING", result.control["request"]["origin_phase"])
            self.assertIn("code", result.control["request"]["scores"])
            self.assertIsNone(provider.permissions)

    def test_heuristic_code_route_still_waits_for_manual_route_selection_with_scores(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs" / "explorer" / "improvements" / "slash-command-suggestions" / "improvement.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("# Improvement: Slash Command Suggestions\n", encoding="utf-8")

            result = Orchestrator(
                repository,
                HarnessConfig(provider="local", timeout_seconds=17),
                RoutingProvider(),
            ).run("Implement docs/explorer/improvements/slash-command-suggestions/improvement.md")

            self.assertEqual("waiting_for_user", result.outcome)
            assert result.control is not None
            request = result.control["request"]
            self.assertEqual("ROUTING", request["origin_phase"])
            self.assertIn("code", request["scores"])
            self.assertIn("non_code", request["scores"])
            self.assertIn("code", request["ranked_paths"])

    def test_provider_failure_stderr_is_persisted_in_attempt_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            progress: list[str] = []
            with self.assertRaises(HarnessError):
                run_with_flow(
                    Orchestrator(
                        repository,
                        HarnessConfig(provider="local", max_attempts=1),
                        FailingImplementProvider(),
                        progress=progress.append,
                    ),
                    "Update README.md",
                    "sdd_low",
                )

            self.assertIn("[implement stderr] codex auth failed", progress)
            attempt = json.loads(
                (repository / ".ai-harness" / "artifacts" / "current" / "attempts" / "T1" / "1.json").read_text()
            )
            self.assertEqual("failed", attempt["status"])
            self.assertIn("phase implement provider exited with 1", attempt["failure"])
            self.assertIn("codex auth failed", attempt["implementation"]["stderr"])
            self.assertFalse((repository / ".ai-harness" / "artifacts" / "current" / "jobs" / "J0001" / "debug-before.json").exists())
            self.assertFalse((repository / ".ai-harness" / "artifacts" / "current" / "jobs" / "J0001" / "debug-after.json").exists())


    def test_worker_debug_mode_records_git_evidence_around_worker_invocation(self) -> None:
        previous = os.environ.get("AI_HARNESS_WORKER_DEBUG")
        os.environ["AI_HARNESS_WORKER_DEBUG"] = "1"
        try:
            with tempfile.TemporaryDirectory() as directory:
                repository = Path(directory)
                with self.assertRaises(HarnessError):
                    run_with_flow(
                        Orchestrator(
                            repository,
                            HarnessConfig(provider="local", max_attempts=1),
                            FailingImplementProvider(),
                        ),
                        "Update README.md",
                        "sdd_low",
                    )

                job = repository / ".ai-harness" / "artifacts" / "current" / "jobs" / "J0001"
                before = json.loads((job / "debug-before.json").read_text(encoding="utf-8"))
                after = json.loads((job / "debug-after.json").read_text(encoding="utf-8"))
                self.assertEqual("before", before["stage"])
                self.assertEqual("after", after["stage"])
                self.assertEqual("implement", before["phase"])
                self.assertEqual("implement", after["phase"])
                self.assertEqual("J0001", before["job_id"])
                self.assertEqual(3, len(before["commands"]))
                self.assertEqual(["git", "status", "--short", "--untracked-files=all"], before["commands"][0]["command"])
                self.assertEqual(["git", "diff", "--name-status", "--"], after["commands"][2]["command"])
        finally:
            if previous is None:
                os.environ.pop("AI_HARNESS_WORKER_DEBUG", None)
            else:
                os.environ["AI_HARNESS_WORKER_DEBUG"] = previous

    def test_legacy_provider_signature_still_runs_without_progress_callback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            with self.assertRaises(HarnessError) as caught:
                run_with_flow(
                    Orchestrator(
                        repository,
                        HarnessConfig(provider="local", max_attempts=1),
                        LegacyFailingImplementProvider(),
                    ),
                    "Update README.md",
                    "sdd_low",
                )

            self.assertIn("phase implement provider exited with 1", str(caught.exception))
            attempt = json.loads(
                (repository / ".ai-harness" / "artifacts" / "current" / "attempts" / "T1" / "1.json").read_text()
            )
            self.assertIn("legacy provider failed", attempt["implementation"]["stderr"])

    def test_simple_task_includes_referenced_markdown_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            (repository / "tests").mkdir()
            draft = repository / "draft-improvements" / "non-code-provider-pass-through.md"
            draft.parent.mkdir()
            draft.write_text(
                "# Non-Code Provider Pass-Through\n\nRoute non-code requests to the provider.\n",
                encoding="utf-8",
            )
            provider = CapturingImplementProvider()

            with self.assertRaises(HarnessError):
                run_with_flow(
                    Orchestrator(
                        repository,
                        HarnessConfig(provider="local", max_attempts=1),
                        provider,
                    ),
                    "Fix a typo in draft-improvements/non-code-provider-pass-through.md",
                    "sdd_low",
                )

            tasks = json.loads((repository / ".ai-harness" / "artifacts" / "current" / "tasks.json").read_text())
            self.assertEqual(
                "Implement the improvement described by draft-improvements/non-code-provider-pass-through.md",
                tasks["tasks"][0]["title"],
            )
            self.assertIn("Route non-code requests to the provider.", provider.implement_prompt)
            self.assertEqual([[sys.executable, "-c", "print('syntax gate skipped outside git')"]], tasks["tasks"][0]["focused_tests"])
            broader = tasks["tasks"][0]["broader_tests"]
            self.assertTrue(any(command[-2:] == ["discover", "tests/integration"] for command in broader))
            self.assertTrue(any(command[-1] == "tests.acceptance.test_end_to_end" for command in broader))
            self.assertIsNotNone(provider.implement_permissions)
            assert provider.implement_permissions is not None
            self.assertIsNone(provider.implement_permissions["timeout_seconds"])

    def test_preselected_strategy_override_is_persisted_for_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            recommendation = select_strategy("Update orchestrator routing")
            decision = finalize_strategy_decision(recommendation, answer="simple", prompted=True)

            provider = CapturingImplementProvider()
            waiting = Orchestrator(
                repository,
                HarnessConfig(provider="local", max_attempts=1),
                provider,
            ).run("Fix typo in README.md", strategy_decision=decision)
            self.assertEqual("waiting_for_user", waiting.outcome)
            assert waiting.control is not None

            with self.assertRaises(HarnessError):
                Orchestrator(
                    repository,
                    HarnessConfig(provider="local", max_attempts=1),
                    provider,
                ).run(
                    "Fix typo in README.md",
                    resume_run_id=waiting.run_id,
                    decision_answer=json.dumps({
                        "schema_version": 1,
                        "kind": "decision_answer",
                        "decision_id": waiting.control["decision_id"],
                        "answer": "Use code.",
                        "selected_option": "code",
                    }),
                )

            strategy = json.loads(
                (repository / ".ai-harness" / "artifacts" / "current" / "strategy.json").read_text()
            )
            self.assertEqual("SDD", strategy["strategy"])
            self.assertEqual("LOW", strategy["complexity"])
            self.assertEqual("SDD", strategy["recommended_strategy"])
            self.assertEqual("MEDIUM", strategy["recommended_complexity"])
            self.assertTrue(strategy["prompted"])
            self.assertTrue(strategy["overridden"])
            self.assertEqual("prompt_override", strategy["selection_source"])
            self.assertEqual("simple", strategy["override_text"])

    def test_non_code_pipeline_completes_without_modifying_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            result = run_with_route(
                Orchestrator(repository, HarnessConfig(provider="local"), RejectingProvider()),
                "Research and compare competitor positioning and customer segments",
                "non_code",
            )

            archived_state = json.loads((result.snapshot_path / "state.json").read_text())
            rendered = render_result(result)
            self.assertEqual(PHASES, result.phases)
            self.assertEqual("non-code stub", result.outcome)
            self.assertTrue(result.snapshot_path.is_dir())
            self.assertEqual("completed", archived_state["status"])
            self.assertEqual("COMPLETED", archived_state["current_phase"])
            self.assertEqual(list(PHASES), archived_state["completed_phases"])
            self.assertNotIn("tasks.json", result.artifacts)
            headings = ["## Router", "## Strategy", "## Pipeline", "## Artifacts", "## Result"]
            self.assertEqual(sorted(rendered.index(item) for item in headings), [rendered.index(item) for item in headings])
            with RunLock(repository):
                pass


if __name__ == "__main__":
    unittest.main()
