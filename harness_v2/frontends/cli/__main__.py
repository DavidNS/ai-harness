"""Command-line frontend for the v2 in-process host contract."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from harness_v2.backend.application.contracts import (
    CancelRun,
    CommandResult,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetKnowledgePatch,
    GetKnowledgePatchResult,
    GetRun,
    GetRunResult,
    GetRunState,
    GetRunStateResult,
    InstallCiTemplates,
    KnowledgePatchView,
    ListKnowledgePatches,
    ListKnowledgePatchesResult,
    InstallCiTemplatesResult,
    InvalidRunStateError,
    ListRuns,
    ListRunsResult,
    RejectKnowledgePatch,
    RejectKnowledgePatchResult,
    ResumeRun,
    RetryStep,
    RunNotFoundError,
    RunView,
    StartRun,
    SubmitUserDecision,
)
from harness_v2.hosts.daemon.client import DaemonClient
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
    parser.add_argument(
        "--branch",
        choices=("off", "current", "create", "create-from-main"),
        default="current",
        help="git branch behavior for release context, default: current",
    )
    parser.add_argument(
        "--github-ci-mode",
        choices=("off", "baseline", "branch"),
        default="baseline",
        help="CI evidence mode for release context, default: baseline",
    )
    parser.add_argument(
        "--model-provider",
        choices=("codex", "claude"),
        default="codex",
        help="model provider for in-process workers, default: codex",
    )
    parser.add_argument(
        "--host-mode",
        choices=("in-process", "daemon"),
        default="in-process",
        help="backend host mode, default: in-process",
    )
    parser.add_argument(
        "--daemon-url",
        default="http://127.0.0.1:8765",
        help="daemon base URL when --host-mode daemon is used",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    start = subcommands.add_parser("start", help="start a simulated v2 run")
    start.add_argument("--root-bundle", default="SDD_BUNDLE", help="root bundle, default: SDD_BUNDLE")
    start.add_argument("request", nargs="+", help="request text")

    resume = subcommands.add_parser("resume", help="resume an existing run")
    resume.add_argument("run_id")

    cancel = subcommands.add_parser("cancel", help="cancel an active run")
    cancel.add_argument("run_id")

    retry = subcommands.add_parser("retry", help="retry the failed step")
    retry.add_argument("run_id")
    retry.add_argument("step_id")

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

    reject_patch = subcommands.add_parser("reject-knowledge-patch", help="reject a candidate knowledge patch")
    reject_patch.add_argument("patch_id")
    reject_patch.add_argument("reason")

    get_patch = subcommands.add_parser("get-knowledge-patch", help="show a candidate knowledge patch")
    get_patch.add_argument("patch_id")

    list_patches = subcommands.add_parser("list-knowledge-patches", help="list candidate knowledge patches")
    list_patches.add_argument("--run-id", default=None)
    list_patches.add_argument("--status", choices=("CANDIDATE", "REJECTED"), default=None)

    install = subcommands.add_parser("install-ci", help="install managed CI templates")
    install.add_argument("target", nargs="?", default="github", choices=("github", "gitlab", "both"))
    install.add_argument("--force", action="store_true", help="replace an existing unmanaged CI file")

    subcommands.add_parser("list", help="list runs")
    return parser


def _render_run(run: RunView) -> None:
    print(f"Run: {run.run_id}")
    print(f"Status: {run.status}")
    print(f"Request: {run.request}")
    print(f"Root bundle: {run.root_bundle}")
    if run.current_step is not None:
        step = run.current_step
        print(f"Current step: {step.step_id} {step.bundle}/{step.phase}")
    if run.completed_steps:
        print("Completed steps: " + ", ".join(step.step_id for step in run.completed_steps))
    if run.pending_decision is not None:
        decision = run.pending_decision
        options = f" options={','.join(decision.options)}" if decision.options else ""
        print(f"Pending decision: {decision.decision_id} bundle={decision.origin_bundle}{options}")
        print(f"Prompt: {decision.prompt}")


def _render_events(result: CommandResult) -> None:
    for event in result.events:
        step_id = getattr(event, "step_id", None)
        phase = getattr(event, "phase", None)
        bundle = getattr(event, "bundle", None)
        if step_id and phase and bundle:
            suffix = f" step={step_id} bundle={bundle} phase={phase}"
        elif phase and bundle:
            suffix = f" bundle={bundle} phase={phase}"
        elif phase:
            suffix = f" phase={phase}"
        elif type(event).__name__ == "EscalationRaised":
            suffix = f" issue={event.issue_id} bundle={event.origin_bundle} category={event.category}"
        elif type(event).__name__ == "EscalationResolved":
            target = f" target={event.target_bundle}" if event.target_bundle else ""
            suffix = f" issue={event.issue_id} action={event.action}{target}"
        elif type(event).__name__ == "BundleRetryStarted":
            suffix = f" bundle={event.bundle}"
        elif type(event).__name__ == "KnowledgePatchCreated":
            suffix = f" patch={event.patch_id} origin={event.origin_bundle} path={event.path}"
        elif type(event).__name__ == "KnowledgePatchRejected":
            suffix = f" patch={event.patch_id}"
        elif type(event).__name__ == "TestsStarted":
            suffix = f" task={event.task_id} group={event.group} attempt={event.attempt}"
        elif type(event).__name__ == "TestsFinished":
            suffix = f" task={event.task_id} group={event.group} attempt={event.attempt} failed={event.failed}/{event.total}"
        else:
            suffix = ""
        print(f"Event: {type(event).__name__}{suffix}")


def _render_command_result(result: CommandResult) -> None:
    _render_run(result.run)
    _render_events(result)


def _render_install_result(result: InstallCiTemplatesResult) -> None:
    print(f"CI target: {result.target}")
    print(f"Installed: {', '.join(result.installed) if result.installed else 'none'}")
    print(f"Skipped: {', '.join(result.skipped) if result.skipped else 'none'}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    for event in result.events:
        print(f"Event: {type(event).__name__}")


def _render_get(result: GetRunResult) -> None:
    _render_run(result.run)


def _render_list(result: ListRunsResult) -> None:
    print(f"Runs: {len(result.runs)}")
    for run in result.runs:
        phase = f" step={run.current_step.step_id} bundle={run.current_step.bundle} phase={run.current_step.phase}" if run.current_step else ""
        print(f"Run: {run.run_id} status={run.status}{phase} request={run.request}")


def _render_state(result: GetRunStateResult) -> None:
    print(f"Run: {result.run_id}")
    print(f"Status: {result.status}")
    if result.current_step is not None:
        step = result.current_step
        print(f"Current step: {step.step_id} {step.bundle}/{step.phase}")
    if result.pending_decision is not None:
        decision = result.pending_decision
        options = f" options={','.join(decision.options)}" if decision.options else ""
        print(f"Pending decision: {decision.decision_id} bundle={decision.origin_bundle}{options}")
        print(f"Prompt: {decision.prompt}")


def _render_actions(result: GetAvailableActionsResult) -> None:
    print(f"Run: {result.run_id}")
    print(f"Actions: {', '.join(result.actions) if result.actions else 'none'}")


def _render_patch(patch: KnowledgePatchView) -> None:
    print(f"Patch: {patch.patch_id}")
    print(f"Status: {patch.status}")
    print(f"Run: {patch.run_id}")
    print(f"Origin bundle: {patch.origin_bundle}")
    print(f"Path: {patch.path}")
    print(f"Proposal: {patch.proposal_id}")
    print(f"Summary: {patch.summary}")
    if patch.rejection_reason is not None:
        print(f"Rejection reason: {patch.rejection_reason}")


def _render_get_patch(result: GetKnowledgePatchResult) -> None:
    _render_patch(result.patch)


def _render_list_patches(result: ListKnowledgePatchesResult) -> None:
    print(f"Knowledge patches: {len(result.patches)}")
    for patch in result.patches:
        print(f"Patch: {patch.patch_id} status={patch.status} run={patch.run_id} origin={patch.origin_bundle}")


def _render_reject_patch(result: RejectKnowledgePatchResult) -> None:
    _render_patch(result.patch)
    for event in result.events:
        print(f"Event: {type(event).__name__} patch={event.patch_id}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.host_mode == "daemon":
        host = DaemonClient(args.daemon_url)
    else:
        host = InProcessHost(
            state_root=args.state_root,
            working_directory=args.working_directory,
            allow_repository_mutation=args.allow_repository_mutation,
            branch_mode=args.branch,
            github_ci_mode=args.github_ci_mode,
            model_provider_name=args.model_provider,
        )
    try:
        if args.command == "install-ci":
            _render_install_result(host.execute(InstallCiTemplates(target=args.target, force=args.force)))
            return 0
        if args.command == "reject-knowledge-patch":
            _render_reject_patch(host.execute(RejectKnowledgePatch(args.patch_id, args.reason)))
            return 0
        if args.command == "get-knowledge-patch":
            _render_get_patch(host.query(GetKnowledgePatch(args.patch_id)))
            return 0
        if args.command == "list-knowledge-patches":
            _render_list_patches(host.query(ListKnowledgePatches(run_id=args.run_id, status=args.status)))
            return 0
        if args.command == "start":
            _render_command_result(host.execute(StartRun(request=" ".join(args.request), root_bundle=args.root_bundle)))
            return 0
        if args.command == "resume":
            _render_command_result(host.execute(ResumeRun(run_id=args.run_id)))
            return 0
        if args.command == "cancel":
            _render_command_result(host.execute(CancelRun(run_id=args.run_id)))
            return 0
        if args.command == "retry":
            _render_command_result(host.execute(RetryStep(run_id=args.run_id, step_id=args.step_id)))
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
