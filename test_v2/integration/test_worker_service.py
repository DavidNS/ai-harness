from __future__ import annotations

import json
from pathlib import Path
import unittest

from harness_v2.adapters.models import FakeModelProvider
from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.backend.application.contracts import InvalidRunStateError, RunNotFoundError
from harness_v2.backend.application.worker_service import WorkerTaskRequest, WorkerTaskService
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.model_provider import (
    CapabilityProjection,
    ModelProviderResult,
    ModelSelection,
    PathCapability,
    TimeoutPolicy,
    TruncationPolicy,
)
from harness_v2.backend.ports.worker_resources import WorkerResourceSpec


def running_run(run_id: str = "run-1", phase: PhaseName = PhaseName.EXPLORE_BUNDLE) -> RunRecord:
    completed = (PhaseName.EXPLORE_BUNDLE, PhaseName.KNOWLEDGE_EXTRACT_EXPLORE) if phase == PhaseName.PROPOSAL_BUNDLE else ()
    return RunRecord(run_id, "Fix tests", RunStatus.RUNNING, RunStrategy.SDD, current_phase=phase, completed_phases=completed)


def request(run_id: str = "run-1", phase: PhaseName = PhaseName.EXPLORE_BUNDLE, task_id: str = "task-1") -> WorkerTaskRequest:
    return WorkerTaskRequest(
        run_id=run_id,
        phase=phase,
        task_id=task_id,
        inputs={"mode": "malformed"},
        working_directory=Path.cwd(),
        model=ModelSelection("fake", "test"),
        timeout=TimeoutPolicy(5),
        truncation=TruncationPolicy(512),
    )


class StaticWorkerResources:
    def get(self, task_id: str) -> WorkerResourceSpec:
        return WorkerResourceSpec(
            task_id=task_id,
            playbook_markdown="# Worker\nUse the test worker.",
            prompt_markdown="# Prompt\nReturn the requested output.",
            capabilities=CapabilityProjection(paths=(PathCapability("src/**", "read"),)),
        )


class WorkerTaskServiceIntegrationTests(unittest.TestCase):
    def test_running_phase_requests_worker_and_stores_request_and_raw_result_artifacts(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        provider = FakeModelProvider([ModelProviderResult("not json", "", 0, 0.01)])
        state.save(running_run())
        service = WorkerTaskService(state, artifacts, provider, StaticWorkerResources())

        result = service.execute(request())

        self.assertTrue(result.provider_succeeded)
        self.assertEqual("workers/EXPLORE_BUNDLE/task-1/request.json", result.request_artifact_id)
        self.assertEqual("workers/EXPLORE_BUNDLE/task-1/result.json", result.result_artifact_id)
        stored_request = json.loads(artifacts.read("run-1", result.request_artifact_id))
        stored_result = json.loads(artifacts.read("run-1", result.result_artifact_id))
        self.assertEqual("task-1", stored_request["task_id"])
        self.assertEqual({"mode": "malformed"}, stored_request["inputs"])
        self.assertEqual("fake", stored_request["model"]["provider"])
        self.assertEqual([{"pattern": "src/**", "mode": "read"}], stored_request["capabilities"]["paths"])
        self.assertIn("# Worker", stored_request["prompt"])
        self.assertIn('"task_id": "task-1"', stored_request["prompt"])
        self.assertEqual("not json", stored_result["stdout"])
        self.assertEqual([stored_request["prompt"]], [call.prompt for call in provider.requests])

    def test_worker_task_fails_closed_for_missing_inactive_or_wrong_phase_runs(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        service = WorkerTaskService(state, artifacts, FakeModelProvider(), StaticWorkerResources())

        with self.assertRaises(RunNotFoundError):
            service.execute(request())

        state.save(RunRecord("completed", "Fix", RunStatus.COMPLETED, RunStrategy.EXPLORE_BUNDLE, completed_phases=(PhaseName.EXPLORE_BUNDLE,)))
        with self.assertRaises(InvalidRunStateError):
            service.execute(request("completed", PhaseName.EXPLORE_BUNDLE))

        state.save(running_run("run-2", PhaseName.PROPOSAL_BUNDLE))
        with self.assertRaises(InvalidRunStateError):
            service.execute(request("run-2", PhaseName.EXPLORE_BUNDLE))

    def test_worker_task_rejects_unsafe_task_ids_before_artifact_write(self) -> None:
        with self.assertRaises(ValueError):
            request(task_id="../escape")
        with self.assertRaises(ValueError):
            request(task_id="nested/task")


if __name__ == "__main__":
    unittest.main()
