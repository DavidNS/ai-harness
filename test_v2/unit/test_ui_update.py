from __future__ import annotations

import unittest

from harness_v2.backend.application.contracts import ErrorView, RunSummaryView, RunView
from harness_v2.frontends.ui import messages as m
from harness_v2.frontends.ui.state import HOME, Screen, UiState, current_screen, push_screen
from harness_v2.frontends.ui.update import update


def _at(screen: Screen, **overrides: object) -> UiState:
    return UiState(nav=(HOME, screen), **overrides)  # type: ignore[arg-type]


class KeyNavigationTests(unittest.TestCase):
    def test_down_and_up_wrap_selection(self) -> None:
        state = _at(Screen("start-bundle"))
        n = len(__import__("harness_v2.frontends.ui.screens", fromlist=["build_items"]).build_items(current_screen(state), state))

        down, effect = update(state, m.Key("down"))
        self.assertIsInstance(effect, m.Nothing)
        self.assertEqual(1, current_screen(down).selected)

        up, _ = update(state, m.Key("up"))
        self.assertEqual(n - 1, current_screen(up).selected)

    def test_enter_activates_selected_choice(self) -> None:
        state = _at(Screen("start-bundle"))  # first item -> Navigate start-request(SDD)
        new, effect = update(state, m.Key("\r"))
        self.assertIsInstance(effect, m.Nothing)
        self.assertEqual("start-request", current_screen(new).screen_id)
        self.assertEqual(("SDD_BUNDLE",), current_screen(new).context)

    def test_digit_activates_item(self) -> None:
        state = UiState(runs=(RunSummaryView("run-1", "a", "RUNNING"),), nav=(HOME, Screen("runs")))
        new, effect = update(state, m.Key("1"))
        self.assertEqual(m.Select("run-1"), effect)

    def test_escape_pops_screen(self) -> None:
        state = _at(Screen("runs"))
        new, effect = update(state, m.Key("escape"))
        self.assertEqual((HOME,), new.nav)


class DrilldownTests(unittest.TestCase):
    def test_full_retry_bundle_flow(self) -> None:
        run = RunView("run-1", "Fix", "FAILED", "SDD_BUNDLE", completed_bundles=("EXPLORE_BUNDLE",))
        state = UiState(selected_run=run, selected_actions=("retry-step", "retry-bundle"), nav=(HOME, Screen("actions")))

        # Actions -> Retry
        state, effect = update(state, m.Navigate("retry-mode"))
        self.assertEqual("retry-mode", current_screen(state).screen_id)

        # Retry -> "Retry a whole bundle" (second item)
        state, _ = update(state, m.Key("down"))
        state, effect = update(state, m.Key("\r"))
        self.assertEqual("retry-bundle", current_screen(state).screen_id)

        # pick EXPLORE_BUNDLE
        state, effect = update(state, m.Key("1"))
        self.assertEqual(m.RetryBundle("EXPLORE_BUNDLE"), effect)
        self.assertEqual((HOME,), state.nav)  # terminal command returns home

    def test_start_flow_bundle_then_text(self) -> None:
        state = _at(Screen("start-bundle"))
        state, _ = update(state, m.Key("\r"))  # pick SDD_BUNDLE -> start-request
        self.assertEqual("start-request", current_screen(state).screen_id)

        state, effect = update(state, m.SubmitLine("Fix the bug"))
        self.assertEqual(m.Start("SDD_BUNDLE", "Fix the bug"), effect)
        self.assertEqual((HOME,), state.nav)

    def test_empty_submit_cancels(self) -> None:
        state = _at(Screen("start-request", kind="input", context=("SDD_BUNDLE",)))
        new, effect = update(state, m.SubmitLine("   "))
        self.assertIsInstance(effect, m.Nothing)
        self.assertEqual((HOME,), new.nav)
        self.assertEqual("cancelled", new.notice)


class MessageMappingTests(unittest.TestCase):
    def test_select_pushes_actions_and_emits_select(self) -> None:
        state = UiState(nav=(HOME, Screen("runs")))
        new, effect = update(state, m.Invoke("select", ("run-9",)))
        self.assertEqual(m.Select("run-9"), effect)
        self.assertEqual("actions", current_screen(new).screen_id)

    def test_terminal_command_collapses_to_home(self) -> None:
        state = _at(Screen("actions"), selected_actions=("resume", "cancel"))
        new, effect = update(state, m.Invoke("resume"))
        self.assertEqual(m.Resume(), effect)
        self.assertEqual((HOME,), new.nav)

    def test_refresh_stays_in_place(self) -> None:
        state = _at(Screen("runs"))
        new, effect = update(state, m.Invoke("refresh"))
        self.assertEqual(m.Refresh(), effect)
        self.assertEqual(state.nav, new.nav)

    def test_quit_raises_system_exit(self) -> None:
        with self.assertRaises(SystemExit):
            update(UiState(), m.Quit())


if __name__ == "__main__":
    unittest.main()
