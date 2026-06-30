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

    def test_explorer_graph_is_single_explore_bundle(self):
        self.assertEqual(("EXPLORE_BUNDLE",), tuple(str(item) for item in GRAPHS[Strategy.EXPLORER]))

    def test_full_sdd_graph_contains_only_bundle_phases(self):
        self.assertEqual((
            "EXPLORE_BUNDLE",
            "PROPOSAL_BUNDLE",
            "SPEC_BUNDLE",
            "DESIGN_BUNDLE",
            "TASKS_BUNDLE",
            "TDD_BUNDLE",
        ), tuple(str(item) for item in GRAPHS[Strategy.SDD]))

    def test_skipping_a_phase_fails_closed(self):
        with self.assertRaises(TransitionError):
            validate_transition(Strategy.SDD, "EXPLORE_BUNDLE", "SPEC_BUNDLE")
