from pathlib import Path
import json
import tempfile
import unittest
from ai_harness.errors import StateError
from ai_harness.models import *
from ai_harness.stores import ArtifactStore, StateStore


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.artifacts = ArtifactStore(self.root); self.store = StateStore(self.root, self.artifacts)
        self.state = RunState("run", "request", "INITIALIZING", Strategy.SDD, Mode.CODE, "modify_code", Complexity.MEDIUM, "local")
        self.store.save(self.state)

    def tearDown(self): self.temp.cleanup()

    def test_mutations_validate_transitions(self):
        self.store.mark_phase_completed("INITIALIZING")
        self.store.mark_phase_started("LOADING_KNOWLEDGE")
        self.assertEqual(self.store.load().current_phase, "LOADING_KNOWLEDGE")
        with self.assertRaises(Exception): self.store.mark_phase_started("ROUTING")

    def test_resume_rejects_corrupt_artifact(self):
        self.artifacts.write("explore.md", "one")
        self.store.record_artifact("explore.md", "EXPLORE")
        self.artifacts.write("explore.md", "two")
        with self.assertRaises(StateError): self.store.validate_resume("run")

    def test_resume_rejects_wrong_run_id(self):
        with self.assertRaises(StateError): self.store.validate_resume("other")


    def test_load_rejects_non_object_state_json(self):
        self.artifacts.write("state.json", "[]")

        with self.assertRaises(StateError) as caught:
            self.store.load()

        self.assertEqual("state must be a JSON object", str(caught.exception))

    def test_load_wraps_malformed_object_state(self):
        payload = self.state.to_dict()
        del payload["run_id"]
        self.artifacts.write("state.json", json.dumps(payload))

        with self.assertRaises(StateError) as caught:
            self.store.load()

        self.assertEqual("state is malformed", str(caught.exception))

    def test_waiting_decision_records_request_and_answer(self):
        from ai_harness.control_outputs import DecisionAnswer, DecisionRequest
        prefix = ["INITIALIZING", "LOADING_KNOWLEDGE", "DETECTING_INTENT", "ROUTING", "SELECTING_STRATEGY", "EXPLORE", "PURPOSE", "SPEC"]
        self.store.update(completed_phases=prefix, current_phase="DESIGN")
        waiting = self.store.record_decision_request(
            DecisionRequest("DESIGN", "Two designs are viable.", "Should compatibility be preserved?", ("Compatibility is lower risk.",)),
            target_phase="DESIGN",
        )
        self.assertEqual(RunStatus.WAITING_FOR_USER, waiting.status)
        self.assertEqual("D1", waiting.pending_decision.id)
        self.assertTrue(self.artifacts.exists("decisions/D1/request.json"))
        self.store.validate_resume("run")

        active = self.store.record_decision_answer(DecisionAnswer("D1", "Preserve compatibility."))
        self.assertEqual(RunStatus.ACTIVE, active.status)
        self.assertIsNone(active.pending_decision)
        self.assertTrue(self.artifacts.exists("decisions/D1/answer.json"))
        self.store.validate_resume("run")

    def test_waiting_resume_rejects_corrupt_decision_request(self):
        from ai_harness.control_outputs import DecisionRequest
        prefix = ["INITIALIZING", "LOADING_KNOWLEDGE", "DETECTING_INTENT", "ROUTING", "SELECTING_STRATEGY", "EXPLORE", "PURPOSE", "SPEC"]
        self.store.update(completed_phases=prefix, current_phase="DESIGN")
        self.store.record_decision_request(
            DecisionRequest("DESIGN", "Two designs are viable.", "Should compatibility be preserved?", ("Compatibility is lower risk.",)),
            target_phase="DESIGN",
        )
        self.artifacts.write("decisions/D1/request.json", "{}")
        with self.assertRaises(StateError):
            self.store.validate_resume("run")

    def test_answer_rejects_selected_option_without_matching_request_option(self):
        from ai_harness.control_outputs import DecisionAnswer, DecisionRequest
        prefix = ["INITIALIZING", "LOADING_KNOWLEDGE", "DETECTING_INTENT", "ROUTING", "SELECTING_STRATEGY", "EXPLORE", "PURPOSE", "SPEC"]
        self.store.update(completed_phases=prefix, current_phase="DESIGN")
        self.store.record_decision_request(
            DecisionRequest("DESIGN", "A free-form decision is needed.", "Which behavior should be used?", ("No fixed options were supplied.",)),
            target_phase="DESIGN",
        )
        with self.assertRaises(StateError):
            self.store.record_decision_answer(DecisionAnswer("D1", "Use the default.", "missing"))

    def test_phase_escalation_invalidates_downstream_artifacts_and_tasks(self):
        from ai_harness.control_outputs import PhaseEscalation
        completed = ["INITIALIZING", "LOADING_KNOWLEDGE", "DETECTING_INTENT", "ROUTING", "SELECTING_STRATEGY", "EXPLORE", "PURPOSE", "SPEC"]
        self.store.update(completed_phases=completed, current_phase="DESIGN", tasks=[Task("T1", "Task")])
        for name, phase in (("spec.md", "SPEC"), ("design.md", "DESIGN"), ("tasks.json", "TASKS")):
            self.artifacts.write(name, phase)
            self.store.record_artifact(name, phase)
        state = self.store.record_phase_escalation(
            PhaseEscalation("DESIGN", "SPEC", "The decision changes requirements."),
            active_graph_phase="DESIGN",
        )
        self.assertEqual("SPEC", state.current_phase)
        self.assertEqual(completed[:-1], state.completed_phases)
        self.assertEqual([], state.tasks)
        self.assertFalse(self.artifacts.exists("spec.md"))
        self.assertFalse(self.artifacts.exists("design.md"))
        self.assertTrue(self.artifacts.exists("escalations/E1.json"))
        self.store.validate_resume("run")
        history = self.store.escalation_history()
        self.assertEqual("E1", history[0]["escalation_id"])
        self.assertEqual("DESIGN", history[0]["escalation"]["origin_phase"])
        self.assertEqual("SPEC", history[0]["escalation"]["target_phase"])
        self.assertEqual("DESIGN", history[0]["escalation"]["active_graph_phase"])
        self.assertEqual("The decision changes requirements.", history[0]["escalation"]["reason"])
