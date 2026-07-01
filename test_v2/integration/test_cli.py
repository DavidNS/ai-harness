from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from harness_v2.adapters.storage import FileArtifactStore, FileStateStore
from harness_v2.backend.domain.decisions import DecisionAction, DecisionEffect, PendingDecision
from harness_v2.backend.domain.errors import ErrorRecord
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord

ROOT = Path(__file__).resolve().parents[2]
TIMESTAMP = "2026-07-01T00:00:00+00:00"


class CliIntegrationTests(unittest.TestCase):
    def run_cli(self, state_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", "-m", "harness_v2.frontends.cli", "--state-root", str(state_root), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_module_starts_pending_run_then_resume_executes_explore_and_advances_to_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"

            started = self.run_cli(state_root, "start", "Fix", "tests")
            self.assertEqual(0, started.returncode, started.stderr)
            self.assertIn("Run: ", started.stdout)
            self.assertIn("Status: PENDING", started.stdout)
            self.assertIn("Event: RunStarted", started.stdout)

            run_id = next(line.split(": ", 1)[1] for line in started.stdout.splitlines() if line.startswith("Run: "))

            listed = self.run_cli(state_root, "list")
            self.assertEqual(0, listed.returncode, listed.stderr)
            self.assertIn("Runs: 1", listed.stdout)
            self.assertIn(f"Run: {run_id} status=PENDING", listed.stdout)

            fetched = self.run_cli(state_root, "get", run_id)
            self.assertEqual(0, fetched.returncode, fetched.stderr)
            self.assertIn(f"Run: {run_id}", fetched.stdout)
            self.assertIn("Request: Fix tests", fetched.stdout)

            resumed = self.run_cli(state_root, "resume", run_id)
            self.assertEqual(0, resumed.returncode, resumed.stderr)
            self.assertIn("Status: RUNNING", resumed.stdout)
            self.assertIn("Current phase: PROPOSAL_BUNDLE", resumed.stdout)
            self.assertIn("Completed phases: EXPLORE_BUNDLE", resumed.stdout)
            self.assertIn("Event: RunResumed", resumed.stdout)
            self.assertIn("Event: PhaseStarted phase=EXPLORE_BUNDLE", resumed.stdout)
            self.assertIn("Event: PhaseCompleted phase=EXPLORE_BUNDLE", resumed.stdout)
            self.assertIn("Event: PhaseStarted phase=PROPOSAL_BUNDLE", resumed.stdout)

            state = self.run_cli(state_root, "state", run_id)
            self.assertEqual(0, state.returncode, state.stderr)
            self.assertIn("Status: RUNNING", state.stdout)
            self.assertIn("Current phase: PROPOSAL_BUNDLE", state.stdout)

            actions = self.run_cli(state_root, "actions", run_id)
            self.assertEqual(0, actions.returncode, actions.stderr)
            self.assertIn("Actions: resume, cancel", actions.stdout)



    def test_cli_sdd_completes_with_successive_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"
            started = self.run_cli(state_root, "start", "Fix", "tests")
            self.assertEqual(0, started.returncode, started.stderr)
            run_id = next(line.split(": ", 1)[1] for line in started.stdout.splitlines() if line.startswith("Run: "))

            outputs = []
            for _ in range(6):
                resumed = self.run_cli(state_root, "resume", run_id)
                self.assertEqual(0, resumed.returncode, resumed.stderr)
                outputs.append(resumed.stdout)

            self.assertIn("Current phase: PROPOSAL_BUNDLE", outputs[0])
            self.assertIn("Current phase: SPEC_BUNDLE", outputs[1])
            self.assertIn("Current phase: DESIGN_BUNDLE", outputs[2])
            self.assertIn("Current phase: TASKS_BUNDLE", outputs[3])
            self.assertIn("Current phase: TDD_BUNDLE", outputs[4])
            self.assertIn("Status: COMPLETED", outputs[5])
            self.assertIn("Event: RunCompleted", outputs[5])

    def test_cli_start_with_explore_strategy_resume_completes_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"

            started = self.run_cli(state_root, "start", "--strategy", "EXPLORE_BUNDLE", "Fix", "tests")
            self.assertEqual(0, started.returncode, started.stderr)
            run_id = next(line.split(": ", 1)[1] for line in started.stdout.splitlines() if line.startswith("Run: "))

            resumed = self.run_cli(state_root, "resume", run_id)

            self.assertEqual(0, resumed.returncode, resumed.stderr)
            self.assertIn("Status: COMPLETED", resumed.stdout)
            self.assertIn("Completed phases: EXPLORE_BUNDLE", resumed.stdout)
            self.assertIn("Event: RunCompleted", resumed.stdout)


    def test_cli_explorer_strategy_completes_with_successive_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"
            started = self.run_cli(state_root, "start", "--strategy", "EXPLORER", "Investigate", "explorer")
            self.assertEqual(0, started.returncode, started.stderr)
            run_id = next(line.split(": ", 1)[1] for line in started.stdout.splitlines() if line.startswith("Run: "))

            outputs = []
            for _ in range(6):
                resumed = self.run_cli(state_root, "resume", run_id)
                self.assertEqual(0, resumed.returncode, resumed.stderr)
                outputs.append(resumed.stdout)

            self.assertIn("Current phase: EXPLORER_DISCOVERY", outputs[0])
            self.assertIn("Current phase: EXPLORER_DECISION", outputs[1])
            self.assertIn("Current phase: EXPLORER_ARTIFACT", outputs[2])
            self.assertIn("Current phase: EXPLORER_REVIEW", outputs[3])
            self.assertIn("Current phase: EXPLORER_DISTILL", outputs[4])
            self.assertIn("Status: COMPLETED", outputs[5])
            self.assertIn("Completed phases: EXPLORER_INTAKE, EXPLORER_DISCOVERY, EXPLORER_DECISION, EXPLORER_ARTIFACT, EXPLORER_REVIEW, EXPLORER_DISTILL", outputs[5])

    def test_cli_cancel_and_decision_use_host_contract_with_file_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"
            store = FileStateStore(state_root)
            store.save(
                RunRecord(
                    run_id="run-active",
                    request="Fix tests",
                    status=RunStatus.RUNNING,
                    strategy=RunStrategy.SDD,
                    current_phase=PhaseName.EXPLORE_BUNDLE,
                )
            )
            store.save(
                RunRecord(
                    run_id="run-waiting",
                    request="Choose path",
                    status=RunStatus.WAITING_FOR_USER,
                    strategy=RunStrategy.SDD,
                    current_phase=PhaseName.EXPLORE_BUNDLE,
                    pending_decision=PendingDecision(
                        decision_id="decision-1",
                        origin_phase=PhaseName.EXPLORE_BUNDLE,
                        prompt="Choose",
                        created_at=TIMESTAMP,
                        options=("continue", "cancel"),
                    ),
                )
            )

            cancelled = self.run_cli(state_root, "cancel", "run-active")
            self.assertEqual(0, cancelled.returncode, cancelled.stderr)
            self.assertIn("Status: CANCELLED", cancelled.stdout)
            self.assertIn("Event: RunCancelled", cancelled.stdout)
            self.assertEqual(RunStatus.CANCELLED, store.get("run-active").status)

            decided = self.run_cli(state_root, "decision", "run-waiting", "decision-1", "continue")
            self.assertEqual(0, decided.returncode, decided.stderr)
            self.assertIn("Status: RUNNING", decided.stdout)
            self.assertIn("Event: UserDecisionReceived", decided.stdout)
            self.assertEqual(RunStatus.RUNNING, store.get("run-waiting").status)

    def test_cli_state_displays_decision_prompt_and_decision_can_escalate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"
            store = FileStateStore(state_root)
            artifacts = FileArtifactStore(state_root)
            store.save(
                RunRecord(
                    run_id="run-waiting",
                    request="Choose path",
                    status=RunStatus.WAITING_FOR_USER,
                    strategy=RunStrategy.SDD,
                    current_phase=PhaseName.DESIGN_BUNDLE,
                    completed_phases=(PhaseName.EXPLORE_BUNDLE, PhaseName.PROPOSAL_BUNDLE, PhaseName.SPEC_BUNDLE),
                    pending_decision=PendingDecision(
                        decision_id="decision-1",
                        origin_phase=PhaseName.DESIGN_BUNDLE,
                        prompt="Continue or revisit the spec?",
                        created_at=TIMESTAMP,
                        options=("continue", "respec"),
                        effects=(DecisionEffect("respec", DecisionAction.ESCALATE, PhaseName.SPEC_BUNDLE),),
                    ),
                )
            )
            artifacts.write("run-waiting", "spec.md", b"spec")
            artifacts.write("run-waiting", "design.md", b"design")

            state = self.run_cli(state_root, "state", "run-waiting")
            self.assertEqual(0, state.returncode, state.stderr)
            self.assertIn("Pending decision: decision-1 phase=DESIGN_BUNDLE options=continue,respec", state.stdout)
            self.assertIn("Prompt: Continue or revisit the spec?", state.stdout)

            decided = self.run_cli(state_root, "decision", "run-waiting", "decision-1", "respec")
            self.assertEqual(0, decided.returncode, decided.stderr)
            self.assertIn("Status: RUNNING", decided.stdout)
            self.assertIn("Current phase: SPEC_BUNDLE", decided.stdout)
            self.assertIn("Event: PhaseEscalated from=DESIGN_BUNDLE target=SPEC_BUNDLE", decided.stdout)
            self.assertEqual(PhaseName.SPEC_BUNDLE, store.get("run-waiting").current_phase)


    def test_cli_retry_reopens_failed_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"
            store = FileStateStore(state_root)
            artifacts = FileArtifactStore(state_root)
            store.save(
                RunRecord(
                    run_id="run-failed",
                    request="Fix design",
                    status=RunStatus.FAILED,
                    strategy=RunStrategy.SDD,
                    completed_phases=(PhaseName.EXPLORE_BUNDLE, PhaseName.PROPOSAL_BUNDLE, PhaseName.SPEC_BUNDLE),
                    errors=(ErrorRecord("DESIGN_BUNDLE_FAILED", "bad design", phase="DESIGN_BUNDLE", timestamp=TIMESTAMP),),
                )
            )
            artifacts.write("run-failed", "design.md", b"stale")

            retried = self.run_cli(state_root, "retry", "run-failed", "DESIGN_BUNDLE")

            self.assertEqual(0, retried.returncode, retried.stderr)
            self.assertIn("Status: RUNNING", retried.stdout)
            self.assertIn("Current phase: DESIGN_BUNDLE", retried.stdout)
            self.assertIn("Event: PhaseRetryStarted phase=DESIGN_BUNDLE", retried.stdout)
            self.assertEqual(RunStatus.RUNNING, store.get("run-failed").status)


    def test_cli_missing_run_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            missing = self.run_cli(Path(temp) / "runtime", "get", "missing")

            self.assertNotEqual(0, missing.returncode)
            self.assertIn("error:", missing.stderr)


if __name__ == "__main__":
    unittest.main()
