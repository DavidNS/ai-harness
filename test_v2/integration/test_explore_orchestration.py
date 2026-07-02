from __future__ import annotations

import json
from pathlib import Path
import unittest

from harness_v2.adapters.models import FakeModelProvider, ScriptedModelProvider
from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryKnowledgePatchStore, InMemoryStateStore
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.contracts import (
    PhaseCompleted,
    PhaseFailed,
    PhaseStarted,
    ResumeRun,
    RunCompleted,
    StartRun,
    SubmitUserDecision,
    UserDecisionRequested,
)
from harness_v2.backend.application.bundle_artifacts import BundleRuntimeConfig
from harness_v2.backend.application.bundle_orchestration import BundleOrchestrator
from harness_v2.backend.application.bundle_registry import default_bundle_registry
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.model_provider import ModelProviderResult

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class StaticClock:
    def now_iso(self) -> str:
        return TIMESTAMP


class StaticIdGenerator:
    def __init__(self, value: str = "run-1") -> None:
        self.value = value

    def new_id(self) -> str:
        return self.value


def profile(*, questions: list[str] | None = None) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "phase": "explore_request_profile",
            "summary": "Fix tests",
            "request_type": "feature",
            "complexity": "local_change",
            "ambiguity": "clear",
            "risk": "low",
            "evidence_depth": "standard",
            "request_parts": ["Fix tests"],
            "constraints": [],
            "evidence_questions": ["What fails?"],
            "gatherers": ["code"],
            "clarification_questions": questions or [],
        }
    )


def digest() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "phase": "explore_evidence_digest",
            "evidence": [
                {
                    "id": "E1",
                    "kind": "knowledge",
                    "claim": "The request is bounded.",
                    "status": "supported",
                    "confidence": "high",
                    "severity": "info",
                    "sources": [{"type": "knowledge", "description": "fixture"}],
                }
            ],
            "blockers": [],
        }
    )


def synthesis(*, refs: list[str] | None = None) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "kind": "explore_outcome_synthesis",
            "status": "ready_for_purpose",
            "normalized_request": {"summary": "Fix tests"},
            "triage": {"complexity": "local_change", "ambiguity": "clear", "risk": "low", "evidence_depth": "standard"},
            "entries": [
                {
                    "id": "entry-1",
                    "classification": "improvement",
                    "title": "Fix tests",
                    "evidence_refs": refs or ["E1"],
                }
            ],
        }
    )




def seed_explore_outcome(artifacts: InMemoryArtifactStore, run_id: str = "run-1") -> None:
    artifacts.write(
        run_id,
        "explore/outcome_bundle.json",
        json.dumps(
            {
                "schema_version": 1,
                "kind": "explore_outcome_bundle",
                "status": "ready_for_purpose",
                "normalized_request": {"summary": "Fix tests"},
                "triage": {},
                "evidence": [],
                "exploration_map": {},
                "entries": [],
            }
        ).encode(),
    )


def seed_purpose(artifacts: InMemoryArtifactStore, run_id: str = "run-1") -> None:
    artifacts.write(
        run_id,
        "purpose/bundle.json",
        json.dumps(
            {
                "schema_version": 1,
                "kind": "purpose_bundle",
                "summary": "Fix tests",
                "selected_entries": ["entry-1"],
                "implementation_mode": "direct_patch",
                "problem": "Fix tests",
                "scope": "One bounded change.",
                "approach": "Use the SDD skeleton.",
                "structural_work": [],
                "exclusions": [],
                "acceptance_outline": ["Tests pass."],
                "evidence_refs": [],
            }
        ).encode(),
    )


def seed_spec(artifacts: InMemoryArtifactStore, run_id: str = "run-1") -> None:
    artifacts.write(run_id, "spec.md", b"# Spec v1\n## Behavioral Requirements\nWorks.\n## Acceptance Criteria\nPasses.\n")


def seed_design(artifacts: InMemoryArtifactStore, run_id: str = "run-1") -> None:
    artifacts.write(
        run_id,
        "design.md",
        (
            "# Design v1\n"
            "## Boundaries\nBackend only.\n"
            "## Invariants\nState through ports.\n"
            "## Implementation Approach\nSmall change.\n"
            "## Unit Test Design\nFocused tests.\n"
            "## Integration Test Design\nLifecycle tests.\n"
            "## End-to-End Test Design\nSkeleton completion.\n"
        ).encode(),
    )

def task_id_from_prompt(prompt: str) -> str:
    marker = "Return only the required artifact. Controller inputs:"
    payload = json.loads(prompt.rsplit(marker, 1)[1].strip())
    return str(payload["task_id"])

def service(
    state: InMemoryStateStore | None = None,
    artifacts: InMemoryArtifactStore | None = None,
    provider: object | None = None,
) -> tuple[RunService, InMemoryStateStore, InMemoryArtifactStore, object]:
    state = state or InMemoryStateStore()
    artifacts = artifacts or InMemoryArtifactStore()
    provider = provider or ScriptedModelProvider()
    clock = StaticClock()
    worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
    orchestrator = BundleOrchestrator(
        state,
        artifacts,
        worker,
        clock,
        default_bundle_registry(),
        BundleRuntimeConfig(working_directory=Path.cwd()),
        knowledge_patches=InMemoryKnowledgePatchStore(),
    )
    return RunService(state, StaticIdGenerator(), orchestrator=orchestrator, clock=clock), state, artifacts, provider


class ExploreOrchestrationIntegrationTests(unittest.TestCase):
    def test_resume_explore_strategy_completes_bundle_and_records_artifacts(self) -> None:
        app, state, artifacts, _provider = service()
        app.execute(StartRun("Fix tests", strategy="EXPLORE_BUNDLE"))

        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("COMPLETED", result.run.status)
        self.assertEqual(("EXPLORE_BUNDLE",), result.run.completed_phases)
        self.assertEqual(["RunResumed", "PhaseStarted", "PhaseCompleted", "RunCompleted"], [type(event).__name__ for event in result.events])
        self.assertEqual(RunStatus.COMPLETED, state.get("run-1").status)
        artifact_ids = [item.artifact_id for item in artifacts.list("run-1")]
        self.assertIn("explore/request_profile.json", artifact_ids)
        self.assertIn("explore/context_pack.json", artifact_ids)
        self.assertIn("explore/evidence_digest.json", artifact_ids)
        self.assertIn("explore/exploration_map.json", artifact_ids)
        self.assertIn("explore/outcome_synthesis.json", artifact_ids)
        self.assertIn("explore/outcome_bundle.json", artifact_ids)
        self.assertIn("published/explore-handoff.json", artifact_ids)

    def test_resume_sdd_advances_from_explore_to_knowledge_and_stops(self) -> None:
        app, state, _artifacts, _provider = service()
        app.execute(StartRun("Fix tests"))

        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("RUNNING", result.run.status)
        self.assertEqual("KNOWLEDGE_EXTRACT_EXPLORE", result.run.current_phase)
        self.assertEqual(("EXPLORE_BUNDLE",), result.run.completed_phases)
        self.assertIsInstance(result.events[-2], PhaseCompleted)
        self.assertIsInstance(result.events[-1], PhaseStarted)
        persisted = state.get("run-1")
        self.assertEqual(PhaseName.KNOWLEDGE_EXTRACT_EXPLORE, persisted.current_phase)


    def test_sdd_skeleton_advances_to_tdd_then_fails_without_mutation_enabled(self) -> None:
        app, state, artifacts, _provider = service()
        app.execute(StartRun("Fix tests"))

        expected = [
            ("KNOWLEDGE_EXTRACT_EXPLORE", ("EXPLORE_BUNDLE",)),
            ("PROPOSAL_BUNDLE", ("EXPLORE_BUNDLE", "KNOWLEDGE_EXTRACT_EXPLORE")),
            ("SPEC_BUNDLE", ("EXPLORE_BUNDLE", "KNOWLEDGE_EXTRACT_EXPLORE", "PROPOSAL_BUNDLE")),
            ("DESIGN_BUNDLE", ("EXPLORE_BUNDLE", "KNOWLEDGE_EXTRACT_EXPLORE", "PROPOSAL_BUNDLE", "SPEC_BUNDLE")),
            ("TASKS_BUNDLE", ("EXPLORE_BUNDLE", "KNOWLEDGE_EXTRACT_EXPLORE", "PROPOSAL_BUNDLE", "SPEC_BUNDLE", "DESIGN_BUNDLE")),
            ("TDD_BUNDLE", ("EXPLORE_BUNDLE", "KNOWLEDGE_EXTRACT_EXPLORE", "PROPOSAL_BUNDLE", "SPEC_BUNDLE", "DESIGN_BUNDLE", "TASKS_BUNDLE")),
        ]
        for current_phase, completed in expected:
            result = app.execute(ResumeRun("run-1"))
            self.assertEqual(completed, result.run.completed_phases)
            self.assertEqual(current_phase, result.run.current_phase)

        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("FAILED", result.run.status)
        self.assertIsNone(result.run.current_phase)
        self.assertEqual(("EXPLORE_BUNDLE", "KNOWLEDGE_EXTRACT_EXPLORE", "PROPOSAL_BUNDLE", "SPEC_BUNDLE", "DESIGN_BUNDLE", "TASKS_BUNDLE"), result.run.completed_phases)
        self.assertEqual(RunStatus.FAILED, state.get("run-1").status)
        artifact_ids = [item.artifact_id for item in artifacts.list("run-1")]
        for artifact_id in (
            "purpose/bundle.json",
            "spec.md",
            "design.md",
            "tasks.json",
            "published/proposal-handoff.json",
            "published/spec-handoff.json",
            "published/design-handoff.json",
            "published/tasks-handoff.json",
            "published/tdd-results.json",
        ):
            self.assertIn(artifact_id, artifact_ids)
        tdd_results = json.loads(artifacts.read("run-1", "published/tdd-results.json"))
        self.assertIn("TDD loop service", tdd_results["blocked_reason"])
        self.assertTrue(all(task.status.value == "PENDING" for task in state.get("run-1").tasks))

    def test_single_proposal_bundle_uses_same_registry_path(self) -> None:
        app, state, artifacts, _provider = service()
        app.execute(StartRun("Fix proposal", strategy="PROPOSAL_BUNDLE"))
        seed_explore_outcome(artifacts)

        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("COMPLETED", result.run.status)
        self.assertEqual(("PROPOSAL_BUNDLE",), result.run.completed_phases)
        self.assertEqual(RunStatus.COMPLETED, state.get("run-1").status)
        self.assertIsNotNone(artifacts.read("run-1", "purpose/bundle.json"))


    def test_standalone_proposal_requires_seeded_explore_outcome(self) -> None:
        app, state, _artifacts, _provider = service()
        app.execute(StartRun("Fix proposal", strategy="PROPOSAL_BUNDLE"))

        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("FAILED", result.run.status)
        self.assertIsInstance(result.events[-1], PhaseFailed)
        self.assertIn("explore/outcome_bundle.json", result.events[-1].error)
        self.assertEqual(RunStatus.FAILED, state.get("run-1").status)

    def test_downstream_bundles_reuse_existing_valid_artifacts_without_worker(self) -> None:
        cases = (
            ("SPEC_BUNDLE", PhaseName.SPEC_BUNDLE, lambda artifacts: (seed_explore_outcome(artifacts), seed_purpose(artifacts)), "spec.md"),
            ("DESIGN_BUNDLE", PhaseName.DESIGN_BUNDLE, lambda artifacts: (seed_explore_outcome(artifacts), seed_purpose(artifacts), seed_spec(artifacts)), "design.md"),
            ("TASKS_BUNDLE", PhaseName.TASKS_BUNDLE, lambda artifacts: (seed_explore_outcome(artifacts), seed_purpose(artifacts), seed_spec(artifacts), seed_design(artifacts)), "tasks.json"),
        )
        for strategy, phase, seed, artifact_id in cases:
            with self.subTest(strategy=strategy):
                state = InMemoryStateStore()
                artifacts = InMemoryArtifactStore()
                provider = FakeModelProvider([])
                app, _state, _artifacts, _provider = service(state, artifacts, provider)
                app.execute(StartRun("Fix tests", strategy=strategy))
                seed(artifacts)
                if artifact_id == "tasks.json":
                    artifacts.write(
                        "run-1",
                        artifact_id,
                        json.dumps({
                            "schema_version": 1,
                            "phase": "tasks",
                            "tasks": [{
                                "id": "T1",
                                "title": "Seeded task",
                                "depends_on": [],
                                "acceptance_criteria": ["Done."],
                                "touched_paths": ["."],
                                "focused_tests": [],
                                "broader_tests": [],
                                "status": "pending",
                            }],
                        }).encode(),
                    )
                elif artifact_id == "spec.md":
                    seed_spec(artifacts)
                else:
                    seed_design(artifacts)

                result = app.execute(ResumeRun("run-1"))

                self.assertEqual("COMPLETED", result.run.status)
                self.assertEqual((phase.value,), result.run.completed_phases)
                self.assertEqual([], provider.requests)

    def test_downstream_bundles_fail_on_missing_or_invalid_prerequisites(self) -> None:
        cases = (
            ("SPEC_BUNDLE", "purpose/bundle.json", lambda artifacts: seed_explore_outcome(artifacts)),
            ("DESIGN_BUNDLE", "spec.md", lambda artifacts: (seed_explore_outcome(artifacts), seed_purpose(artifacts))),
            ("TASKS_BUNDLE", "design.md", lambda artifacts: (seed_explore_outcome(artifacts), seed_purpose(artifacts), seed_spec(artifacts))),
        )
        for strategy, missing, seed in cases:
            with self.subTest(strategy=strategy):
                app, state, artifacts, _provider = service()
                app.execute(StartRun("Fix tests", strategy=strategy))
                seed(artifacts)

                result = app.execute(ResumeRun("run-1"))

                self.assertEqual("FAILED", result.run.status)
                self.assertIsInstance(result.events[-1], PhaseFailed)
                self.assertIn(missing, result.events[-1].error)
                self.assertEqual(RunStatus.FAILED, state.get("run-1").status)

        app, _state, artifacts, _provider = service()
        app.execute(StartRun("Fix tests", strategy="DESIGN_BUNDLE"))
        seed_explore_outcome(artifacts)
        seed_purpose(artifacts)
        artifacts.write("run-1", "spec.md", b"bad spec")

        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("FAILED", result.run.status)
        self.assertIn("document must start with # Spec v1", result.events[-1].error)

    def test_resume_reuses_existing_valid_artifacts_before_invoking_workers(self) -> None:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        provider = FakeModelProvider([ModelProviderResult(digest(), "", 0, 0), ModelProviderResult(synthesis(), "", 0, 0)])
        app, _state, _artifacts, _provider = service(state, artifacts, provider)
        state.save(RunRecord("run-1", "Fix tests", RunStatus.RUNNING, RunStrategy.EXPLORE_BUNDLE, current_phase=PhaseName.EXPLORE_BUNDLE))
        artifacts.write("run-1", "explore/request_profile.json", (profile() + "\n").encode())

        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("COMPLETED", result.run.status)
        self.assertEqual(["explore_evidence_digest", "explore_outcome_synthesis"], [task_id_from_prompt(call.prompt) for call in provider.requests])


    def test_non_explore_bundle_failure_uses_generic_validation_artifact(self) -> None:
        provider = FakeModelProvider([ModelProviderResult("not json", "", 0, 0)])
        app, state, artifacts, _provider = service(provider=provider)
        app.execute(StartRun("Fix proposal", strategy="PROPOSAL_BUNDLE"))

        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("FAILED", result.run.status)
        self.assertIsInstance(result.events[-1], PhaseFailed)
        self.assertEqual(RunStatus.FAILED, state.get("run-1").status)
        failure = json.loads(artifacts.read("run-1", "validation/PROPOSAL_BUNDLE-failure.json"))
        self.assertEqual("PROPOSAL_BUNDLE", failure["phase"])

    def test_invalid_synthesis_evidence_refs_are_repaired_by_controller(self) -> None:
        provider = FakeModelProvider([
            ModelProviderResult(profile(), "", 0, 0),
            ModelProviderResult(digest(), "", 0, 0),
            ModelProviderResult(synthesis(refs=["missing"]), "", 0, 0),
        ])
        app, state, artifacts, _provider = service(provider=provider)
        app.execute(StartRun("Fix tests", strategy="EXPLORE_BUNDLE"))

        result = app.execute(ResumeRun("run-1"))

        self.assertEqual("COMPLETED", result.run.status)
        self.assertIsInstance(result.events[-2], PhaseCompleted)
        self.assertEqual(RunStatus.COMPLETED, state.get("run-1").status)
        bundle = json.loads(artifacts.read("run-1", "explore/outcome_bundle.json"))
        self.assertEqual(["E1"], bundle["entries"][0]["evidence_refs"])

    def test_clarification_waits_then_submit_decision_and_resume_completes(self) -> None:
        provider = FakeModelProvider([
            ModelProviderResult(profile(questions=["Which test should be fixed?"]), "", 0, 0),
            ModelProviderResult(digest(), "", 0, 0),
            ModelProviderResult(synthesis(), "", 0, 0),
        ])
        app, state, _artifacts, _provider = service(provider=provider)
        app.execute(StartRun("Fix tests", strategy="EXPLORE_BUNDLE"))

        waiting = app.execute(ResumeRun("run-1"))

        self.assertEqual("WAITING_FOR_USER", waiting.run.status)
        self.assertIsInstance(waiting.events[-1], UserDecisionRequested)
        decision_id = waiting.run.pending_decision.decision_id

        decided = app.execute(SubmitUserDecision("run-1", decision_id, "Fix unit tests"))
        self.assertEqual("RUNNING", decided.run.status)
        self.assertEqual(1, len(state.get("run-1").decision_history))

        completed = app.execute(ResumeRun("run-1"))
        self.assertEqual("COMPLETED", completed.run.status)
        self.assertIsInstance(completed.events[-1], RunCompleted)
        self.assertEqual(["explore_request_profile", "explore_evidence_digest", "explore_outcome_synthesis"], [task_id_from_prompt(call.prompt) for call in provider.requests])


if __name__ == "__main__":
    unittest.main()
