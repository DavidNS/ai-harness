from pathlib import Path
import tempfile
import unittest

from ai_harness.models import Complexity, Mode, RunState, Strategy
from ai_harness.stores import ArtifactStore
from ai_harness.stores.state.records import (
    artifact_metadata,
    decision_history,
    escalation_history,
    next_control_id,
    next_decision_id,
)


def make_state() -> RunState:
    return RunState(
        "run",
        "request",
        "INITIALIZING",
        Strategy.SDD,
        Mode.CODE,
        "modify_code",
        Complexity.MEDIUM,
        "local",
    )


class StateRecordHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.artifacts = ArtifactStore(self.root)
        self.state = make_state()

    def tearDown(self):
        self.temp.cleanup()

    def record_json_artifact(self, name: str, payload: object, phase: str = "CONTROL") -> None:
        self.artifacts.write_json(name, payload)
        self.state.artifacts[name] = artifact_metadata(self.artifacts, name, phase)

    def test_next_ids_reuse_first_available_slot_by_control_folder(self):
        self.record_json_artifact("decisions/D1/request.json", {"question": "one"})
        self.record_json_artifact("decisions/D3/request.json", {"question": "three"})
        self.record_json_artifact("escalations/E1.json", {"reason": "retry"})

        self.assertEqual("D2", next_decision_id(self.state))
        self.assertEqual("E2", next_control_id(self.state, "E", "escalations"))

    def test_decision_history_returns_requests_with_optional_answers(self):
        self.record_json_artifact("decisions/D2/request.json", {"question": "second"})
        self.record_json_artifact("decisions/D1/request.json", {"question": "first"})
        self.record_json_artifact("decisions/D1/answer.json", {"answer": "chosen"})
        self.state.artifacts["decisions/D3/request.json"] = {
            "path": "decisions/D3/request.json",
            "phase": "CONTROL",
            "checksum": "missing",
            "timestamp": "missing",
        }

        self.assertEqual(
            [
                {
                    "decision_id": "D1",
                    "request": {"question": "first"},
                    "answer": {"answer": "chosen"},
                },
                {"decision_id": "D2", "request": {"question": "second"}},
            ],
            decision_history(self.state, self.artifacts),
        )

    def test_escalation_history_returns_existing_escalation_files_in_order(self):
        self.record_json_artifact("escalations/E2.json", {"reason": "second"})
        self.record_json_artifact("escalations/E1.json", {"reason": "first"})
        self.record_json_artifact("escalations/E1/notes.json", {"ignored": True})
        self.state.artifacts["escalations/E3.json"] = {
            "path": "escalations/E3.json",
            "phase": "CONTROL",
            "checksum": "missing",
            "timestamp": "missing",
        }

        self.assertEqual(
            [
                {"escalation_id": "E1", "escalation": {"reason": "first"}},
                {"escalation_id": "E2", "escalation": {"reason": "second"}},
            ],
            escalation_history(self.state, self.artifacts),
        )


if __name__ == "__main__":
    unittest.main()
