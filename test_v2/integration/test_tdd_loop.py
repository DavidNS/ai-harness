from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness_v2.adapters.git import FilesystemRepositoryAdapter
from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.adapters.tools import SubprocessToolRunner
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.bundle_artifacts import BundleRuntimeConfig
from harness_v2.backend.application.bundle_orchestration import BundleOrchestrator
from harness_v2.backend.application.bundle_registry import default_bundle_registry
from harness_v2.backend.application.tdd_loop import TddLoopService, parse_tdd_review
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.domain.tasks import TaskStatus, TaskSummary
from harness_v2.backend.ports.model_provider import ModelProviderRequest, ModelProviderResult


class StaticClock:
    def now_iso(self) -> str:
        return "2026-07-01T00:00:00+00:00"


class TddFixtureProvider:
    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        payload = _payload(request.prompt)
        task_id = str(payload.get("task_id"))
        if task_id == "tdd_create_test":
            (request.working_directory / "test_feature.py").write_text(
                "import unittest\n"
                "from feature import answer\n\n"
                "class FeatureTests(unittest.TestCase):\n"
                "    def test_answer(self):\n"
                "        self.assertEqual(42, answer())\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n",
                encoding="utf-8",
            )
            return ModelProviderResult("created test", "", 0, 0.0)
        if task_id == "tdd_implement":
            (request.working_directory / "feature.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
            return ModelProviderResult("implemented", "", 0, 0.0)
        if task_id == "tdd_review":
            return ModelProviderResult("# Review v1\n## Verdict\nAPPROVE\n## Findings\n- Looks good.\n", "", 0, 0.0)
        return ModelProviderResult("", f"unexpected task {task_id}", 7, 0.0)


class ScopeViolationProvider(TddFixtureProvider):
    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        payload = _payload(request.prompt)
        if payload.get("task_id") == "tdd_implement":
            (request.working_directory / "outside.txt").write_text("escaped\n", encoding="utf-8")
            return ModelProviderResult("changed outside", "", 0, 0.0)
        return super().run(request)


class NeverFixesProvider(TddFixtureProvider):
    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        payload = _payload(request.prompt)
        if payload.get("task_id") == "tdd_implement":
            return ModelProviderResult("no change", "", 0, 0.0)
        return super().run(request)


class ReviewEscalatesProvider(TddFixtureProvider):
    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        payload = _payload(request.prompt)
        if payload.get("task_id") == "tdd_review":
            return ModelProviderResult(
                "# Review v1\n"
                "## Verdict\n"
                "REQUEST_CHANGES\n"
                "## Escalation Category\n"
                "DESIGN_GAP\n"
                "## Findings\n"
                "- Design needs revision.\n",
                "",
                0,
                0.0,
            )
        return super().run(request)


class TddLoopIntegrationTests(unittest.TestCase):
    def test_tdd_bundle_completes_controlled_fixture_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "feature.py").write_text("def answer():\n    return 0\n", encoding="utf-8")
            state, artifacts, orchestrator = _orchestrator(root, TddFixtureProvider(), allow_mutation=True)
            _seed_tdd_run(state, artifacts)

            result = orchestrator.execute_current_phase("run-1")

            self.assertIsNotNone(result)
            self.assertEqual("RUNNING", result.run.status)
            self.assertEqual("KNOWLEDGE_EXTRACT_TDD", result.run.current_phase)
            self.assertEqual("def answer():\n    return 42\n", (root / "feature.py").read_text(encoding="utf-8"))
            persisted = state.get("run-1")
            self.assertEqual(TaskStatus.COMPLETED, persisted.tasks[0].status)
            self.assertEqual(1, persisted.tasks[0].attempts)
            self.assertIn(b'"blocked_reason": null', artifacts.read("run-1", "published/tdd-results.json"))

    def test_tdd_bundle_without_mutation_permission_escalates_validation_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "feature.py").write_text("def answer():\n    return 0\n", encoding="utf-8")
            state, artifacts, orchestrator = _orchestrator(root, TddFixtureProvider(), allow_mutation=False)
            _seed_tdd_run(state, artifacts)

            result = orchestrator.execute_current_phase("run-1")

            self.assertIsNotNone(result)
            self.assertEqual("FAILED", result.run.status)
            self.assertIn("TDD_BUNDLE_ESCALATION_FAILED", [error.code for error in state.get("run-1").errors])
            self.assertIn(b"mutation-enabled", artifacts.read("run-1", "published/tdd-results.json"))

    def test_tdd_scope_violation_rolls_back_and_rewinds_to_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "feature.py").write_text("def answer():\n    return 0\n", encoding="utf-8")
            state, _artifacts, orchestrator = _orchestrator(root, ScopeViolationProvider(), allow_mutation=True)
            _seed_tdd_run(state, _artifacts)

            result = orchestrator.execute_current_phase("run-1")

            self.assertIsNotNone(result)
            self.assertEqual("RUNNING", result.run.status)
            self.assertEqual("TASKS_BUNDLE", result.run.current_phase)
            self.assertFalse((root / "outside.txt").exists())
            self.assertEqual("def answer():\n    return 0\n", (root / "feature.py").read_text(encoding="utf-8"))
            self.assertEqual((), state.get("run-1").tasks)

    def test_tdd_retries_until_max_attempts_then_escalates_implementation_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "feature.py").write_text("def answer():\n    return 0\n", encoding="utf-8")
            state, artifacts, orchestrator = _orchestrator(root, NeverFixesProvider(), allow_mutation=True, max_attempts=2)
            _seed_tdd_run(state, artifacts)

            result = orchestrator.execute_current_phase("run-1")

            self.assertIsNotNone(result)
            self.assertEqual("FAILED", result.run.status)
            self.assertIn("IMPLEMENTATION_BLOCKED", [getattr(event, "category", None) for event in result.events])
            persisted = state.get("run-1")
            self.assertIn("did not pass within 2 attempts", persisted.errors[0].message)
            self.assertEqual(2, persisted.tasks[0].attempts)
            self.assertEqual("def answer():\n    return 0\n", (root / "feature.py").read_text(encoding="utf-8"))

    def test_tdd_review_category_escalates_to_policy_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "feature.py").write_text("def answer():\n    return 0\n", encoding="utf-8")
            state, artifacts, orchestrator = _orchestrator(root, ReviewEscalatesProvider(), allow_mutation=True)
            _seed_tdd_run(state, artifacts)

            result = orchestrator.execute_current_phase("run-1")

            self.assertIsNotNone(result)
            self.assertEqual("RUNNING", result.run.status)
            self.assertEqual("DESIGN_BUNDLE", result.run.current_phase)
            self.assertEqual("def answer():\n    return 0\n", (root / "feature.py").read_text(encoding="utf-8"))
            self.assertEqual((), state.get("run-1").tasks)

    def test_tdd_worker_capabilities_are_repo_wide_write_for_cli_projection(self) -> None:
        for task_id in ("tdd_create_test", "tdd_implement", "tdd_review"):
            with self.subTest(task_id=task_id):
                spec = FileWorkerResourceStore().get(task_id)
                self.assertEqual(1, len(spec.capabilities.paths))
                self.assertEqual("**", spec.capabilities.paths[0].pattern)
                self.assertEqual("write", spec.capabilities.paths[0].mode)

    def test_review_parser_accepts_approve_and_rejects_bad_verdict(self) -> None:
        self.assertEqual(
            {"verdict": "REQUEST_CHANGES", "findings": ["Needs work."], "escalation_category": None},
            parse_tdd_review("# Review v1\n## Verdict\nREQUEST_CHANGES\n## Findings\n- Needs work.\n"),
        )
        self.assertEqual(
            {"verdict": "REQUEST_CHANGES", "findings": ["Needs design."], "escalation_category": "DESIGN_GAP"},
            parse_tdd_review(
                "# Review v1\n"
                "## Verdict\n"
                "REQUEST_CHANGES\n"
                "## Escalation Category\n"
                "DESIGN_GAP\n"
                "## Findings\n"
                "- Needs design.\n"
            ),
        )
        with self.assertRaises(Exception):
            parse_tdd_review("# Review v1\n## Verdict\nMAYBE\n")


def _orchestrator(
    root: Path,
    provider: object,
    *,
    allow_mutation: bool,
    max_attempts: int = 3,
) -> tuple[InMemoryStateStore, InMemoryArtifactStore, BundleOrchestrator]:
    state = InMemoryStateStore()
    artifacts = InMemoryArtifactStore()
    worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
    repository = FilesystemRepositoryAdapter()
    tdd = TddLoopService(repository=repository, rollback=repository, tool_runner=SubprocessToolRunner(), max_attempts=max_attempts)
    registry = default_bundle_registry(tdd_loop=tdd)
    orchestrator = BundleOrchestrator(
        state,
        artifacts,
        worker,
        StaticClock(),
        registry,
        BundleRuntimeConfig(working_directory=root, allow_repository_mutation=allow_mutation, tdd_command_timeout_seconds=5),
    )
    return state, artifacts, orchestrator


def _seed_tdd_run(state: InMemoryStateStore, artifacts: InMemoryArtifactStore) -> None:
    tasks = (TaskSummary("T1", "Implement answer", TaskStatus.PENDING),)
    state.save(
        RunRecord(
            run_id="run-1",
            request="Implement answer",
            status=RunStatus.RUNNING,
            strategy=RunStrategy.SDD,
            current_phase=PhaseName.TDD_BUNDLE,
            completed_phases=(
                PhaseName.EXPLORE_BUNDLE,
                PhaseName.KNOWLEDGE_EXTRACT_EXPLORE,
                PhaseName.PROPOSAL_BUNDLE,
                PhaseName.SPEC_BUNDLE,
                PhaseName.DESIGN_BUNDLE,
                PhaseName.TASKS_BUNDLE,
            ),
            tasks=tasks,
        )
    )
    artifacts.write("run-1", "tasks.json", json.dumps({
        "schema_version": 1,
        "phase": "tasks",
        "tasks": [{
            "id": "T1",
            "title": "Implement answer",
            "depends_on": [],
            "acceptance_criteria": ["answer returns 42"],
            "touched_paths": ["feature.py", "test_feature.py"],
            "focused_tests": [["python3", "-B", "-m", "unittest", "test_feature.py"]],
            "broader_tests": [],
            "status": "pending",
        }],
    }).encode("utf-8"))


def _payload(prompt: str) -> dict[str, object]:
    marker = "Return only the required artifact. Controller inputs:"
    raw = prompt.rsplit(marker, 1)[1].strip()
    value = json.loads(raw)
    assert isinstance(value, dict)
    return value


if __name__ == "__main__":
    unittest.main()
