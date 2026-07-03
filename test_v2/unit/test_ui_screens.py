from __future__ import annotations

import unittest

from harness_v2.backend.application.contracts import (
    ErrorView,
    PendingDecisionView,
    RunSummaryView,
    RunView,
    StepView,
)
from harness_v2.frontends.ui import messages as m
from harness_v2.frontends.ui.screens import ROOT_BUNDLES, build_items, screen_title
from harness_v2.frontends.ui.state import Screen, UiState


def _run(**overrides: object) -> RunView:
    fields: dict[str, object] = {
        "run_id": "run-1",
        "request": "Fix tests",
        "status": "FAILED",
        "root_bundle": "SDD_BUNDLE",
    }
    fields.update(overrides)
    return RunView(**fields)  # type: ignore[arg-type]


class ScreenBuildersTests(unittest.TestCase):
    def test_runs_screen_lists_runs_then_back(self) -> None:
        state = UiState(runs=(RunSummaryView("run-1", "Fix", "RUNNING"), RunSummaryView("run-2", "Other", "PENDING")))

        items = build_items(Screen("runs"), state)

        self.assertEqual(m.Invoke("select", ("run-1",)), items[0].msg)
        self.assertEqual(m.Invoke("select", ("run-2",)), items[1].msg)
        self.assertEqual(m.Back(), items[-1].msg)

    def test_actions_screen_reflects_available_actions(self) -> None:
        state = UiState(selected_actions=("resume", "cancel"))
        labels = [item.label for item in build_items(Screen("actions"), state)]
        self.assertEqual(["Resume run", "Cancel run", "Back"], labels)

        failed = UiState(selected_actions=("retry-step", "retry-bundle"))
        retry = build_items(Screen("actions"), failed)
        self.assertEqual(m.Navigate("retry-mode"), retry[0].msg)

    def test_actions_screen_routes_decision_to_options_or_input(self) -> None:
        with_options = UiState(
            selected_actions=("submit-user-decision", "cancel"),
            selected_run=_run(
                status="WAITING_FOR_USER",
                pending_decision=PendingDecisionView("d1", "SDD_BUNDLE", "Choose", "2026-07-01T00:00:00+00:00", ("keep", "drop")),
            ),
        )
        decision_item = next(i for i in build_items(Screen("actions"), with_options) if i.label == "Answer decision")
        self.assertEqual(m.Navigate("decision-options"), decision_item.msg)

        free_text = UiState(
            selected_actions=("submit-user-decision", "cancel"),
            selected_run=_run(
                status="WAITING_FOR_USER",
                pending_decision=PendingDecisionView("d1", "SDD_BUNDLE", "Why?", "2026-07-01T00:00:00+00:00"),
            ),
        )
        free_item = next(i for i in build_items(Screen("actions"), free_text) if i.label == "Answer decision")
        self.assertEqual(m.Navigate("decision-input"), free_item.msg)

    def test_retry_bundle_screen_derives_bundles_from_runview(self) -> None:
        run = _run(
            completed_bundles=("EXPLORE_BUNDLE",),
            current_step=StepView("SDD_BUNDLE:020", "TDD_BUNDLE", "TDD_EXECUTE", 19),
            errors=(ErrorView("boom", "x", bundle="PROPOSAL_BUNDLE", phase="PROPOSAL_DRAFT"),),
        )
        items = build_items(Screen("retry-bundle"), UiState(selected_run=run))
        labels = [item.label for item in items[:-1]]
        self.assertEqual(["EXPLORE_BUNDLE", "TDD_BUNDLE", "PROPOSAL_BUNDLE"], labels)
        self.assertEqual(m.Invoke("retry-bundle", ("EXPLORE_BUNDLE",)), items[0].msg)

    def test_retry_step_screen_uses_current_step_id(self) -> None:
        run = _run(current_step=StepView("SDD_BUNDLE:020", "TDD_BUNDLE", "TDD_EXECUTE", 19))
        state = UiState(selected_run=run)

        items = build_items(Screen("retry-step"), state)

        self.assertEqual("SDD_BUNDLE:020 TDD_BUNDLE/TDD_EXECUTE", items[0].label)
        self.assertEqual(m.Invoke("retry-step", ("SDD_BUNDLE:020",)), items[0].msg)

    def test_start_bundle_screen_offers_root_bundles(self) -> None:
        items = build_items(Screen("start-bundle"), UiState())
        self.assertEqual("SDD_BUNDLE", items[0].label)
        self.assertEqual(m.Navigate("start-request", ("SDD_BUNDLE",)), items[0].msg)
        self.assertEqual(len(ROOT_BUNDLES) + 1, len(items))  # + Back

    def test_decision_options_screen_from_pending_decision(self) -> None:
        run = _run(
            status="WAITING_FOR_USER",
            pending_decision=PendingDecisionView("d1", "SDD_BUNDLE", "Choose", "2026-07-01T00:00:00+00:00", ("keep", "drop")),
        )
        items = build_items(Screen("decision-options"), UiState(selected_run=run))
        self.assertEqual(m.Invoke("decision", ("keep",)), items[0].msg)
        self.assertEqual(m.Invoke("decision", ("drop",)), items[1].msg)

    def test_titles(self) -> None:
        self.assertEqual("Runs", screen_title(Screen("runs"), UiState()))
        self.assertEqual("Choose the step", screen_title(Screen("retry-step"), UiState()))
        self.assertEqual("request> ", screen_title(Screen("start-request", kind="input"), UiState()))


if __name__ == "__main__":
    unittest.main()
