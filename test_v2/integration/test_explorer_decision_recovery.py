from __future__ import annotations

import json
from pathlib import Path
import unittest

from harness_v2.adapters.models import FakeModelProvider
from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.bundle_artifacts import BundleRuntimeConfig
from harness_v2.backend.application.bundle_orchestration import BundleOrchestrator
from harness_v2.backend.application.bundle_registry import default_bundle_registry
from harness_v2.backend.application.bundles.explorer_recovery import EXPLORER_REFINEMENT_DECISION_ID
from harness_v2.backend.application.contracts import ResumeRun, StartRun, SubmitUserDecision
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus
from harness_v2.backend.ports.artifact_store import ArtifactNotFoundError
from harness_v2.backend.ports.model_provider import ModelProviderResult

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class StaticClock:
    def now_iso(self) -> str:
        return TIMESTAMP


class StaticIdGenerator:
    def new_id(self) -> str:
        return "run-1"


def model_result(payload: dict[str, object]) -> ModelProviderResult:
    return ModelProviderResult(json.dumps(payload), "", 0, 0)


def intake() -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "explorer_intake",
        "claims": [{"id": "C1", "class": "repository-factual", "text": "Investigate", "evidence_targets": ["repo"]}],
        "strategic_framing": {"mode": "specific"},
        "synthesis_notes": ["Start with discovery."],
    }


def discovery(label: str = "initial") -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "explorer_discovery",
        "claims": [{"id": "C1", "status": "resolved", "evidence": [label]}],
        "evidence_trace": [{"id": "T1", "claim_id": "C1", "source": "code", "path": "file.py", "excerpt": label, "confidence": "high"}],
        "candidate_directions": [],
        "critic_findings": [],
        "related_improvements": [],
        "repository_observations": [],
    }


def decision(outcome: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "explorer_decision",
        "outcome": outcome,
        "rationale": "More evidence is needed.",
        "evidence": ["T1"],
        "selected_direction": "D1",
        "value_hypothesis": "Better discovery improves the candidate.",
        "behavioral_delta": "Rediscover with user refinement.",
        "minimum_verification": "Rerun discovery.",
        "rejected_alternatives": [],
        "counterevidence": [],
        "falsifying_conditions": [],
    }


def prompt_payload(prompt: str) -> dict[str, object]:
    marker = "Return only the required artifact. Controller inputs:"
    return json.loads(prompt.rsplit(marker, 1)[1].strip())


class FailingSaveStateStore:
    def __init__(self, delegate: InMemoryStateStore) -> None:
        self.delegate = delegate

    def get(self, run_id: str):
        return self.delegate.get(run_id)

    def save(self, run) -> None:
        raise RuntimeError("save failed")

    def list_all(self):
        return self.delegate.list_all()

    def list_active(self):
        return self.delegate.list_active()

    def list_completed(self):
        return self.delegate.list_completed()


class ExplorerDecisionRecoveryTests(unittest.TestCase):
    def service(self, provider: FakeModelProvider) -> tuple[RunService, InMemoryStateStore, InMemoryArtifactStore]:
        state = InMemoryStateStore()
        artifacts = InMemoryArtifactStore()
        clock = StaticClock()
        worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
        orchestrator = BundleOrchestrator(
            state,
            artifacts,
            worker,
            clock,
            default_bundle_registry(),
            BundleRuntimeConfig(working_directory=Path.cwd()),
        )
        return RunService(state, StaticIdGenerator(), orchestrator=orchestrator, clock=clock, artifact_store=artifacts), state, artifacts

    def test_needs_user_decision_waits_then_refinement_rewinds_and_guides_rediscovery(self) -> None:
        provider = FakeModelProvider([
            model_result(intake()),
            model_result(discovery()),
            model_result(decision("needs_user_decision")),
            model_result(discovery("refined")),
        ])
        app, state, artifacts = self.service(provider)
        app.execute(StartRun("Investigate recovery", strategy="EXPLORER"))
        app.execute(ResumeRun("run-1"))
        app.execute(ResumeRun("run-1"))

        waiting = app.execute(ResumeRun("run-1"))

        self.assertEqual("WAITING_FOR_USER", waiting.run.status)
        self.assertEqual(EXPLORER_REFINEMENT_DECISION_ID, waiting.run.pending_decision.decision_id)
        self.assertIn("More evidence is needed", waiting.run.pending_decision.prompt)
        self.assertEqual(RunStatus.WAITING_FOR_USER, state.get("run-1").status)

        decided = app.execute(SubmitUserDecision("run-1", EXPLORER_REFINEMENT_DECISION_ID, "look for CLI entrypoints"))

        self.assertEqual("RUNNING", decided.run.status)
        self.assertEqual("EXPLORER_DISCOVERY", decided.run.current_phase)
        self.assertEqual(("EXPLORER_INTAKE",), decided.run.completed_phases)
        self.assertEqual(["UserDecisionReceived", "EscalationRaised", "EscalationResolved", "PhaseStarted"], [type(event).__name__ for event in decided.events])
        for stale in ("explorer/discovery.json", "explorer/decision.json"):
            with self.assertRaises(ArtifactNotFoundError):
                artifacts.read("run-1", stale)

        rediscovered = app.execute(ResumeRun("run-1"))

        self.assertEqual("EXPLORER_DECISION", rediscovered.run.current_phase)
        refinement = json.loads(artifacts.read("run-1", "explorer/refinement.json"))
        self.assertEqual("look for CLI entrypoints", refinement["response"])
        payload = prompt_payload(provider.requests[-1].prompt)
        self.assertEqual("explorer_discovery", payload["task_id"])
        self.assertEqual("look for CLI entrypoints", payload["inputs"]["refinement"]["response"])
        self.assertEqual("look for CLI entrypoints", state.get("run-1").decision_history[-1].response)

    def test_escalate_discovery_recovers_automatically_and_invalidates_stale_artifacts(self) -> None:
        provider = FakeModelProvider([
            model_result(intake()),
            model_result(discovery()),
            model_result(decision("escalate_discovery")),
        ])
        app, state, artifacts = self.service(provider)
        app.execute(StartRun("Investigate recovery", strategy="EXPLORER"))
        app.execute(ResumeRun("run-1"))
        app.execute(ResumeRun("run-1"))

        recovered = app.execute(ResumeRun("run-1"))

        self.assertEqual("RUNNING", recovered.run.status)
        self.assertEqual("EXPLORER_DISCOVERY", recovered.run.current_phase)
        self.assertEqual(("EXPLORER_INTAKE",), recovered.run.completed_phases)
        self.assertEqual(["RunResumed", "EscalationRaised", "EscalationResolved", "PhaseStarted"], [type(event).__name__ for event in recovered.events])
        self.assertEqual(PhaseName.EXPLORER_DISCOVERY, state.get("run-1").current_phase)
        for stale in ("explorer/discovery.json", "explorer/decision.json"):
            with self.assertRaises(ArtifactNotFoundError):
                artifacts.read("run-1", stale)

    def test_escalate_discovery_restores_invalidated_artifacts_when_state_save_fails(self) -> None:
        provider = FakeModelProvider([
            model_result(intake()),
            model_result(discovery()),
            model_result(decision("escalate_discovery")),
        ])
        app, state, artifacts = self.service(provider)
        app.execute(StartRun("Investigate recovery", strategy="EXPLORER"))
        app.execute(ResumeRun("run-1"))
        app.execute(ResumeRun("run-1"))
        original = state.get("run-1")
        failing_clock = StaticClock()
        worker = WorkerTaskService(FailingSaveStateStore(state), artifacts, provider, FileWorkerResourceStore())
        orchestrator = BundleOrchestrator(
            FailingSaveStateStore(state),
            artifacts,
            worker,
            failing_clock,
            default_bundle_registry(),
            BundleRuntimeConfig(working_directory=Path.cwd()),
        )
        failing_app = RunService(FailingSaveStateStore(state), StaticIdGenerator(), orchestrator=orchestrator, clock=failing_clock, artifact_store=artifacts)

        with self.assertRaises(RuntimeError):
            failing_app.execute(ResumeRun("run-1"))

        self.assertEqual(original, state.get("run-1"))
        self.assertTrue(artifacts.read("run-1", "explorer/discovery.json"))
        self.assertTrue(artifacts.read("run-1", "explorer/decision.json"))



if __name__ == "__main__":
    unittest.main()
