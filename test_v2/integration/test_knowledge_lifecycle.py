from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness_v2.adapters.models import ScriptedModelProvider
from harness_v2.adapters.storage import (
    FileKnowledgePatchStore,
    InMemoryArtifactStore,
    InMemoryKnowledgePatchStore,
    InMemoryStateStore,
)
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.bundle_artifacts import BundleRuntimeConfig
from harness_v2.backend.application.bundle_orchestration import BundleExecutionResult, BundleOrchestrator
from harness_v2.backend.application.bundle_registry import default_bundle_registry
from harness_v2.backend.application.contracts import ResumeRun, StartRun
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.domain.knowledge import KnowledgePatchStatus, parse_learning_proposal
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus
from harness_v2.backend.domain.tasks import TaskStatus
from harness_v2.backend.ports.model_provider import ModelProviderRequest, ModelProviderResult


TIMESTAMP = "2026-07-01T00:00:00+00:00"


class StaticIdGenerator:
    def new_id(self) -> str:
        return "run-1"


class StaticClock:
    def now_iso(self) -> str:
        return TIMESTAMP


class CompletingTddLoop:
    def execute(self, context) -> BundleExecutionResult:
        completed = tuple(task.replace(status=TaskStatus.COMPLETED) for task in context.run.tasks)
        context.artifacts.write_json(
            context.run.run_id,
            "published/tdd-results.json",
            {"schema_version": 1, "phase": "tdd", "results": [], "blocked_reason": None},
        )
        context.artifacts.write_json(
            context.run.run_id,
            "published/tdd-handoff.json",
            {
                "schema_version": 1,
                "bundle": "tdd",
                "artifacts": ["tasks.json", "published/tdd-results.json"],
                "next_bundle": "KNOWLEDGE_EXTRACT_TDD",
                "completed_tasks": [task.task_id for task in completed],
            },
        )
        return BundleExecutionResult(tasks=completed)


class MalformedKnowledgeProvider(ScriptedModelProvider):
    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        if '"task_id": "knowledge_synthesis"' in request.prompt:
            return ModelProviderResult("not json", "", 0, 0.0)
        return super().run(request)


def service(
    provider: ScriptedModelProvider | None = None,
    *,
    tdd_loop: object | None = None,
) -> tuple[RunService, InMemoryKnowledgePatchStore]:
    state = InMemoryStateStore()
    artifacts = InMemoryArtifactStore()
    knowledge = InMemoryKnowledgePatchStore()
    worker = WorkerTaskService(state, artifacts, provider or ScriptedModelProvider(), FileWorkerResourceStore())
    registry = default_bundle_registry(tdd_loop=tdd_loop)
    orchestrator = BundleOrchestrator(
        state,
        artifacts,
        worker,
        StaticClock(),
        registry,
        BundleRuntimeConfig(working_directory=Path.cwd()),
        knowledge_patches=knowledge,
    )
    return (
        RunService(
            state,
            StaticIdGenerator(),
            orchestrator=orchestrator,
            clock=StaticClock(),
            artifact_store=artifacts,
            invalidation_rules=registry.invalidation_rules(),
        ),
        knowledge,
    )


def valid_proposal() -> object:
    return {
        "schema_version": 1,
        "phase": "learning",
        "proposal_manifest": {
            "schema_version": 1,
            "proposal_id": "proposal.v2.file.001",
            "summary": "File-backed candidate.",
            "source_artifacts": ["published/tdd-results.json"],
            "claims_file": "proposed_claims.jsonl",
        },
        "proposed_claims": [{
            "id": "claim.v2.file.001",
            "domain": "harness",
            "subjects": ["KnowledgeLifecycle"],
            "files": ["harness_v2/backend/domain/lifecycle.py"],
            "symbols": [],
            "claim_type": "behavior",
            "text": "Candidate knowledge stays separate from accepted SOT.",
            "status": "active",
            "evidence": [{"type": "code", "file": "harness_v2/backend/domain/lifecycle.py"}],
            "valid_from": None,
            "valid_until": None,
            "last_verified": None,
        }],
        "proposed_relations": [],
    }


class KnowledgeLifecycleIntegrationTests(unittest.TestCase):
    def test_sdd_creates_versioned_candidate_patch_after_explore(self) -> None:
        app, knowledge = service()
        app.execute(StartRun("Fix tests"))

        app.execute(ResumeRun("run-1"))
        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("PROPOSAL_BUNDLE", result.run.current_phase)
        self.assertIn("KnowledgePatchCreated", [type(event).__name__ for event in result.events])
        patches = knowledge.list_patches("run-1")
        self.assertEqual(1, len(patches))
        self.assertEqual("patch.run-1.explore_bundle.v0001", patches[0].patch_id)
        self.assertEqual(PhaseName.EXPLORE_BUNDLE, patches[0].origin_phase)

    def test_full_sdd_with_successful_tdd_creates_second_candidate_patch(self) -> None:
        app, knowledge = service(tdd_loop=CompletingTddLoop())
        app.execute(StartRun("Fix tests"))

        result = None
        for _ in range(8):
            result = app.execute(ResumeRun("run-1"))

        self.assertIsNotNone(result)
        self.assertEqual("COMPLETED", result.run.status)
        patches = knowledge.list_patches("run-1", status=KnowledgePatchStatus.CANDIDATE)
        self.assertEqual(
            ["patch.run-1.explore_bundle.v0001", "patch.run-1.tdd_bundle.v0001"],
            [patch.patch_id for patch in patches],
        )

    def test_malformed_knowledge_output_fails_without_creating_patch(self) -> None:
        app, knowledge = service(MalformedKnowledgeProvider())
        app.execute(StartRun("Fix tests"))
        app.execute(ResumeRun("run-1"))

        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("FAILED", result.run.status)
        self.assertEqual((), knowledge.list_patches("run-1"))

    def test_file_store_writes_pending_patch_and_reject_does_not_create_sot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileKnowledgePatchStore(root)
            patch = store.create_patch("run-1", PhaseName.TDD_BUNDLE, parse_learning_proposal(valid_proposal()), TIMESTAMP)

            store.reject_patch(patch.patch_id, "not durable", TIMESTAMP)

            patch_root = root / "knowledge-source" / "patches" / "pending" / "run-1" / "tdd_bundle" / "v0001"
            self.assertTrue((patch_root / "proposal_manifest.json").is_file())
            self.assertTrue((patch_root / "proposed_claims.jsonl").is_file())
            state = json.loads((patch_root / "patch_state.json").read_text(encoding="utf-8"))
            self.assertEqual("REJECTED", state["status"])
            self.assertFalse((root / "docs" / "knowledge-db").exists())
            self.assertFalse((root / ".ai-harness" / "knowledge.db").exists())


if __name__ == "__main__":
    unittest.main()
