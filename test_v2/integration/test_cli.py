from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from harness_v2.adapters.storage import FileStateStore
from harness_v2.backend.domain.decisions import PendingDecision
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

    def test_cli_module_starts_simulated_run_and_persists_for_queries(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"

            started = self.run_cli(state_root, "start", "Fix", "tests")
            self.assertEqual(0, started.returncode, started.stderr)
            self.assertIn("Run: ", started.stdout)
            self.assertIn("Status: COMPLETED", started.stdout)
            self.assertIn("Event: RunStarted", started.stdout)
            self.assertIn("Event: PhaseStarted phase=EXPLORE_BUNDLE", started.stdout)
            self.assertIn("Event: PhaseCompleted phase=EXPLORE_BUNDLE", started.stdout)
            self.assertIn("Event: RunCompleted", started.stdout)

            run_id = next(line.split(": ", 1)[1] for line in started.stdout.splitlines() if line.startswith("Run: "))

            listed = self.run_cli(state_root, "list")
            self.assertEqual(0, listed.returncode, listed.stderr)
            self.assertIn("Runs: 1", listed.stdout)
            self.assertIn(f"Run: {run_id} status=COMPLETED", listed.stdout)

            fetched = self.run_cli(state_root, "get", run_id)
            self.assertEqual(0, fetched.returncode, fetched.stderr)
            self.assertIn(f"Run: {run_id}", fetched.stdout)
            self.assertIn("Request: Fix tests", fetched.stdout)

            resumed = self.run_cli(state_root, "resume", run_id)
            self.assertNotEqual(0, resumed.returncode)
            self.assertIn("error:", resumed.stderr)

            state = self.run_cli(state_root, "state", run_id)
            self.assertEqual(0, state.returncode, state.stderr)
            self.assertIn("Status: COMPLETED", state.stdout)

            actions = self.run_cli(state_root, "actions", run_id)
            self.assertEqual(0, actions.returncode, actions.stderr)
            self.assertIn("Actions: none", actions.stdout)

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

    def test_cli_missing_run_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            missing = self.run_cli(Path(temp) / "runtime", "get", "missing")

            self.assertNotEqual(0, missing.returncode)
            self.assertIn("error:", missing.stderr)


if __name__ == "__main__":
    unittest.main()
