from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Thread

from harness_v2.adapters.storage import FileStateStore
from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.hosts.daemon.server import DaemonConfig, DaemonHttpServer

ROOT = Path(__file__).resolve().parents[2]
TIMESTAMP = "2026-07-01T00:00:00+00:00"


class RunningDaemon:
    def __init__(self, state_root: Path):
        self.server = DaemonHttpServer(DaemonConfig(state_root=state_root, port=0))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.url = f"http://{host}:{port}"

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5.0)
        self.server.server_close()


class CliDaemonIntegrationTests(unittest.TestCase):
    def run_cli(self, daemon_url: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", "-m", "harness_v2.frontends.cli", "--host-mode", "daemon", "--daemon-url", daemon_url, *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_can_use_daemon_backed_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"
            daemon = RunningDaemon(state_root)
            self.addCleanup(daemon.close)

            started = self.run_cli(daemon.url, "start", "--strategy", "EXPLORE_BUNDLE", "Fix", "tests")
            self.assertEqual(0, started.returncode, started.stderr)
            self.assertIn("Status: PENDING", started.stdout)
            self.assertIn("Event: RunStarted", started.stdout)
            run_id = next(line.split(": ", 1)[1] for line in started.stdout.splitlines() if line.startswith("Run: "))

            listed = self.run_cli(daemon.url, "list")
            self.assertEqual(0, listed.returncode, listed.stderr)
            self.assertIn(f"Run: {run_id} status=PENDING", listed.stdout)

            resumed = self.run_cli(daemon.url, "resume", run_id)
            self.assertEqual(0, resumed.returncode, resumed.stderr)
            self.assertIn("Status: COMPLETED", resumed.stdout)
            self.assertIn("Event: RunCompleted", resumed.stdout)

    def test_cli_daemon_mode_routes_cancel_and_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"
            store = FileStateStore(state_root)
            store.save(RunRecord("run-active", "Fix tests", RunStatus.RUNNING, RunStrategy.SDD, current_phase=PhaseName.EXPLORE_BUNDLE))
            store.save(
                RunRecord(
                    "run-waiting",
                    "Choose path",
                    RunStatus.WAITING_FOR_USER,
                    RunStrategy.SDD,
                    current_phase=PhaseName.EXPLORE_BUNDLE,
                    pending_decision=PendingDecision("decision-1", PhaseName.EXPLORE_BUNDLE, "Choose", TIMESTAMP, options=("continue", "cancel")),
                )
            )
            daemon = RunningDaemon(state_root)
            self.addCleanup(daemon.close)

            cancelled = self.run_cli(daemon.url, "cancel", "run-active")
            self.assertEqual(0, cancelled.returncode, cancelled.stderr)
            self.assertIn("Status: CANCELLED", cancelled.stdout)
            self.assertIn("Event: RunCancelled", cancelled.stdout)

            decided = self.run_cli(daemon.url, "decision", "run-waiting", "decision-1", "continue")
            self.assertEqual(0, decided.returncode, decided.stderr)
            self.assertIn("Status: RUNNING", decided.stdout)
            self.assertIn("Event: UserDecisionReceived", decided.stdout)


if __name__ == "__main__":
    unittest.main()
