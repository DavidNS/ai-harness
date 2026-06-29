import unittest
from ai_harness.errors import TransitionError
from ai_harness.models import Strategy
from ai_harness.pipeline.state_machine import GRAPHS, allowed_transitions, validate_transition


class StateMachineTests(unittest.TestCase):
    def test_every_declared_edge_and_failure_edge_is_legal(self):
        for strategy, phases in GRAPHS.items():
            for current, target in zip(phases, phases[1:]):
                validate_transition(strategy, current, target)
            for phase in phases[:-1]:
                validate_transition(strategy, phase, "FAILED")

    def test_explorer_graph_contains_only_analysis_phases(self):
        graph = GRAPHS[Strategy.EXPLORER]
        self.assertIn("EXPLORER_INTAKE", graph)
        self.assertIn("EXPLORER_DISCOVERY", graph)
        self.assertIn("EXPLORER_DECISION", graph)
        self.assertIn("EXPLORER_ARTIFACT", graph)
        self.assertIn("EXPLORER_REVIEW", graph)
        self.assertNotIn("EXPLORER", graph)
        self.assertNotIn("TDD_LOOP", graph)
        self.assertNotIn("LEARNING", graph)

    def test_skipping_a_phase_fails_closed(self):
        with self.assertRaises(TransitionError):
            validate_transition(Strategy.SDD, "INITIALIZING", "ROUTING")
