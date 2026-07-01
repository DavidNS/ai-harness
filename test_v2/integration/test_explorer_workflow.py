from __future__ import annotations

import json
from pathlib import Path
import unittest

from harness_v2.adapters.models import ScriptedModelProvider
from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.bundle_artifacts import BundleRuntimeConfig
from harness_v2.backend.application.bundle_orchestration import BundleOrchestrator
from harness_v2.backend.application.bundle_registry import default_bundle_registry
from harness_v2.backend.application.contracts import ResumeRun, StartRun
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.domain.lifecycle import EXPLORER_PHASES, RunStatus

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class StaticClock:
    def now_iso(self) -> str:
        return TIMESTAMP


class StaticIdGenerator:
    def new_id(self) -> str:
        return "run-1"


class ExplorerWorkflowIntegrationTests(unittest.TestCase):
    def service(self) -> tuple[RunService, InMemoryStateStore, InMemoryArtifactStore, ScriptedModelProvider]:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        provider = ScriptedModelProvider()
        worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
        orchestrator = BundleOrchestrator(state, artifacts, worker, StaticClock(), default_bundle_registry(), BundleRuntimeConfig(working_directory=Path.cwd()))
        return RunService(state, StaticIdGenerator(), orchestrator=orchestrator, clock=StaticClock()), state, artifacts, provider

    def test_explorer_strategy_completes_one_stage_per_resume(self) -> None:
        app, state, artifacts, _provider = self.service()
        app.execute(StartRun("Investigate v2 explorer", strategy="EXPLORER"))

        expected = [
            ("EXPLORER_DISCOVERY", ("EXPLORER_INTAKE",)),
            ("EXPLORER_DECISION", ("EXPLORER_INTAKE", "EXPLORER_DISCOVERY")),
            ("EXPLORER_ARTIFACT", ("EXPLORER_INTAKE", "EXPLORER_DISCOVERY", "EXPLORER_DECISION")),
            ("EXPLORER_REVIEW", ("EXPLORER_INTAKE", "EXPLORER_DISCOVERY", "EXPLORER_DECISION", "EXPLORER_ARTIFACT")),
            ("EXPLORER_DISTILL", ("EXPLORER_INTAKE", "EXPLORER_DISCOVERY", "EXPLORER_DECISION", "EXPLORER_ARTIFACT", "EXPLORER_REVIEW")),
            (None, tuple(phase.value for phase in EXPLORER_PHASES)),
        ]
        for current_phase, completed in expected:
            result = app.execute(ResumeRun("run-1"))
            self.assertEqual(current_phase, result.run.current_phase)
            self.assertEqual(completed, result.run.completed_phases)

        self.assertEqual(RunStatus.COMPLETED, state.get("run-1").status)
        artifact_ids = [item.artifact_id for item in artifacts.list("run-1")]
        for artifact_id in (
            "explorer/intake.json",
            "explorer/discovery.json",
            "explorer/decision.json",
            "explorer/artifact-candidate.txt",
            "explorer/review.md",
            "explorer/distilled-candidate.md",
        ):
            self.assertIn(artifact_id, artifact_ids)
        worker_tasks = []
        for phase, task in (
            ("EXPLORER_INTAKE", "explorer_intake"),
            ("EXPLORER_DISCOVERY", "explorer_discovery"),
            ("EXPLORER_DECISION", "explorer_decision"),
            ("EXPLORER_ARTIFACT", "explorer_artifact"),
            ("EXPLORER_REVIEW", "explorer_review"),
            ("EXPLORER_DISTILL", "explorer_distill"),
        ):
            payload = json.loads(artifacts.read("run-1", f"workers/{phase}/{task}/request.json"))
            worker_tasks.append(payload["task_id"])
        self.assertEqual(
            [
                "explorer_intake",
                "explorer_discovery",
                "explorer_decision",
                "explorer_artifact",
                "explorer_review",
                "explorer_distill",
            ],
            worker_tasks,
        )


if __name__ == "__main__":
    unittest.main()
