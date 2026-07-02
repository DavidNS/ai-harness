from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from threading import Thread

from harness_v2.adapters.storage import FileStateStore
from harness_v2.backend.application.contracts import StartRun
from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.frontends.ui.controller import UiController
from harness_v2.frontends.ui.renderer import render
from harness_v2.frontends.ui.state import UiState
from harness_v2.hosts.daemon.client import DaemonClient
from harness_v2.hosts.daemon.server import DaemonConfig, DaemonHttpServer

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class RunningDaemon:
    def __init__(self, state_root: Path):
        self.server = DaemonHttpServer(DaemonConfig(state_root=state_root, port=0))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.client = DaemonClient(f"http://{host}:{port}", timeout=5.0)

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5.0)
        self.server.server_close()


class UiDaemonIntegrationTests(unittest.TestCase):
    def daemon(self, state_root: Path) -> RunningDaemon:
        daemon = RunningDaemon(state_root)
        self.addCleanup(daemon.close)
        return daemon

    def test_ui_observes_run_progress_and_completion_through_daemon(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            daemon = self.daemon(Path(temp) / "runtime")
            controller = UiController(daemon.client)

            state = controller.start(UiState(), "Fix tests", strategy="EXPLORE_BUNDLE")
            self.assertEqual("PENDING", state.selected_run.status if state.selected_run else None)

            state = controller.resume(state)
            output = render(state)

            self.assertIn("status: COMPLETED", output)
            self.assertIn("completed: EXPLORE_BUNDLE", output)
            self.assertIn("RunCompleted", output)

    def test_ui_displays_and_submits_pending_decision_through_daemon(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_root = Path(temp) / "runtime"
            store = FileStateStore(state_root)
            store.save(
                RunRecord(
                    "run-waiting",
                    "Choose path",
                    RunStatus.WAITING_FOR_USER,
                    RunStrategy.SDD,
                    current_phase=PhaseName.EXPLORE_BUNDLE,
                    pending_decision=PendingDecision(
                        "decision-1",
                        PhaseName.EXPLORE_BUNDLE,
                        "Choose",
                        TIMESTAMP,
                        options=("continue", "cancel"),
                    ),
                )
            )
            daemon = self.daemon(state_root)
            controller = UiController(daemon.client)

            state = controller.select(controller.refresh(UiState()), "run-waiting")
            self.assertIn("pending decision:", render(state))
            self.assertIn("options: continue, cancel", render(state))

            state = controller.submit_decision(state, "continue")

            self.assertEqual("RUNNING", state.selected_run.status if state.selected_run else None)
            self.assertIn("submitted decision", render(state))
            self.assertEqual(RunStatus.RUNNING, store.get("run-waiting").status)

    def test_ui_polls_daemon_event_stream_with_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            daemon = self.daemon(Path(temp) / "runtime")
            controller = UiController(daemon.client)
            daemon.client.execute(StartRun("Fix tests", strategy="EXPLORE_BUNDLE"))

            state = controller.poll_events(UiState())

            self.assertEqual(1, state.event_cursor)
            self.assertEqual("RunStarted", state.events[0].event_type)


if __name__ == "__main__":
    unittest.main()
