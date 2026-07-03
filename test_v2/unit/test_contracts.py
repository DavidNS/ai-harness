from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
import json
import unittest

from harness_v2.backend.application.contracts import (
    BundleRetryStarted,
    BundleStarted,
    CancelRun,
    CommandResult,
    ErrorView,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetRun,
    GetRunResult,
    GetRunState,
    GetRunStateResult,
    InstallCiTemplates,
    InstallCiTemplatesResult,
    ListRuns,
    ListRunsResult,
    PendingDecisionView,
    StepCompleted,
    StepFailed,
    StepStarted,
    ResumeRun,
    RetryBundle,
    RetryStep,
    RunCancelled,
    RunCompleted,
    RunStarted,
    RunSummaryView,
    RunView,
    StepView,
    StartRun,
    SubmitUserDecision,
    TaskSummaryView,
    UserDecisionRequested,
)
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord


class ContractTests(unittest.TestCase):
    def test_commands_queries_events_and_results_use_step_identity(self) -> None:
        commands = (
            StartRun("Fix tests"),
            StartRun("Explore", root_bundle="EXPLORE_BUNDLE"),
            ResumeRun("run-1"),
            RetryBundle("run-1", "EXPLORE_BUNDLE"),
            RetryStep("run-1", "EXPLORE_BUNDLE:002"),
            CancelRun("run-1"),
            InstallCiTemplates("github", force=True),
            SubmitUserDecision("run-1", "decision-1", "continue"),
        )
        queries = (GetRun("run-1"), ListRuns(), GetRunState("run-1"), GetAvailableActions("run-1"))
        events = (
            RunStarted("run-1", "Fix tests", "SDD_BUNDLE"),
            BundleStarted("run-1", "EXPLORE_BUNDLE"),
            StepStarted("run-1", "EXPLORE_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING"),
            StepCompleted("run-1", "EXPLORE_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING"),
            StepFailed("run-1", "EXPLORE_BUNDLE:002", "EXPLORE_BUNDLE", "EXPLORE_CONTEXT_PACK", "failed"),
            BundleRetryStarted("run-1", "EXPLORE_BUNDLE"),
            UserDecisionRequested("run-1", "decision-1", "EXPLORE_BUNDLE", "Choose", ("continue",)),
            RunCompleted("run-1"),
            RunCancelled("run-1"),
        )

        self.assertEqual("SDD_BUNDLE", commands[0].root_bundle)
        self.assertTrue(all(item is not None for item in (*commands, *queries, *events)))

    def test_result_dtos_can_be_created_and_serialized(self) -> None:
        decision = PendingDecisionView("decision-1", "EXPLORE_BUNDLE", "Choose", "2026-07-01T00:00:00+00:00", ("continue",))
        task = TaskSummaryView("task-1", "Implement", "IN_PROGRESS", attempts=1, last_failure="failed once")
        step = StepView("SDD_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING", 0)
        error = ErrorView("E001", "failed", "SDD_BUNDLE:001", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING", "2026-07-01T00:00:00+00:00")
        run = RunView(
            run_id="run-1",
            request="Fix tests",
            status="WAITING_FOR_USER",
            root_bundle="SDD_BUNDLE",
            current_step=step,
            completed_steps=(),
            completed_bundles=(),
            pending_decision=decision,
            tasks=(task,),
            errors=(error,),
        )
        results = (
            CommandResult(run=run, events=(RunStarted("run-1", "Fix tests", "SDD_BUNDLE"),)),
            GetRunResult(run=run),
            ListRunsResult(runs=(RunSummaryView("run-1", "Fix tests", "WAITING_FOR_USER", step),)),
            GetRunStateResult("run-1", "WAITING_FOR_USER", step, decision),
            GetAvailableActionsResult("run-1", ("submit-user-decision", "cancel")),
            InstallCiTemplatesResult("github", installed=(".github/workflows/ai-harness-ci.yml",)),
        )

        encoded = json.dumps(asdict(results[0]), sort_keys=True)
        self.assertIn('"current_step"', encoded)
        self.assertIn('"step_id": "SDD_BUNDLE:001"', encoded)
        self.assertTrue(all(result is not None for result in results))

    def test_result_dtos_reject_raw_domain_objects_and_bad_nested_values(self) -> None:
        domain_run = RunRecord(
            run_id="run-1",
            request="Fix tests",
            status=RunStatus.COMPLETED,
            root_bundle=BundleName.EXPLORE_BUNDLE,
            completed_phases=_explore_phases(),
        )
        invalid_cases = (
            lambda: CommandResult(run=domain_run, events=()),
            lambda: GetRunResult(run=domain_run),
            lambda: ListRunsResult(runs=(domain_run,)),
            lambda: RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE", tasks=(object(),)),
            lambda: RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE", errors=(object(),)),
            lambda: CommandResult(run=RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE"), events=(object(),)),
        )
        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(TypeError):
                    create()

    def test_text_and_enum_fields_are_validated(self) -> None:
        self.assertEqual("Fix tests", StartRun("  Fix tests  ").request)
        self.assertEqual("EXPLORE_BUNDLE", StepStarted("run-1", "SDD_BUNDLE:002", "  EXPLORE_BUNDLE  ", "EXPLORE_CONTEXT_PACK").bundle)
        self.assertEqual("COMPLETED", RunView("run-1", "Fix", "  COMPLETED  ", "EXPLORE_BUNDLE").status)

        invalid_cases = (
            lambda: StartRun(" "),
            lambda: StartRun("Fix", root_bundle="SDD"),
            lambda: RetryStep("run-1", " "),
            lambda: RetryStep("", "SDD_BUNDLE:001"),
            lambda: RetryBundle("run-1", "NOT_A_BUNDLE"),
            lambda: StepStarted("run-1", "SDD_BUNDLE:001", "EXPLORE_BUNDLE", "NOT_A_PHASE"),
            lambda: UserDecisionRequested("run-1", "decision-1", "NOT_A_BUNDLE", "Choose"),
            lambda: RunView("run-1", "Fix", "COMPLETED", "SDD"),
        )
        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(ValueError):
                    create()

    def test_dtos_are_frozen(self) -> None:
        command = StartRun("Fix tests")
        with self.assertRaises(FrozenInstanceError):
            command.request = "changed"  # type: ignore[misc]


def _explore_phases() -> tuple[PhaseName, ...]:
    return (
        PhaseName.EXPLORE_REQUEST_UNDERSTANDING,
        PhaseName.EXPLORE_CONTEXT_PACK,
        PhaseName.EXPLORE_EVIDENCE_DIGEST,
        PhaseName.EXPLORE_EXPLORATION_MAP,
        PhaseName.EXPLORE_OUTCOME_SYNTHESIS,
        PhaseName.EXPLORE_HANDOFF,
    )


if __name__ == "__main__":
    unittest.main()
