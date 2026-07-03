from __future__ import annotations

import unittest

from test_v2.support.model_providers import FakeModelProvider
from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from pathlib import Path

from harness_v2.backend.application.worker_service import WorkerTaskRequest, WorkerTaskService
from harness_v2.backend.domain.bundles import BUNDLE_SPECS
from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec, PhaseName, PhaseRef, RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.model_provider import ModelProviderResult, ModelSelection


class WorkerServiceIntegrationTests(unittest.TestCase):
    def test_worker_service_writes_worker_artifacts_for_current_phase(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        state.save(RunRecord("run-1", "Fix tests", RunStatus.RUNNING, root_bundle=BundleName.EXPLORE_BUNDLE, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING))
        provider = FakeModelProvider([ModelProviderResult('{"schema_version":1}', "", 0, 0.0)])
        service = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())

        result = service.execute(WorkerTaskRequest("run-1", BundleName.EXPLORE_BUNDLE, PhaseName.EXPLORE_REQUEST_UNDERSTANDING, "EXPLORE_BUNDLE:001", "explore_request_profile", {"request": "Fix"}, Path.cwd(), ModelSelection("codex")))

        self.assertTrue(result.provider_succeeded)
        self.assertEqual("workers/EXPLORE_BUNDLE_001/explore_request_profile/request.json", result.request_artifact_id)
        self.assertEqual("request_profile", provider.requests[0].output_schema.name if provider.requests[0].output_schema else None)
        self.assertTrue(artifacts.list("run-1"))

    def test_worker_artifacts_are_scoped_by_step_id_for_repeated_phase_names(self) -> None:
        original = BUNDLE_SPECS[BundleName.EXPLORE_BUNDLE]
        BUNDLE_SPECS[BundleName.EXPLORE_BUNDLE] = BundleSpec(
            BundleName.EXPLORE_BUNDLE,
            (
                PhaseRef(PhaseName.EXPLORE_REQUEST_UNDERSTANDING),
                PhaseRef(PhaseName.EXPLORE_REQUEST_UNDERSTANDING),
            ),
        )
        try:
            state = InMemoryStateStore()
            artifacts = InMemoryArtifactStore()
            provider = FakeModelProvider([ModelProviderResult("one", "", 0, 0.0), ModelProviderResult("two", "", 0, 0.0)])
            service = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
            state.save(RunRecord("run-1", "Fix tests", RunStatus.RUNNING, root_bundle=BundleName.EXPLORE_BUNDLE, current_step_id="EXPLORE_BUNDLE:001"))
            first = service.execute(WorkerTaskRequest("run-1", BundleName.EXPLORE_BUNDLE, PhaseName.EXPLORE_REQUEST_UNDERSTANDING, "EXPLORE_BUNDLE:001", "explore_request_profile", {"request": "Fix"}, Path.cwd(), ModelSelection("codex")))
            state.save(RunRecord("run-1", "Fix tests", RunStatus.RUNNING, root_bundle=BundleName.EXPLORE_BUNDLE, current_step_id="EXPLORE_BUNDLE:002", completed_step_ids=("EXPLORE_BUNDLE:001",)))
            second = service.execute(WorkerTaskRequest("run-1", BundleName.EXPLORE_BUNDLE, PhaseName.EXPLORE_REQUEST_UNDERSTANDING, "EXPLORE_BUNDLE:002", "explore_request_profile", {"request": "Fix"}, Path.cwd(), ModelSelection("codex")))

            self.assertNotEqual(first.request_artifact_id, second.request_artifact_id)
            artifact_ids = tuple(item.artifact_id for item in artifacts.list("run-1"))
            self.assertIn("workers/EXPLORE_BUNDLE_001/explore_request_profile/request.json", artifact_ids)
            self.assertIn("workers/EXPLORE_BUNDLE_002/explore_request_profile/request.json", artifact_ids)
        finally:
            BUNDLE_SPECS[BundleName.EXPLORE_BUNDLE] = original


if __name__ == "__main__":
    unittest.main()
