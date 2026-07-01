from __future__ import annotations

import unittest

from harness_v2.backend.domain.errors import DomainValidationError, InvalidTransitionError
from harness_v2.backend.domain.lifecycle import EXPLORER_PHASES, LifecycleGraph, PhaseName, RunStrategy, SDD_PHASES, TerminalState


class LifecycleGraphTests(unittest.TestCase):
    def test_sdd_graph_allows_ordered_bundle_transitions(self) -> None:
        graph = LifecycleGraph.for_strategy(RunStrategy.SDD)

        self.assertEqual(PhaseName.EXPLORE_BUNDLE, graph.start_phase)
        self.assertEqual(PhaseName.PROPOSAL_BUNDLE, graph.next_after(PhaseName.EXPLORE_BUNDLE))
        self.assertEqual(PhaseName.SPEC_BUNDLE, graph.next_after(PhaseName.PROPOSAL_BUNDLE))
        self.assertEqual(PhaseName.DESIGN_BUNDLE, graph.next_after(PhaseName.SPEC_BUNDLE))
        self.assertEqual(PhaseName.TASKS_BUNDLE, graph.next_after(PhaseName.DESIGN_BUNDLE))
        self.assertEqual(PhaseName.TDD_BUNDLE, graph.next_after(PhaseName.TASKS_BUNDLE))
        self.assertEqual(TerminalState.COMPLETED, graph.next_after(PhaseName.TDD_BUNDLE))


    def test_explorer_graph_allows_ordered_stage_transitions(self) -> None:
        graph = LifecycleGraph.for_strategy(RunStrategy.EXPLORER)

        self.assertEqual(PhaseName.EXPLORER_INTAKE, graph.start_phase)
        self.assertEqual(PhaseName.EXPLORER_DISCOVERY, graph.next_after(PhaseName.EXPLORER_INTAKE))
        self.assertEqual(PhaseName.EXPLORER_DECISION, graph.next_after(PhaseName.EXPLORER_DISCOVERY))
        self.assertEqual(PhaseName.EXPLORER_ARTIFACT, graph.next_after(PhaseName.EXPLORER_DECISION))
        self.assertEqual(PhaseName.EXPLORER_REVIEW, graph.next_after(PhaseName.EXPLORER_ARTIFACT))
        self.assertEqual(PhaseName.EXPLORER_DISTILL, graph.next_after(PhaseName.EXPLORER_REVIEW))
        self.assertEqual(TerminalState.COMPLETED, graph.next_after(PhaseName.EXPLORER_DISTILL))
        graph.validate_completed_prefix(EXPLORER_PHASES[:3])

    def test_bundle_strategies_complete_after_their_single_bundle(self) -> None:
        cases = (
            (RunStrategy.EXPLORE_BUNDLE, PhaseName.EXPLORE_BUNDLE),
            (RunStrategy.PROPOSAL_BUNDLE, PhaseName.PROPOSAL_BUNDLE),
            (RunStrategy.SPEC_BUNDLE, PhaseName.SPEC_BUNDLE),
            (RunStrategy.DESIGN_BUNDLE, PhaseName.DESIGN_BUNDLE),
            (RunStrategy.TASKS_BUNDLE, PhaseName.TASKS_BUNDLE),
            (RunStrategy.TDD_BUNDLE, PhaseName.TDD_BUNDLE),
        )
        for strategy, phase in cases:
            with self.subTest(strategy=strategy):
                graph = LifecycleGraph.for_strategy(strategy)
                self.assertEqual(phase, graph.start_phase)
                self.assertEqual(TerminalState.COMPLETED, graph.next_after(phase))

    def test_invalid_transitions_fail_closed(self) -> None:
        graph = LifecycleGraph.for_strategy(RunStrategy.SDD)

        for source, target in (
            (PhaseName.EXPLORE_BUNDLE, PhaseName.SPEC_BUNDLE),
            (PhaseName.DESIGN_BUNDLE, PhaseName.SPEC_BUNDLE),
            (PhaseName.PROPOSAL_BUNDLE, TerminalState.COMPLETED),
        ):
            with self.subTest(source=source, target=target):
                with self.assertRaises(InvalidTransitionError):
                    graph.validate_transition(source, target)

        single = LifecycleGraph.for_strategy(RunStrategy.EXPLORE_BUNDLE)
        for terminal in TerminalState:
            with self.subTest(terminal=terminal):
                with self.assertRaises(InvalidTransitionError):
                    single.validate_transition(PhaseName.PROPOSAL_BUNDLE, terminal)

    def test_terminal_transitions_and_unknown_nodes_are_rejected(self) -> None:
        graph = LifecycleGraph.for_strategy(RunStrategy.SDD)

        graph.validate_transition(PhaseName.DESIGN_BUNDLE, TerminalState.FAILED)
        graph.validate_transition(PhaseName.DESIGN_BUNDLE, TerminalState.CANCELLED)
        with self.assertRaises(InvalidTransitionError):
            graph.validate_transition(TerminalState.COMPLETED, PhaseName.EXPLORE_BUNDLE)
        with self.assertRaises(DomainValidationError):
            graph.validate_transition("UNKNOWN", PhaseName.EXPLORE_BUNDLE)
        with self.assertRaises(DomainValidationError):
            graph.validate_transition(PhaseName.EXPLORE_BUNDLE, "UNKNOWN")
        self.assertFalse(graph.can_transition("UNKNOWN", PhaseName.EXPLORE_BUNDLE))

    def test_completed_prefix_must_be_unique_and_ordered(self) -> None:
        graph = LifecycleGraph.for_strategy(RunStrategy.SDD)

        graph.validate_completed_prefix(SDD_PHASES[:2])
        with self.assertRaises(DomainValidationError):
            graph.validate_completed_prefix((PhaseName.PROPOSAL_BUNDLE,))
        with self.assertRaises(DomainValidationError):
            graph.validate_completed_prefix((PhaseName.EXPLORE_BUNDLE, PhaseName.EXPLORE_BUNDLE))


if __name__ == "__main__":
    unittest.main()
