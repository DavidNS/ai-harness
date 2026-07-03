from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness_v2.adapters.git.repository import FilesystemRepositoryAdapter
from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryKnowledgePatchStore, InMemoryStateStore
from harness_v2.adapters.tools.subprocess_runner import SubprocessToolRunner
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.bundle_artifacts import BundleRuntimeConfig
from harness_v2.backend.application.contracts import ResumeRun
from harness_v2.backend.application.phase_executor import PhaseExecutor, default_phase_function_registry
from harness_v2.backend.application.run_orchestrator import RunOrchestrator
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.domain.tasks import TaskSummary
from harness_v2.backend.ports.model_provider import ModelProviderResult
from test_v2.support.model_providers import FakeModelProvider, ScriptedModelProvider
from test_v2.support.runtime import StaticClock, StaticIdGenerator
from harness_v2.backend.application.tdd_contracts import parse_tdd_review


def _tasks_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "tasks",
        "tasks": [{
            "id": "T1",
            "title": "Implement feature",
            "depends_on": [],
            "acceptance_criteria": ["feature.py contains ready"],
            "touched_paths": ["feature.py"],
            "focused_tests": [["python3", "-c", "from pathlib import Path; assert Path('feature.py').read_text() == 'ready\\n'"]],
            "broader_tests": [],
            "status": "pending",
        }],
    }


def _orchestrator(root: Path, *, allow_mutation: bool, provider: object) -> tuple[RunOrchestrator, InMemoryStateStore, InMemoryArtifactStore]:
    state = InMemoryStateStore()
    artifacts = InMemoryArtifactStore()
    knowledge = InMemoryKnowledgePatchStore()
    worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
    registry = default_phase_function_registry()
    repository = FilesystemRepositoryAdapter()
    phase_executor = PhaseExecutor(
        artifacts,
        worker,
        StaticClock(),
        registry,
        BundleRuntimeConfig(
            working_directory=root,
            allow_repository_mutation=allow_mutation,
            repository=repository,
            rollback=repository,
            tool_runner=SubprocessToolRunner(),
        ),
        knowledge_patches=knowledge,
    )
    service = RunOrchestrator(
        state,
        StaticIdGenerator(),
        phase_executor=phase_executor,
        clock=StaticClock(),
        artifact_store=artifacts,
        invalidation_rules=registry.invalidation_rules(),
        knowledge_patches=knowledge,
    )
    state.save(RunRecord(
        "run-1",
        "Implement feature",
        RunStatus.RUNNING,
        root_bundle=BundleName.TDD_BUNDLE,
        current_phase=PhaseName.TDD_EXECUTE,
        tasks=(TaskSummary("T1", "Implement feature"),),
    ))
    artifacts.write("run-1", "tasks.json", (json.dumps(_tasks_document(), sort_keys=True) + "\n").encode("utf-8"))
    return service, state, artifacts


class TddPhaseIntegrationTests(unittest.TestCase):
    def test_tdd_execute_completes_task_and_handoff_finishes_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, state, artifacts = _orchestrator(root, allow_mutation=True, provider=ScriptedModelProvider())

            executed = service.execute(ResumeRun("run-1"))

            self.assertEqual("RUNNING", executed.run.status)
            self.assertEqual("TDD_HANDOFF", executed.run.current_step.phase)
            self.assertEqual("COMPLETED", state.get("run-1").tasks[0].status.value)
            self.assertEqual("ready\n", (root / "feature.py").read_text(encoding="utf-8"))
            results = json.loads(artifacts.read("run-1", "published/tdd-results.json").decode("utf-8"))
            self.assertIsNone(results["blocked_reason"])

            completed = service.execute(ResumeRun("run-1"))

            self.assertEqual("COMPLETED", completed.run.status)
            handoff = json.loads(artifacts.read("run-1", "published/tdd-handoff.json").decode("utf-8"))
            self.assertEqual(["T1"], handoff["completed_tasks"])

    def test_tdd_execute_without_mutation_permission_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service, state, artifacts = _orchestrator(Path(directory), allow_mutation=False, provider=FakeModelProvider([ModelProviderResult("", "", 0, 0.0)]))

            result = service.execute(ResumeRun("run-1"))

            self.assertEqual("FAILED", result.run.status)
            self.assertEqual("TDD_EXECUTE", result.run.current_step.phase)
            self.assertEqual("FAILED", state.get("run-1").status.value)
            results = json.loads(artifacts.read("run-1", "published/tdd-results.json").decode("utf-8"))
            self.assertIn("mutation-enabled", results["blocked_reason"])

    def test_tdd_review_parser_requires_structured_evidence(self) -> None:
        review = parse_tdd_review(json.dumps({
            "schema_version": 1,
            "kind": "tdd_review",
            "verdict": "APPROVE",
            "findings": ["ok"],
            "acceptance_criteria": ["criterion"],
            "test_evidence": {"focused": "passed"},
        }))

        self.assertEqual("APPROVE", review["verdict"])
        self.assertEqual({"focused": "passed"}, review["test_evidence"])


if __name__ == "__main__":
    unittest.main()
