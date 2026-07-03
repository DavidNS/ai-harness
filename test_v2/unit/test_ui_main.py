from __future__ import annotations

import unittest
from unittest import mock

from harness_v2.backend.application.contracts import PendingDecisionView, RunView, StepView
from harness_v2.frontends.ui import __main__ as ui_main
from harness_v2.frontends.ui import messages as m
from harness_v2.frontends.ui.dispatch import parse_command
from harness_v2.frontends.ui.state import HOME, Screen, UiState, current_screen


class FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def _record(self, name: str, args: tuple[object, ...], state: UiState) -> UiState:
        self.calls.append((name, args))
        return state

    def refresh(self, state: UiState) -> UiState:
        return self._record("refresh", (), state)

    def select(self, state: UiState, run_id: str) -> UiState:
        return self._record("select", (run_id,), state)

    def start(self, state: UiState, request: str, *, root_bundle: str) -> UiState:
        return self._record("start", (request, root_bundle), state)

    def resume(self, state: UiState) -> UiState:
        return self._record("resume", (), state)

    def cancel(self, state: UiState) -> UiState:
        return self._record("cancel", (), state)

    def retry(self, state: UiState, bundle: str, phase: str) -> UiState:
        return self._record("retry", (bundle, phase), state)

    def retry_bundle(self, state: UiState, bundle: str) -> UiState:
        return self._record("retry_bundle", (bundle,), state)

    def submit_decision(self, state: UiState, response: str) -> UiState:
        return self._record("submit_decision", (response,), state)

    def poll_events(self, state: UiState, *, timeout: float = 0.0) -> UiState:
        return self._record("poll_events", (timeout,), state)


class ParseCommandTests(unittest.TestCase):
    def test_bare_commands_navigate(self) -> None:
        self.assertEqual(m.Navigate("runs"), parse_command("/select"))
        self.assertEqual(m.Navigate("start-bundle"), parse_command("/start"))
        self.assertEqual(m.Navigate("retry-mode"), parse_command("/retry"))

    def test_commands_with_args_invoke_directly(self) -> None:
        self.assertEqual(m.Invoke("select", ("run-42",)), parse_command("/select run-42"))
        self.assertEqual(m.Invoke("start", ("SDD_BUNDLE", "fix the bug")), parse_command("/start SDD_BUNDLE fix the bug"))
        self.assertEqual(m.Invoke("retry-step", ("SDD_BUNDLE:020",)), parse_command("/retry SDD_BUNDLE:020"))

    def test_help_returns_none(self) -> None:
        self.assertIsNone(parse_command("/help"))


class HandleLineTests(unittest.TestCase):
    def test_slash_command_with_args_reaches_controller(self) -> None:
        controller = FakeController()
        ui_main._handle_line(controller, UiState(), "/select run-42")
        self.assertEqual([("select", ("run-42",))], controller.calls)

    def test_bare_command_navigates_without_backend_call(self) -> None:
        controller = FakeController()
        result = ui_main._handle_line(controller, UiState(), "/retry")
        self.assertEqual([], controller.calls)
        self.assertEqual("retry-mode", current_screen(result).screen_id)

    def test_non_slash_line_submits_decision_when_pending(self) -> None:
        controller = FakeController()
        state = UiState(
            selected_run=RunView(
                "run-1", "Fix", "WAITING_FOR_USER", "SDD_BUNDLE",
                pending_decision=PendingDecisionView("d1", "SDD_BUNDLE", "Why?", "2026-07-01T00:00:00+00:00"),
            )
        )
        ui_main._handle_line(controller, state, "continue")
        self.assertEqual([("submit_decision", ("continue",))], controller.calls)

    def test_non_slash_line_without_decision_shows_help(self) -> None:
        controller = FakeController()
        result = ui_main._handle_line(controller, UiState(), "random")
        self.assertEqual([], controller.calls)
        self.assertTrue(result.notice and result.notice.startswith("commands: "))

    def test_bad_command_shows_error(self) -> None:
        controller = FakeController()
        result = ui_main._handle_line(controller, UiState(), "/bogus")
        self.assertTrue(result.error and result.error.startswith("commands: "))


class MenuLineTests(unittest.TestCase):
    def test_digit_activates_item(self) -> None:
        controller = FakeController()
        state = UiState(nav=(HOME, Screen("start-bundle")))
        with mock.patch("builtins.input", return_value="1"):
            result = ui_main._menu_step_line(controller, state)
        self.assertEqual("start-request", current_screen(result).screen_id)

    def test_back_pops_screen(self) -> None:
        controller = FakeController()
        state = UiState(nav=(HOME, Screen("runs")))
        with mock.patch("builtins.input", return_value="b"):
            result = ui_main._menu_step_line(controller, state)
        self.assertEqual((HOME,), result.nav)


if __name__ == "__main__":
    unittest.main()
