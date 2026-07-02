from __future__ import annotations

import unittest

from harness_v2.backend.application.contracts import PendingDecisionView, RunSummaryView, RunView
from harness_v2.frontends.ui.renderer import render
from harness_v2.frontends.ui.state import UiEventView, UiState


class UiRendererTests(unittest.TestCase):
    def test_render_shows_run_progress_actions_and_events(self) -> None:
        run = RunView(
            "run-1",
            "Fix tests",
            "RUNNING",
            "SDD_BUNDLE",
            current_bundle="PROPOSAL_BUNDLE",
            current_phase="PROPOSAL_PURPOSE",
            completed_phases=("EXPLORE_REQUEST_UNDERSTANDING", "EXPLORE_CONTEXT_PACK"),
            completed_bundles=("EXPLORE_BUNDLE",),
        )
        state = UiState(
            runs=(RunSummaryView("run-1", "Fix tests", "RUNNING", "PROPOSAL_BUNDLE", "PROPOSAL_PURPOSE"),),
            selected_run=run,
            selected_actions=("resume", "cancel"),
            event_cursor=3,
            events=(UiEventView(3, "PhaseStarted", "run-1", "bundle=PROPOSAL_BUNDLE phase=PROPOSAL_PURPOSE"),),
        )

        output = render(state)

        self.assertIn("AI Harness v2 UI", output)
        self.assertIn("* run-1 status=RUNNING phase=PROPOSAL_PURPOSE request=Fix tests", output)
        self.assertIn("current phase: PROPOSAL_BUNDLE/PROPOSAL_PURPOSE", output)
        self.assertIn("completed: EXPLORE_REQUEST_UNDERSTANDING -> EXPLORE_CONTEXT_PACK", output)
        self.assertIn("actions: resume, cancel", output)
        self.assertIn("3: PhaseStarted run=run-1 bundle=PROPOSAL_BUNDLE phase=PROPOSAL_PURPOSE", output)

    def test_render_shows_pending_decision(self) -> None:
        decision = PendingDecisionView("decision-1", "EXPLORE_BUNDLE", "Choose path", "2026-07-01T00:00:00+00:00", ("continue", "cancel"))
        state = UiState(
            selected_run=RunView(
                "run-1",
                "Fix tests",
                "WAITING_FOR_USER",
                "SDD_BUNDLE",
                current_bundle="EXPLORE_BUNDLE",
                current_phase="EXPLORE_REQUEST_UNDERSTANDING",
                pending_decision=decision,
            ),
            selected_actions=("submit-user-decision", "cancel"),
        )

        output = render(state)

        self.assertIn("pending decision:", output)
        self.assertIn("id: decision-1", output)
        self.assertIn("bundle: EXPLORE_BUNDLE", output)
        self.assertIn("prompt: Choose path", output)
        self.assertIn("options: continue, cancel", output)


if __name__ == "__main__":
    unittest.main()
