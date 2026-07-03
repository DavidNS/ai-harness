from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from time import monotonic

from test_v2.support.runtime import StaticClock, StaticIdGenerator
from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.bundle_artifacts import BundleRuntimeConfig
from harness_v2.backend.application.contracts import ResumeRun, StartRun, SubmitUserDecision
from harness_v2.backend.application.phase_executor import PhaseExecutor, default_phase_function_registry
from harness_v2.backend.application.run_orchestrator import RunOrchestrator
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.ports.model_provider import ModelProviderRequest, ModelProviderResult


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True)


class AskUserProvider:
    def __init__(self, *, resolve_after_decision: bool = True) -> None:
        self.resolve_after_decision = resolve_after_decision
        self.outcome_inputs: list[dict[str, object]] = []

    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        started = monotonic()
        payload = _payload(request.prompt)
        task_id = payload.get("task_id")
        inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
        if task_id == "explore_request_profile":
            stdout = _json({
                "schema_version": 1,
                "phase": "explore_request_profile",
                "summary": "Choose direction",
                "request_type": "feature",
                "complexity": "local_change",
                "ambiguity": "clear",
                "risk": "low",
                "evidence_depth": "standard",
                "request_parts": ["Choose direction"],
                "constraints": [],
                "evidence_questions": ["Which direction?"],
                "gatherers": ["code"],
                "clarification_questions": [],
            })
        elif task_id == "explore_evidence_digest":
            stdout = _json({
                "schema_version": 1,
                "phase": "explore_evidence_digest",
                "evidence": [{
                    "id": "E1",
                    "kind": "knowledge",
                    "claim": "Two directions are possible.",
                    "status": "supported",
                    "confidence": "high",
                    "severity": "info",
                    "sources": [{"type": "knowledge", "description": "fixture"}],
                }],
                "blockers": [],
            })
        elif task_id == "explore_outcome_synthesis":
            self.outcome_inputs.append(inputs)
            history = inputs.get("decision_history") if isinstance(inputs.get("decision_history"), list) else []
            if history and self.resolve_after_decision:
                stdout = _json({
                    "schema_version": 1,
                    "kind": "explore_outcome_synthesis",
                    "status": "ready_for_purpose",
                    "normalized_request": {"summary": "Implement selected direction."},
                    "triage": {"complexity": "local_change"},
                    "entries": [{
                        "id": "entry-1",
                        "classification": "improvement",
                        "action": "create",
                        "title": "Implement selected direction",
                        "rationale": "The user selected option-a.",
                        "behavioral_delta": "The selected behavior is implemented.",
                        "minimum_verification": "Run focused tests.",
                        "evidence_refs": ["E1"],
                    }],
                })
            else:
                stdout = _json({
                    "schema_version": 1,
                    "kind": "explore_outcome_synthesis",
                    "status": "needs_user_decision",
                    "normalized_request": {"summary": "Choose direction."},
                    "triage": {"complexity": "local_change"},
                    "entries": [{
                        "id": "entry-1",
                        "classification": "decision_needed",
                        "action": "ask_user",
                        "title": "Choose direction",
                        "rationale": "Two viable directions remain.",
                        "question": "Which direction should EXPLORE pursue?",
                        "options": ["option-a", "option-b"],
                        "evidence_refs": ["E1"],
                    }],
                })
        else:
            stdout = _json({})
        return ModelProviderResult(stdout, "", 0, monotonic() - started)


def _payload(prompt: str) -> dict[str, object]:
    marker = "Controller inputs:\n"
    index = prompt.rfind(marker)
    if index < 0:
        return {}
    value = json.loads(prompt[index + len(marker):])
    return value if isinstance(value, dict) else {}


class ExploreAskUserIntegrationTests(unittest.TestCase):
    def test_ask_user_waits_then_submit_rewinds_explore_with_decision_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = AskUserProvider()
            state = InMemoryStateStore()
            artifacts = InMemoryArtifactStore()
            worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
            registry = default_phase_function_registry()
            executor = PhaseExecutor(artifacts, worker, StaticClock(), registry, BundleRuntimeConfig(Path(directory)))
            service = RunOrchestrator(state, StaticIdGenerator("run-1"), executor, StaticClock(), artifacts, registry.invalidation_rules())

            started = service.execute(StartRun("Choose direction", root_bundle="EXPLORE_BUNDLE"))
            run_id = started.run.run_id
            result = _resume_until_status(service, run_id, "WAITING_FOR_USER")

            self.assertEqual("EXPLORE_BUNDLE", result.run.pending_decision.origin_bundle)
            self.assertEqual("explore-entry-1-decision", result.run.pending_decision.decision_id)
            self.assertEqual(("option-a", "option-b", "none_of_above"), result.run.pending_decision.options)
            pending = state.get(run_id).pending_decision
            self.assertEqual("ESCALATE", pending.effects[0].action.value)
            self.assertEqual("EXPLORATION_GAP", pending.effects[0].category.value)

            submitted = service.execute(SubmitUserDecision(run_id, "explore-entry-1-decision", "option-a"))
            self.assertEqual("RUNNING", submitted.run.status)
            self.assertEqual("EXPLORE_REQUEST_UNDERSTANDING", submitted.run.current_step.phase)

            completed = _resume_until_status(service, run_id, "COMPLETED")

            self.assertEqual("COMPLETED", completed.run.status)
            self.assertEqual(2, len(provider.outcome_inputs))
            history = provider.outcome_inputs[-1]["decision_history"]
            self.assertEqual("option-a", history[0]["response"])

    def test_repeated_same_ask_user_after_answer_fails_instead_of_looping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = AskUserProvider(resolve_after_decision=False)
            state = InMemoryStateStore()
            artifacts = InMemoryArtifactStore()
            worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
            registry = default_phase_function_registry()
            executor = PhaseExecutor(artifacts, worker, StaticClock(), registry, BundleRuntimeConfig(Path(directory)))
            service = RunOrchestrator(state, StaticIdGenerator("run-1"), executor, StaticClock(), artifacts, registry.invalidation_rules())

            started = service.execute(StartRun("Choose direction", root_bundle="EXPLORE_BUNDLE"))
            run_id = started.run.run_id
            _resume_until_status(service, run_id, "WAITING_FOR_USER")
            service.execute(SubmitUserDecision(run_id, "explore-entry-1-decision", "option-a"))

            failed = _resume_until_status(service, run_id, "FAILED")

            self.assertEqual("FAILED", failed.run.status)
            self.assertIn("already answered", failed.run.errors[-1].message)


def _resume_until_status(service: RunOrchestrator, run_id: str, status: str):
    result = None
    for _ in range(20):
        result = service.execute(ResumeRun(run_id))
        if result.run.status == status:
            return result
    raise AssertionError(f"run did not reach {status}: {result.run if result is not None else None}")


if __name__ == "__main__":
    unittest.main()
