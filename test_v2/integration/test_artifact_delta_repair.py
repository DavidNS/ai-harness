from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_v2.support.model_providers import FakeModelProvider
from test_v2.support.runtime import StaticClock
from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.bundle_artifacts import BundleArtifactGateway, BundleRuntimeConfig, BundleValidationError
from harness_v2.backend.application.phase_artifacts import sdd
from harness_v2.backend.application.phase_executor import PhaseExecutor, default_phase_function_registry
from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.model_provider import ModelProviderResult


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True)


def _partial_tasks() -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "tasks",
        "tasks": [{
            "id": "T1",
            "title": "Task",
            "depends_on": [],
            "acceptance_criteria": ["works"],
            "touched_paths": ["feature.py"],
            "broader_tests": [],
            "status": "pending",
        }],
    }


def _focused_delta() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "json_artifact_delta",
        "target_artifact": "tasks.json",
        "operations": [{"op": "add", "path": "/tasks/0/focused_tests", "value": [["python3", "-m", "unittest"]]}],
    }


def _runtime(root: Path, provider: FakeModelProvider, *, root_bundle: BundleName = BundleName.TASKS_BUNDLE, phase: PhaseName = PhaseName.TASKS_DRAFT) -> tuple[RunRecord, InMemoryArtifactStore, BundleArtifactGateway]:
    state = InMemoryStateStore()
    artifacts = InMemoryArtifactStore()
    run = RunRecord("run-1", "Fix", RunStatus.RUNNING, root_bundle=root_bundle, current_phase=phase)
    state.save(run)
    worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
    gateway = BundleArtifactGateway(artifacts, worker, BundleRuntimeConfig(root))
    return run, artifacts, gateway


class ArtifactDeltaRepairIntegrationTests(unittest.TestCase):
    def test_worker_json_repair_persists_revalidated_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeModelProvider([
                ModelProviderResult(_json(_partial_tasks()), "", 0, 0.0),
                ModelProviderResult(_json(_focused_delta()), "", 0, 0.0),
            ])
            run, artifacts, gateway = _runtime(Path(directory), provider)

            repaired = gateway.ensure_worker_json_with_repair(run, BundleName.TASKS_BUNDLE, PhaseName.TASKS_DRAFT, "tasks", "tasks.json", {}, sdd.validate_tasks_document)

            self.assertEqual([["python3", "-m", "unittest"]], repaired["tasks"][0]["focused_tests"])
            persisted = json.loads(artifacts.read("run-1", "tasks.json").decode("utf-8"))
            self.assertEqual(repaired, persisted)
            diagnostic = json.loads(artifacts.read("run-1", "validation/TASKS_BUNDLE_001-tasks.json-repair.json").decode("utf-8"))
            self.assertEqual("repaired", diagnostic["attempts"][0]["status"])

    def test_existing_valid_artifact_is_reused_without_repair_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeModelProvider([])
            run, artifacts, gateway = _runtime(Path(directory), provider)
            valid = _partial_tasks()
            valid["tasks"][0]["focused_tests"] = [["python3", "-m", "unittest"]]  # type: ignore[index]
            artifacts.write("run-1", "tasks.json", (_json(valid) + "\n").encode("utf-8"))

            result = gateway.ensure_worker_json_with_repair(run, BundleName.TASKS_BUNDLE, PhaseName.TASKS_DRAFT, "tasks", "tasks.json", {}, sdd.validate_tasks_document)

            self.assertEqual(valid, result)
            self.assertEqual([], provider.requests)


    def test_repair_attempts_build_on_partially_repaired_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            partial = _partial_tasks()
            del partial["tasks"][0]["touched_paths"]  # type: ignore[index]
            provider = FakeModelProvider([
                ModelProviderResult(_json(partial), "", 0, 0.0),
                ModelProviderResult(_json(_focused_delta()), "", 0, 0.0),
                ModelProviderResult(_json({
                    "schema_version": 1,
                    "kind": "json_artifact_delta",
                    "target_artifact": "tasks.json",
                    "operations": [{"op": "add", "path": "/tasks/0/touched_paths", "value": ["feature.py"]}],
                }), "", 0, 0.0),
            ])
            run, _artifacts, gateway = _runtime(Path(directory), provider)

            repaired = gateway.ensure_worker_json_with_repair(run, BundleName.TASKS_BUNDLE, PhaseName.TASKS_DRAFT, "tasks", "tasks.json", {}, sdd.validate_tasks_document, max_repairs=2)

            self.assertEqual([["python3", "-m", "unittest"]], repaired["tasks"][0]["focused_tests"])
            self.assertEqual(["feature.py"], repaired["tasks"][0]["touched_paths"])

    def test_invalid_delta_fails_after_bounded_repairs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            invalid_delta = dict(_focused_delta(), target_artifact="other.json")
            provider = FakeModelProvider([
                ModelProviderResult(_json(_partial_tasks()), "", 0, 0.0),
                ModelProviderResult(_json(invalid_delta), "", 0, 0.0),
                ModelProviderResult(_json(invalid_delta), "", 0, 0.0),
            ])
            run, artifacts, gateway = _runtime(Path(directory), provider)

            with self.assertRaises(BundleValidationError):
                gateway.ensure_worker_json_with_repair(run, BundleName.TASKS_BUNDLE, PhaseName.TASKS_DRAFT, "tasks", "tasks.json", {}, sdd.validate_tasks_document, max_repairs=2)

            diagnostic = json.loads(artifacts.read("run-1", "validation/TASKS_BUNDLE_001-tasks.json-repair.json").decode("utf-8"))
            self.assertEqual(2, len(diagnostic["attempts"]))

    def test_non_json_worker_output_can_be_repaired_with_root_delta(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            full = dict(_partial_tasks())
            full["tasks"] = [dict(full["tasks"][0], focused_tests=[["python3", "-m", "unittest"]])]  # type: ignore[index]
            provider = FakeModelProvider([
                ModelProviderResult("not json", "", 0, 0.0),
                ModelProviderResult(_json({"schema_version": 1, "kind": "json_artifact_delta", "target_artifact": "tasks.json", "operations": [{"op": "add", "path": "", "value": full}]}), "", 0, 0.0),
            ])
            run, _artifacts, gateway = _runtime(Path(directory), provider)

            repaired = gateway.ensure_worker_json_with_repair(run, BundleName.TASKS_BUNDLE, PhaseName.TASKS_DRAFT, "tasks", "tasks.json", {}, sdd.validate_tasks_document)

            self.assertEqual(full, repaired)

    def test_tasks_draft_phase_uses_delta_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = FakeModelProvider([
                ModelProviderResult(_json(_partial_tasks()), "", 0, 0.0),
                ModelProviderResult(_json(_focused_delta()), "", 0, 0.0),
            ])
            state = InMemoryStateStore()
            artifacts = InMemoryArtifactStore()
            run = RunRecord("run-1", "Fix", RunStatus.RUNNING, root_bundle=BundleName.TASKS_BUNDLE, current_phase=PhaseName.TASKS_DRAFT)
            state.save(run)
            worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
            registry = default_phase_function_registry()
            phase_executor = PhaseExecutor(artifacts, worker, StaticClock(), registry, BundleRuntimeConfig(root))
            _write_task_prerequisites(artifacts)

            draft_result = phase_executor.execute(run, BundleName.TASKS_BUNDLE, PhaseName.TASKS_DRAFT)
            self.assertIsNone(draft_result.tasks)

            validate_step = bundle_catalog.step_for_phase(BundleName.TASKS_BUNDLE, PhaseName.VALIDATE_JSON)
            validate_run = RunRecord(
                "run-1",
                "Fix",
                RunStatus.RUNNING,
                root_bundle=BundleName.TASKS_BUNDLE,
                current_step_id=validate_step.step_id,
                completed_step_ids=(bundle_catalog.start_step(BundleName.TASKS_BUNDLE).step_id,),
            )
            state.save(validate_run)
            result = phase_executor.execute(validate_run, BundleName.TASKS_BUNDLE, PhaseName.VALIDATE_JSON)

            self.assertEqual("T1", result.tasks[0].task_id)
            tasks = json.loads(artifacts.read("run-1", "tasks.json").decode("utf-8"))
            self.assertEqual([["python3", "-m", "unittest"]], tasks["tasks"][0]["focused_tests"])

    def test_proposal_validate_json_repairs_purpose_action_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_path = "docs/explorer/improvements/existing/improvement.md"
            provider = FakeModelProvider([
                ModelProviderResult(_json({
                    "schema_version": 1,
                    "kind": "json_artifact_delta",
                    "target_artifact": "purpose/bundle.json",
                    "operations": [
                        {"op": "replace", "path": "/implementation_mode", "value": "update_existing"},
                        {"op": "replace", "path": "/scope", "value": f"Update {target_path}."},
                    ],
                }), "", 0, 0.0),
            ])
            state = InMemoryStateStore()
            artifacts = InMemoryArtifactStore()
            validate_step = bundle_catalog.step_for_phase(BundleName.PROPOSAL_BUNDLE, PhaseName.VALIDATE_JSON)
            run = RunRecord(
                "run-1",
                "Fix",
                RunStatus.RUNNING,
                root_bundle=BundleName.PROPOSAL_BUNDLE,
                current_step_id=validate_step.step_id,
                completed_step_ids=(bundle_catalog.start_step(BundleName.PROPOSAL_BUNDLE).step_id,),
            )
            state.save(run)
            worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
            phase_executor = PhaseExecutor(artifacts, worker, StaticClock(), default_phase_function_registry(), BundleRuntimeConfig(root))
            artifacts.write("run-1", "explore/outcome_bundle.json", (_json({
                "schema_version": 1,
                "kind": "explore_outcome_bundle",
                "status": "ready_for_purpose",
                "normalized_request": {"summary": "Fix"},
                "triage": {},
                "evidence": [],
                "exploration_map": {},
                "entries": [{
                    "id": "entry-1",
                    "classification": "improvement",
                    "action": "update_existing",
                    "title": "Update existing",
                    "rationale": "A related improvement exists.",
                    "evidence_refs": [],
                    "target": {"path": target_path, "checksum": "abc"},
                }],
            }) + "\n").encode("utf-8"))
            artifacts.write("run-1", "purpose/bundle.json", (_json({
                "schema_version": 1,
                "kind": "purpose_bundle",
                "summary": "Fix",
                "implementation_mode": "direct_patch",
                "problem": "P",
                "scope": "S",
                "approach": "A",
                "outcome": "proceed",
                "selected_entries": ["entry-1"],
                "structural_work": [],
                "exclusions": ["none"],
                "acceptance_outline": ["works"],
                "evidence_refs": [],
            }) + "\n").encode("utf-8"))

            phase_executor.execute(run, BundleName.PROPOSAL_BUNDLE, PhaseName.VALIDATE_JSON)

            repaired = json.loads(artifacts.read("run-1", "purpose/bundle.json").decode("utf-8"))
            self.assertEqual("update_existing", repaired["implementation_mode"])
            self.assertEqual(f"Update {target_path}.", repaired["scope"])
            diagnostic = json.loads(artifacts.read("run-1", "validation/PROPOSAL_BUNDLE_002-purpose_bundle.json-repair.json").decode("utf-8"))
            self.assertEqual("repaired", diagnostic["attempts"][0]["status"])


def _write_task_prerequisites(artifacts: InMemoryArtifactStore) -> None:
    artifacts.write("run-1", "explore/outcome_bundle.json", (_json({
        "schema_version": 1,
        "kind": "explore_outcome_bundle",
        "evidence": [],
        "exploration_map": {},
        "status": "ready_for_purpose",
        "normalized_request": {},
        "triage": {},
        "entries": [{
            "id": "entry",
            "classification": "improvement",
            "action": "create",
            "title": "Fix",
            "rationale": "The requested fix is bounded enough for task planning.",
            "behavioral_delta": "The requested fix is implemented.",
            "minimum_verification": "Run focused tests for the requested fix.",
            "evidence_refs": [],
        }],
    }) + "\n").encode("utf-8"))
    artifacts.write("run-1", "purpose/bundle.json", (_json({
        "schema_version": 1,
        "kind": "purpose_bundle",
        "summary": "Fix",
        "implementation_mode": "direct_patch",
        "problem": "P",
        "scope": "S",
        "approach": "A",
        "outcome": "proceed",
        "selected_entries": ["entry"],
        "structural_work": [],
        "exclusions": ["none"],
        "acceptance_outline": ["works"],
        "evidence_refs": [],
    }) + "\n").encode("utf-8"))
    artifacts.write("run-1", "spec.json", (_json({
        "schema_version": 1,
        "kind": "spec",
        "summary": "Fix",
        "behavioral_requirements": ["works"],
        "acceptance_criteria": ["works"],
        "non_goals": ["none"],
    }) + "\n").encode("utf-8"))
    artifacts.write("run-1", "design.json", (_json({
        "schema_version": 1,
        "kind": "design",
        "boundaries": ["repo"],
        "invariants": ["state"],
        "implementation_approach": ["patch"],
        "test_strategy": {"unit": ["unit"], "integration": ["integration"], "acceptance": ["acceptance"]},
    }) + "\n").encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
