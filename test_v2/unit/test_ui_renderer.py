from __future__ import annotations

import unittest

from harness_v2.backend.application.contracts import PendingDecisionView, RunSummaryView, RunView, StepView
from harness_v2.frontends.ui.renderer import render, render_screen
from harness_v2.frontends.ui.state import Screen, UiEventView, UiState, push_screen


class UiRendererTests(unittest.TestCase):
    def test_render_shows_run_progress_actions_and_events(self) -> None:
        run = RunView(
            "run-1",
            "Fix tests",
            "RUNNING",
            "SDD_BUNDLE",
            current_step=StepView("SDD_BUNDLE:009", "PROPOSAL_BUNDLE", "PROPOSAL_DRAFT", 8),
            completed_steps=(
                StepView("SDD_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING", 0),
                StepView("SDD_BUNDLE:002", "EXPLORE_BUNDLE", "EXPLORE_CONTEXT_PACK", 1),
            ),
            completed_bundles=("EXPLORE_BUNDLE",),
        )
        state = UiState(
            runs=(RunSummaryView("run-1", "Fix tests", "RUNNING", StepView("SDD_BUNDLE:009", "PROPOSAL_BUNDLE", "PROPOSAL_DRAFT", 8)),),
            selected_run=run,
            selected_actions=("resume", "cancel"),
            event_cursor=3,
            events=(UiEventView(3, "StepStarted", "run-1", "step_id=SDD_BUNDLE:009 bundle=PROPOSAL_BUNDLE phase=PROPOSAL_DRAFT"),),
        )

        output = render(state)

        self.assertIn("AI Harness v2 UI", output)
        self.assertIn("* run-1 status=RUNNING phase=PROPOSAL_DRAFT request=Fix tests", output)
        self.assertIn("current step: SDD_BUNDLE:009 PROPOSAL_BUNDLE/PROPOSAL_DRAFT", output)
        self.assertIn("completed: EXPLORE_REQUEST_UNDERSTANDING -> EXPLORE_CONTEXT_PACK", output)
        self.assertIn("actions: resume, cancel", output)
        self.assertIn("3: StepStarted run=run-1 step_id=SDD_BUNDLE:009 bundle=PROPOSAL_BUNDLE phase=PROPOSAL_DRAFT", output)

    def test_render_shows_pending_decision(self) -> None:
        decision = PendingDecisionView("decision-1", "EXPLORE_BUNDLE", "Choose path", "2026-07-01T00:00:00+00:00", ("continue", "cancel"))
        state = UiState(
            selected_run=RunView(
                "run-1",
                "Fix tests",
                "WAITING_FOR_USER",
                "SDD_BUNDLE",
                current_step=StepView("SDD_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING", 0),
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

    def test_render_screen_marks_selected_item(self) -> None:
        state = push_screen(
            UiState(runs=(RunSummaryView("run-1", "a", "RUNNING"), RunSummaryView("run-2", "b", "PENDING"))),
            Screen("runs", selected=1),
        )

        output = render_screen(state)

        lines = output.splitlines()
        self.assertEqual("Runs", lines[0])
        self.assertTrue(lines[1].startswith("  1. run-1"))
        self.assertTrue(lines[2].startswith("> 2. run-2"))

    def test_render_includes_active_screen(self) -> None:
        state = push_screen(UiState(), Screen("start-bundle"))
        self.assertIn("> 1. SDD_BUNDLE", render(state))

    def test_home_screen_renders_dashboard_menu(self) -> None:
        output = render(UiState())

        self.assertIn("Dashboard", output)
        self.assertIn("> 1. Start run", output)
        self.assertIn("  2. Runs", output)

    def test_input_screen_shows_prompt(self) -> None:
        state = push_screen(UiState(), Screen("start-request", kind="input", context=("SDD_BUNDLE",)))
        self.assertIn("request> ", render_screen(state))


if __name__ == "__main__":
    unittest.main()
