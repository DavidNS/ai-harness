from __future__ import annotations

import json
import tempfile
import unittest
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from harness_v2.adapters.storage import FileStateStore
from harness_v2.backend.application.contracts import (
    CancelRun,
    GetRunState,
    InvalidRunStateError,
    ListRuns,
    ResumeRun,
    RunNotFoundError,
    RunStarted,
    StartRun,
    SubmitUserDecision,
    UserDecisionReceived,
)
from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.hosts.daemon.client import DaemonClient
from harness_v2.hosts.daemon.server import DaemonConfig, DaemonHttpServer

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class RunningDaemon:
    def __init__(self, state_root):
        self.server = DaemonHttpServer(DaemonConfig(state_root=state_root, port=0))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.client = DaemonClient(f"http://{host}:{port}", timeout=5.0)
        self.url = f"http://{host}:{port}"

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5.0)
        self.server.server_close()


class DaemonHostIntegrationTests(unittest.TestCase):
    def daemon(self, state_root):
        daemon = RunningDaemon(state_root)
        self.addCleanup(daemon.close)
        return daemon

    def test_health_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            daemon = self.daemon(temp)

            with urlopen(f"{daemon.url}/health", timeout=5.0) as response:
                payload = json.loads(response.read().decode("utf-8"))

            self.assertEqual({"status": "ok"}, payload)

    def test_client_runs_commands_and_queries_against_daemon_host(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            daemon = self.daemon(temp)

            started = daemon.client.execute(StartRun("Fix tests", strategy="EXPLORE_BUNDLE"))
            self.assertEqual("PENDING", started.run.status)
            self.assertEqual([RunStarted], [type(event) for event in started.events])

            state = daemon.client.query(GetRunState(started.run.run_id))
            self.assertEqual("PENDING", state.status)

            resumed = daemon.client.execute(ResumeRun(started.run.run_id))
            self.assertEqual("COMPLETED", resumed.run.status)
            self.assertEqual(("EXPLORE_BUNDLE",), resumed.run.completed_phases)

            listed = daemon.client.query(ListRuns())
            self.assertEqual([started.run.run_id], [run.run_id for run in listed.runs])

    def test_cancel_and_decision_route_through_backend_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = FileStateStore(temp)
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
            daemon = self.daemon(temp)

            cancelled = daemon.client.execute(CancelRun("run-active"))
            self.assertEqual("CANCELLED", cancelled.run.status)
            self.assertEqual(RunStatus.CANCELLED, store.get("run-active").status)

            decided = daemon.client.execute(SubmitUserDecision("run-waiting", "decision-1", "continue"))
            self.assertEqual("RUNNING", decided.run.status)
            self.assertEqual([UserDecisionReceived], [type(event) for event in decided.events])
            self.assertEqual(RunStatus.RUNNING, store.get("run-waiting").status)

    def test_event_stream_returns_ordered_events_after_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            daemon = self.daemon(temp)

            started = daemon.client.execute(StartRun("Fix tests", strategy="EXPLORE_BUNDLE"))
            first_events = daemon.client.events_after(0)
            self.assertEqual([(1, type(started.events[0]))], [(event_id, type(event)) for event_id, event in first_events])

            daemon.client.execute(ResumeRun(started.run.run_id))
            later_events = daemon.client.events_after(1)

            self.assertTrue(later_events)
            self.assertTrue(all(event_id > 1 for event_id, _event in later_events))

    def test_client_maps_backend_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            daemon = self.daemon(temp)

            with self.assertRaises(RunNotFoundError):
                daemon.client.query(GetRunState("missing"))

            started = daemon.client.execute(StartRun("Fix tests"))
            with self.assertRaises(InvalidRunStateError):
                daemon.client.execute(SubmitUserDecision(started.run.run_id, "decision-1", "continue"))

    def test_malformed_command_returns_bad_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            daemon = self.daemon(temp)
            request = Request(
                f"{daemon.url}/v1/commands",
                data=json.dumps({"type": "StartRun", "payload": {}}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5.0)

            self.assertEqual(400, raised.exception.code)
            payload = json.loads(raised.exception.read().decode("utf-8"))
            self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
