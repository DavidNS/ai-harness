from __future__ import annotations

import unittest

from test_v2.support.model_providers import FakeModelProvider
from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from pathlib import Path

from harness_v2.backend.application.worker_service import WorkerTaskRequest, WorkerTaskService
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.model_provider import ModelProviderResult, ModelSelection


class WorkerServiceIntegrationTests(unittest.TestCase):
    def test_worker_service_writes_worker_artifacts_for_current_phase(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        state.save(RunRecord("run-1", "Fix tests", RunStatus.RUNNING, root_bundle=BundleName.EXPLORE_BUNDLE, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING))
        provider = FakeModelProvider([ModelProviderResult('{"schema_version":1}', "", 0, 0.0)])
        service = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())

        result = service.execute(WorkerTaskRequest("run-1", BundleName.EXPLORE_BUNDLE, PhaseName.EXPLORE_REQUEST_UNDERSTANDING, "explore_request_profile", {"request": "Fix"}, Path.cwd(), ModelSelection("codex")))

        self.assertTrue(result.provider_succeeded)
        self.assertTrue(artifacts.list("run-1"))


if __name__ == "__main__":
    unittest.main()
