"""Command-line frontend for the v2 in-process host contract."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

from harness_v2.backend.application.contracts import (
    CancelRun,
    CommandResult,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetRun,
    InvalidRunStateError,
    GetRunResult,
    GetRunState,
    GetRunStateResult,
    ListRuns,
    ListRunsResult,
    ResumeRun,
    RetryPhase,
    RunNotFoundError,
    RunView,
    StartRun,
    SubmitUserDecision,
)
from harness_v2.hosts.in_process.host import InProcessHost

DEFAULT_STATE_ROOT = Path(".ai-harness") / "v2"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AI Harness v2 backend contract")
    parser.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_STATE_ROOT,
        help="v2 runtime state root, default: .ai-harness/v2",
    )
    parser.add_argument(
        "--working-directory",
        type=Path,
        default=None,
        help="working directory for repository-mutating phases, default: current directory",
    )
    parser.add_argument(
        "--allow-repository-mutation",
        action="store_true",
        help="allow TDD workers and validation commands to mutate the configured working directory",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    start = subcommands.add_parser("start", help="start a simulated v2 run")
    start.add_argument("--strategy", default="SDD", help="run strategy, default: SDD")
    start.add_argument("request", nargs="+", help="request text")

    resume = subcommands.add_parser("resume", help="resume an existing run")
    resume.add_argument("run_id")

    cancel = subcommands.add_parser("cancel", help="cancel an active run")
    cancel.add_argument("run_id")

    retry = subcommands.add_parser("retry", help="retry the last failed phase")
    retry.add_argument("run_id")
    retry.add_argument("phase")

    decision = subcommands.add_parser("decision", help="submit a pending user decision")
    decision.add_argument("run_id")
    decision.add_argument("decision_id")
    decision.add_argument("response")

    get = subcommands.add_parser("get", help="show run details")
    get.add_argument("run_id")

    state = subcommands.add_parser("state", help="show run state")
    state.add_argument("run_id")

    actions = subcommands.add_parser("actions", help="show available run actions")
    actions.add_argument("run_id")

    subcommands.add_parser("list", help="list runs")
    return parser


def _render_run(run: RunView) -> None:
    print(f"Run: {run.run_id}")
    print(f"Status: {run.status}")
    print(f"Request: {run.request}")
    print(f"Strategy: {run.strategy}")
    if run.current_phase is not None:
        print(f"Current phase: {run.current_phase}")
    if run.completed_phases:
        print(f"Completed phases: {', '.join(run.completed_phases)}")
    if run.pending_decision is not None:
        decision = run.pending_decision
        options = f" options={','.join(decision.options)}" if decision.options else ""
        print(f"Pending decision: {decision.decision_id} phase={decision.origin_phase}{options}")
        print(f"Prompt: {decision.prompt}")


def _render_events(result: CommandResult) -> None:
    for event in result.events:
        phase = getattr(event, "phase", None)
        if phase:
            suffix = f" phase={phase}"
        elif type(event).__name__ == "EscalationRaised":
            suffix = f" issue={event.issue_id} phase={event.origin_phase} category={event.category}"
        elif type(event).__name__ == "EscalationResolved":
            target = f" target={event.target_phase}" if event.target_phase else ""
            suffix = f" issue={event.issue_id} action={event.action}{target}"
        elif type(event).__name__ == "PhaseRetryStarted":
            suffix = f" phase={event.phase}"
        else:
            suffix = ""
        print(f"Event: {type(event).__name__}{suffix}")


def _render_command_result(result: CommandResult) -> None:
    _render_run(result.run)
    _render_events(result)


def _render_get(result: GetRunResult) -> None:
    _render_run(result.run)


def _render_list(result: ListRunsResult) -> None:
    print(f"Runs: {len(result.runs)}")
    for run in result.runs:
        phase = f" phase={run.current_phase}" if run.current_phase else ""
        print(f"Run: {run.run_id} status={run.status}{phase} request={run.request}")


def _render_state(result: GetRunStateResult) -> None:
    print(f"Run: {result.run_id}")
    print(f"Status: {result.status}")
    if result.current_phase is not None:
        print(f"Current phase: {result.current_phase}")
    if result.pending_decision is not None:
        decision = result.pending_decision
        options = f" options={','.join(decision.options)}" if decision.options else ""
        print(f"Pending decision: {decision.decision_id} phase={decision.origin_phase}{options}")
        print(f"Prompt: {decision.prompt}")


def _render_actions(result: GetAvailableActionsResult) -> None:
    print(f"Run: {result.run_id}")
    print(f"Actions: {', '.join(result.actions) if result.actions else 'none'}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    host = InProcessHost(
        state_root=args.state_root,
        working_directory=args.working_directory,
        allow_repository_mutation=args.allow_repository_mutation,
    )
    try:
        if args.command == "start":
            _render_command_result(host.execute(StartRun(request=" ".join(args.request), strategy=args.strategy)))
            return 0
        if args.command == "resume":
            _render_command_result(host.execute(ResumeRun(run_id=args.run_id)))
            return 0
        if args.command == "cancel":
            _render_command_result(host.execute(CancelRun(run_id=args.run_id)))
            return 0
        if args.command == "retry":
            _render_command_result(host.execute(RetryPhase(run_id=args.run_id, phase=args.phase)))
            return 0
        if args.command == "decision":
            _render_command_result(
                host.execute(
                    SubmitUserDecision(
                        run_id=args.run_id,
                        decision_id=args.decision_id,
                        response=args.response,
                    )
                )
            )
            return 0
        if args.command == "get":
            _render_get(host.query(GetRun(run_id=args.run_id)))
            return 0
        if args.command == "list":
            _render_list(host.query(ListRuns()))
            return 0
        if args.command == "state":
            _render_state(host.query(GetRunState(run_id=args.run_id)))
            return 0
        if args.command == "actions":
            _render_actions(host.query(GetAvailableActions(run_id=args.run_id)))
            return 0
    except (InvalidRunStateError, RunNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
