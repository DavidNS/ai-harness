from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from threading import Thread

from harness_v2.adapters.storage import FileStateStore
from harness_v2.backend.application.contracts import (
    GetKnowledgePatch,
    ListKnowledgePatches,
    ListRuns,
    RejectKnowledgePatch,
    ResumeRun,
    StartRun,
    SubmitUserDecision,
)
from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.knowledge import parse_learning_proposal
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.hosts.daemon.client import DaemonClient
from harness_v2.hosts.daemon.server import DaemonConfig, DaemonHttpServer
from harness_v2.hosts.in_process.host import InProcessHost
from test_v2.support.model_providers import ScriptedModelProvider
from test_v2.support.runtime import memory_orchestrator

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class RunningDaemon:
    def __init__(self, state_root: Path):
        self.server = DaemonHttpServer(DaemonConfig(state_root=state_root, port=0, model_provider=ScriptedModelProvider()))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.client = DaemonClient(f"http://{host}:{port}", timeout=5.0)

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5.0)
        self.server.server_close()


class V2AcceptanceSmokeTests(unittest.TestCase):
    def daemon(self, state_root: Path) -> RunningDaemon:
        daemon = RunningDaemon(state_root)
        self.addCleanup(daemon.close)
        return daemon

    def test_start_list_resume_and_daemon_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            daemon = self.daemon(Path(temp) / "runtime")

            started = daemon.client.execute(StartRun("Fix tests", root_bundle="EXPLORE_BUNDLE"))
            listed = daemon.client.query(ListRuns())
            resumed = daemon.client.execute(ResumeRun(started.run.run_id))
            events = daemon.client.events_after(0)

            self.assertEqual([started.run.run_id], [run.run_id for run in listed.runs])
            self.assertEqual("EXPLORE_BUNDLE", resumed.run.current_step.bundle)
            self.assertIn(resumed.run.current_step.phase, {"EXPLORE_REQUEST_UNDERSTANDING", "EXPLORE_CONTEXT_PACK"})
            self.assertIn("RunStarted", [type(event).__name__ for _event_id, event in events])

    def test_decision_answer_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"
            store = FileStateStore(state_root)
            store.save(
                RunRecord(
                    "run-waiting",
                    "Choose path",
                    RunStatus.WAITING_FOR_USER,
                    current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING,
                    pending_decision=PendingDecision("decision-1", BundleName.EXPLORE_BUNDLE, "Choose", TIMESTAMP, options=("continue",)),
                )
            )
            daemon = self.daemon(state_root)

            result = daemon.client.execute(SubmitUserDecision("run-waiting", "decision-1", "continue"))

            self.assertEqual("RUNNING", result.run.status)
            self.assertEqual(RunStatus.RUNNING, store.get("run-waiting").status)

    def test_knowledge_patch_query_and_reject_smoke(self) -> None:
        service, _state, _artifacts, knowledge = memory_orchestrator()
        patch = knowledge.create_patch("run-1", BundleName.EXPLORE_BUNDLE, parse_learning_proposal(_proposal()), TIMESTAMP)

        listed = service.query(ListKnowledgePatches(run_id="run-1"))
        fetched = service.query(GetKnowledgePatch(patch.patch_id))
        rejected = service.execute(RejectKnowledgePatch(patch.patch_id, "not durable"))

        self.assertEqual((patch.patch_id,), tuple(item.patch_id for item in listed.patches))
        self.assertEqual(patch.patch_id, fetched.patch.patch_id)
        self.assertEqual("REJECTED", rejected.patch.status)

    def test_git_ci_smoke_path_materializes_release_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "runtime"
            repository = Path(temp) / "repo"
            repository.mkdir()
            host = InProcessHost(state_root=root, working_directory=repository, branch_mode="current", github_ci_mode="baseline", model_provider=ScriptedModelProvider())

            started = host.execute(StartRun("Fix tests", root_bundle="EXPLORE_BUNDLE"))
            host.execute(ResumeRun(started.run.run_id))
            host.execute(ResumeRun(started.run.run_id))

            self.assertTrue((root / "runs" / started.run.run_id / "artifacts" / "git-run.json").is_file())
            self.assertTrue((root / "runs" / started.run.run_id / "artifacts" / "ci-signals.json").is_file())
            self.assertTrue((root / "runs" / started.run.run_id / "artifacts" / "ci-signals" / "trunk-baseline.json").is_file())


def _proposal() -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "learning",
        "proposal_manifest": {"schema_version": 1, "proposal_id": "proposal.v2.acceptance.001", "summary": "Learn", "source_artifacts": ["explore/outcome_bundle.json"], "claims_file": "proposed_claims.jsonl"},
        "proposed_claims": [{"id": "claim.v2.acceptance.001", "domain": "harness", "subjects": ["v2"], "files": ["harness_v2/backend/domain/lifecycle.py"], "symbols": [], "claim_type": "behavior", "text": "Bundles compose phases.", "status": "active", "evidence": [{"type": "code", "file": "harness_v2/backend/domain/lifecycle.py"}], "valid_from": None, "valid_until": None, "last_verified": None}],
        "proposed_relations": [],
    }


if __name__ == "__main__":
    unittest.main()
