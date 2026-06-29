import unittest
from ai_harness.errors import ValidationError
from ai_harness.models import *


class ModelTests(unittest.TestCase):
    def test_route_validates_intent_and_confidence(self):
        Route(Mode.CODE, "modify_code", .8)
        Route(Mode.CODE, "explorer_request", .8)
        with self.assertRaises(ValidationError):
            Route(Mode.CODE, "research", .8)

    def test_strategy_accepts_sdd_resolution_levels(self):
        StrategyDecision(Strategy.EXPLORER, Complexity.MEDIUM, 1, "explore")
        StrategyDecision(Strategy.SDD, Complexity.LOW, 1, "small")
        StrategyDecision(Strategy.SDD, Complexity.HIGH, 1, "large")

    def test_tasks_reject_unknown_and_cyclic_dependencies(self):
        with self.assertRaises(ValidationError):
            validate_tasks([Task("a", "A", ("missing",))])
        with self.assertRaises(ValidationError):
            validate_tasks([Task("a", "A", ("b",)), Task("b", "B", ("a",))])

    def test_selects_first_ready_pending_task(self):
        tasks = [Task("a", "A", status=TaskStatus.COMPLETED), Task("b", "B", ("a",)), Task("c", "C")]
        self.assertEqual(select_ready_task(tasks).id, "b")


    def test_waiting_status_requires_matching_pending_decision(self):
        pending = PendingDecision("D1", "DESIGN", "DESIGN", "decisions/D1/request.json")
        state = RunState(
            "run", "request", "DESIGN", Strategy.SDD, Mode.CODE,
            "modify_code", Complexity.MEDIUM, "local",
            selected_model="gpt-5",
            status=RunStatus.WAITING_FOR_USER,
            pending_decision=pending,
        )
        state.validate()
        self.assertEqual("gpt-5", state.to_dict()["selected_model"])
        with self.assertRaises(ValidationError):
            RunState(
                "run", "request", "DESIGN", Strategy.SDD, Mode.CODE,
                "modify_code", Complexity.MEDIUM, "local",
                status=RunStatus.WAITING_FOR_USER,
            ).validate()
        with self.assertRaises(ValidationError):
            RunState(
                "run", "request", "SPEC", Strategy.SDD, Mode.CODE,
                "modify_code", Complexity.MEDIUM, "local",
                status=RunStatus.WAITING_FOR_USER,
                pending_decision=pending,
            ).validate()
        with self.assertRaises(ValidationError):
            RunState(
                "run", "request", "DESIGN", Strategy.SDD, Mode.CODE,
                "modify_code", Complexity.MEDIUM, "local",
                pending_decision=pending,
            ).validate()

    def test_run_state_from_dict_round_trips_state_contract(self):
        state = RunState(
            "run", "request", "DESIGN", Strategy.SDD, Mode.CODE,
            "modify_code", Complexity.MEDIUM, "local",
            selected_provider_command=("codex", "--model", "gpt-5"),
            selected_model="gpt-5",
            completed_phases=["INITIALIZING"],
            tasks=[Task("T1", "Task", acceptance_criteria=("done",), test_commands=("pytest",))],
            errors=[ErrorRecord("phase_failed", "bad output", "DESIGN")],
        )
        loaded = run_state_from_dict(state.to_dict())

        self.assertEqual(state.to_dict(), loaded.to_dict())
        self.assertEqual(("codex", "--model", "gpt-5"), loaded.selected_provider_command)
        self.assertEqual("gpt-5", loaded.selected_model)

    def test_run_state_from_dict_round_trips_waiting_decision(self):
        pending = PendingDecision("D1", "DESIGN", "DESIGN", "decisions/D1/request.json")
        state = RunState(
            "run", "request", "DESIGN", Strategy.SDD, Mode.CODE,
            "modify_code", Complexity.MEDIUM, "local",
            status=RunStatus.WAITING_FOR_USER,
            pending_decision=pending,
        )

        loaded = run_state_from_dict(state.to_dict())

        self.assertEqual(RunStatus.WAITING_FOR_USER, loaded.status)
        self.assertEqual(pending, loaded.pending_decision)

    def test_run_state_from_dict_preserves_legacy_defaults(self):
        payload = RunState(
            "run", "request", "INITIALIZING", Strategy.SDD, Mode.CODE,
            "modify_code", Complexity.MEDIUM, "local",
        ).to_dict()
        for legacy_field in ("selected_provider_command", "selected_model", "status", "schema_version", "harness_version"):
            payload.pop(legacy_field, None)

        loaded = run_state_from_dict(payload)

        self.assertEqual((), loaded.selected_provider_command)
        self.assertEqual("", loaded.selected_model)
        self.assertEqual(RunStatus.ACTIVE, loaded.status)
        self.assertEqual(1, loaded.schema_version)
        self.assertEqual("0.1.0", loaded.harness_version)

    def test_run_state_from_dict_rejects_malformed_contract_values(self):
        payload = RunState(
            "run", "request", "DESIGN", Strategy.SDD, Mode.CODE,
            "modify_code", Complexity.MEDIUM, "local",
        ).to_dict()
        payload["pending_decision"] = []

        with self.assertRaises(ValidationError):
            run_state_from_dict(payload)

        payload = RunState(
            "run", "request", "INITIALIZING", Strategy.SDD, Mode.CODE,
            "modify_code", Complexity.MEDIUM, "local",
        ).to_dict()
        payload["tasks"] = [{"id": "T1"}]

        with self.assertRaises(ValidationError):
            run_state_from_dict(payload)
