from __future__ import annotations

import unittest

from harness_v2.backend.application.contracts import ErrorView, PendingDecisionView, RunSummaryView, RunView, StepView
from harness_v2.frontends.ui import messages as m
from harness_v2.frontends.ui.screens import build_items, screen_title
from harness_v2.frontends.ui.state import HOME, Screen, UiState, current_screen
from harness_v2.frontends.ui.update import update


def _run_view(**overrides: object) -> RunView:
    fields: dict[str, object] = {
        "run_id": "run-1",
        "request": "Fix tests",
        "status": "RUNNING",
        "root_bundle": "SDD_BUNDLE",
    }
    fields.update(overrides)
    return RunView(**fields)  # type: ignore[arg-type]


class DashboardMenuTests(unittest.TestCase):
    def test_home_is_the_guided_dashboard_menu(self) -> None:
        state = UiState()

        self.assertEqual("menu", HOME.kind)
        self.assertEqual("Dashboard", screen_title(HOME, state))
        self.assertEqual(
            ["Start run", "Runs", "Refresh", "Watch events", "Quit"],
            [item.label for item in build_items(HOME, state)],
        )

    def test_home_adds_contextual_run_and_decision_actions(self) -> None:
        run = _run_view(
            status="WAITING_FOR_USER",
            pending_decision=PendingDecisionView(
                "decision-1", "SDD_BUNDLE", "Choose", "2026-07-01T00:00:00+00:00", ("keep", "drop")
            ),
        )
        state = UiState(selected_run=run, selected_actions=("submit-user-decision", "cancel"))

        items = build_items(HOME, state)

        self.assertIn("Selected run actions", [item.label for item in items])
        decision = next(item for item in items if item.label == "Answer decision")
        self.assertEqual(m.Navigate("decision-options"), decision.msg)

    def test_home_digit_navigation_starts_the_start_flow(self) -> None:
        state, effect = update(UiState(), m.Key("1"))

        self.assertIsInstance(effect, m.Nothing)
        self.assertEqual("start-bundle", current_screen(state).screen_id)

    def test_home_digit_navigation_can_quit(self) -> None:
        with self.assertRaises(SystemExit):
            update(UiState(), m.Key("5"))


class ContextualMenuTests(unittest.TestCase):
    def test_runs_screen_lists_runs_then_back(self) -> None:
        state = UiState(runs=(RunSummaryView("run-1", "Fix", "RUNNING"), RunSummaryView("run-2", "Other", "PENDING")))

        items = build_items(Screen("runs"), state)

        self.assertEqual(m.Invoke("select", ("run-1",)), items[0].msg)
        self.assertEqual(m.Invoke("select", ("run-2",)), items[1].msg)
        self.assertEqual(m.Back(), items[-1].msg)

    def test_actions_menu_reflects_backend_actions(self) -> None:
        state = UiState(selected_actions=("resume", "cancel", "retry-step", "submit-user-decision"))

        labels = [item.label for item in build_items(Screen("actions"), state)]

        self.assertEqual(["Resume run", "Cancel run", "Retry", "Answer decision", "Back"], labels)

    def test_retry_step_menu_uses_current_step(self) -> None:
        run = _run_view(current_step=StepView("SDD_BUNDLE:020", "TDD_BUNDLE", "TDD_EXECUTE", 19))
        state = UiState(selected_run=run)

        current_items = build_items(Screen("retry-step"), state)
        self.assertEqual(m.Invoke("retry-step", ("SDD_BUNDLE:020",)), current_items[0].msg)

    def test_decision_options_menu_offers_pending_options(self) -> None:
        run = _run_view(
            status="WAITING_FOR_USER",
            pending_decision=PendingDecisionView(
                "decision-1", "SDD_BUNDLE", "Choose", "2026-07-01T00:00:00+00:00", ("keep", "drop")
            ),
        )
        state = UiState(selected_run=run)

        items = build_items(Screen("decision-options"), state)

        self.assertEqual(m.Invoke("decision", ("keep",)), items[0].msg)
        self.assertEqual(m.Invoke("decision", ("drop",)), items[1].msg)


if __name__ == "__main__":
    unittest.main()
