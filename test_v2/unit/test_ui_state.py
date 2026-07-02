from __future__ import annotations

import unittest

from harness_v2.backend.application.contracts import PhaseStarted, RunSummaryView, RunView, UserDecisionRequested
from harness_v2.frontends.ui.state import UiState, append_events, event_view, replace_run_list, select_run


class UiStateTests(unittest.TestCase):
    def test_replace_run_list_preserves_existing_selected_run(self) -> None:
        selected = RunView("run-1", "Fix tests", "RUNNING", "SDD_BUNDLE", current_bundle="EXPLORE_BUNDLE", current_phase="EXPLORE_REQUEST_UNDERSTANDING")
        state = select_run(UiState(), selected, ("resume", "cancel"))

        updated = replace_run_list(state, (RunSummaryView("run-1", "Fix tests", "RUNNING", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING"),))

        self.assertEqual("run-1", updated.selected_run.run_id if updated.selected_run else None)
        self.assertEqual(("resume", "cancel"), updated.selected_actions)

    def test_replace_run_list_clears_missing_selected_run(self) -> None:
        selected = RunView("run-1", "Fix tests", "RUNNING", "SDD_BUNDLE", current_bundle="EXPLORE_BUNDLE", current_phase="EXPLORE_REQUEST_UNDERSTANDING")
        state = select_run(UiState(), selected, ("resume",))

        updated = replace_run_list(state, (RunSummaryView("run-2", "Other", "PENDING"),))

        self.assertIsNone(updated.selected_run)
        self.assertEqual((), updated.selected_actions)

    def test_append_events_advances_cursor_and_keeps_summary(self) -> None:
        started = event_view(PhaseStarted("run-1", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING"), 1)
        decision = event_view(UserDecisionRequested("run-1", "decision-1", "EXPLORE_BUNDLE", "Choose", ("continue",)), 2)

        updated = append_events(UiState(), (started, decision))

        self.assertEqual(2, updated.event_cursor)
        self.assertEqual(["PhaseStarted", "UserDecisionRequested"], [event.event_type for event in updated.events])
        self.assertIn("bundle=EXPLORE_BUNDLE", updated.events[0].summary)
        self.assertIn("phase=EXPLORE_REQUEST_UNDERSTANDING", updated.events[0].summary)
        self.assertIn("options=continue", updated.events[1].summary)


if __name__ == "__main__":
    unittest.main()
