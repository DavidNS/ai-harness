from __future__ import annotations

import unittest

from harness_v2.backend.application.contracts import RunSummaryView, RunView, StepStarted, StepView, UserDecisionRequested
from harness_v2.frontends.ui.state import (
    HOME,
    Screen,
    UiState,
    append_events,
    current_screen,
    event_view,
    home_screen,
    move_selection,
    pop_screen,
    push_screen,
    replace_run_list,
    select_run,
    with_error,
)


class UiStateTests(unittest.TestCase):
    def test_replace_run_list_preserves_existing_selected_run(self) -> None:
        selected = RunView("run-1", "Fix tests", "RUNNING", "SDD_BUNDLE", current_step=StepView("SDD_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING", 0))
        state = select_run(UiState(), selected, ("resume", "cancel"))

        updated = replace_run_list(state, (RunSummaryView("run-1", "Fix tests", "RUNNING", StepView("SDD_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING", 0)),))

        self.assertEqual("run-1", updated.selected_run.run_id if updated.selected_run else None)
        self.assertEqual(("resume", "cancel"), updated.selected_actions)

    def test_replace_run_list_clears_missing_selected_run(self) -> None:
        selected = RunView("run-1", "Fix tests", "RUNNING", "SDD_BUNDLE", current_step=StepView("SDD_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING", 0))
        state = select_run(UiState(), selected, ("resume",))

        updated = replace_run_list(state, (RunSummaryView("run-2", "Other", "PENDING"),))

        self.assertIsNone(updated.selected_run)
        self.assertEqual((), updated.selected_actions)

    def test_append_events_advances_cursor_and_keeps_summary(self) -> None:
        started = event_view(StepStarted("run-1", "SDD_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING"), 1)
        decision = event_view(UserDecisionRequested("run-1", "decision-1", "EXPLORE_BUNDLE", "Choose", ("continue",)), 2)

        updated = append_events(UiState(), (started, decision))

        self.assertEqual(2, updated.event_cursor)
        self.assertEqual(["StepStarted", "UserDecisionRequested"], [event.event_type for event in updated.events])
        self.assertIn("bundle=EXPLORE_BUNDLE", updated.events[0].summary)
        self.assertIn("options=continue", updated.events[1].summary)


class NavTransitionsTests(unittest.TestCase):
    def test_default_state_starts_at_home(self) -> None:
        self.assertEqual((HOME,), UiState().nav)
        self.assertEqual("home", current_screen(UiState()).screen_id)

    def test_push_and_pop_screen(self) -> None:
        state = push_screen(UiState(), Screen("runs"))
        state = push_screen(state, Screen("actions"))
        self.assertEqual(["home", "runs", "actions"], [s.screen_id for s in state.nav])
        self.assertEqual(["home", "runs"], [s.screen_id for s in pop_screen(state).nav])

    def test_pop_never_removes_home(self) -> None:
        self.assertEqual((HOME,), pop_screen(UiState()).nav)

    def test_move_selection_updates_top_only(self) -> None:
        state = push_screen(push_screen(UiState(), Screen("runs")), Screen("actions"))
        updated = move_selection(state, 3)
        self.assertEqual(0, updated.nav[1].selected)
        self.assertEqual(3, updated.nav[2].selected)

    def test_home_screen_truncates_to_root(self) -> None:
        state = push_screen(push_screen(UiState(), Screen("runs")), Screen("actions"))
        self.assertEqual((HOME,), home_screen(state).nav)

    def test_existing_transitions_preserve_nav(self) -> None:
        state = push_screen(UiState(), Screen("runs", selected=2))
        self.assertEqual(state.nav, with_error(state, "boom").nav)


if __name__ == "__main__":
    unittest.main()
