"""Pure action planning for the command frontend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..bootstrap import GITHUB_CI_MODES

BUNDLE_ACTIONS = frozenset({"sdd", "explore", "proposal", "spec", "design", "tasks", "tdd"})
SOURCE_BUNDLES = frozenset({"proposal", "spec", "design", "tasks", "tdd"})
CONSOLE_ACTION_NAMES = frozenset({
    "archive",
    "artifacts",
    "attach",
    "cancel",
    "ci-mode",
    "design",
    "exit",
    "explore",
    "install-ci",
    "install-packages",
    "jobs",
    "model",
    "proposal",
    "resume",
    "runs",
    "sdd",
    "spec",
    "start",
    "status",
    "tasks",
    "tdd",
})

ActionPlanKind = Literal[
    "archive",
    "attach_job",
    "cancel_job",
    "error",
    "exit",
    "install_ci",
    "install_ci_prompt",
    "install_packages",
    "install_packages_prompt",
    "jobs",
    "list_artifacts",
    "model_prompt",
    "prompt_artifacts_run",
    "prompt_start_request",
    "resume",
    "runs",
    "select_ci_mode",
    "select_ci_mode_prompt",
    "start_job",
    "start_source_bundle",
    "status",
]


@dataclass(frozen=True, slots=True)
class ActionPlan:
    kind: ActionPlanKind
    code: int = 0
    message: str = ""
    values: tuple[str, ...] = ()
    request: str | None = None
    flow: str | None = None
    source_run: str | None = None
    target: str | None = None
    answer: str | None = None
    selected_option: str | None = None
    force: bool = False
    optionals: tuple[str, ...] = ()
    all_optional: bool = False
    dry_install: bool = False


def handled_action_names() -> set[str]:
    return set(CONSOLE_ACTION_NAMES)


def plan_start_request(request: str, *, recovery_blocked: bool) -> ActionPlan:
    if recovery_blocked:
        return ActionPlan("error", code=1, message="error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work")
    return ActionPlan("start_job", request=request)


def plan_action(
    command: str,
    args: tuple[str, ...],
    *,
    raw_tail: str = "",
    recovery_blocked: bool = False,
    interactive: bool = False,
    stdin_tty: bool = False,
) -> ActionPlan | None:
    if command not in CONSOLE_ACTION_NAMES:
        return None
    if command == "exit":
        return ActionPlan("exit")
    if command == "status":
        return ActionPlan("status")
    if command == "runs":
        return ActionPlan("runs")
    if command == "jobs":
        return ActionPlan("jobs")
    if command == "attach":
        return ActionPlan("attach_job", values=args[:1])
    if command == "cancel":
        return ActionPlan("cancel_job", values=args[:1])
    if command == "resume":
        try:
            run_id, answer, selected_option = parse_resume_action_args(list(args))
        except ValueError as exc:
            return ActionPlan("error", code=2, message=f"error: {exc}")
        return ActionPlan("resume", target=run_id, answer=answer, selected_option=selected_option)
    if command == "archive":
        return ActionPlan("archive", values=args[:1])
    if command == "start":
        return _plan_start(args, raw_tail=raw_tail, recovery_blocked=recovery_blocked)
    if command in BUNDLE_ACTIONS:
        return _plan_bundle(command, args, raw_tail=raw_tail, recovery_blocked=recovery_blocked)
    if command == "artifacts":
        return ActionPlan("list_artifacts", values=args[:1]) if args else ActionPlan("prompt_artifacts_run")
    if command == "ci-mode":
        return _plan_ci_mode(args)
    if command == "install-ci":
        return _plan_install_ci(args, interactive=interactive, stdin_tty=stdin_tty)
    if command == "install-packages":
        return _plan_install_packages(args, interactive=interactive, stdin_tty=stdin_tty)
    if command == "model":
        return ActionPlan("model_prompt")
    return None


def _plan_start(args: tuple[str, ...], *, raw_tail: str, recovery_blocked: bool) -> ActionPlan:
    if recovery_blocked:
        return ActionPlan("error", code=1, message="error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work")
    request = raw_tail.strip() if raw_tail else " ".join(args).strip()
    if not request:
        return ActionPlan("prompt_start_request")
    return ActionPlan("start_job", request=request)


def _plan_bundle(command: str, args: tuple[str, ...], *, raw_tail: str, recovery_blocked: bool) -> ActionPlan:
    if recovery_blocked:
        return ActionPlan("error", code=1, message="error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work")
    if command in {"sdd", "explore"}:
        request = (raw_tail.strip() if raw_tail else " ".join(args).strip()) if args else None
        return ActionPlan("start_job", values=args, request=request, flow=command)
    source_run = _source_run_arg(args)
    if source_run is not None:
        return ActionPlan("start_job", values=args, flow=command, source_run=source_run)
    return ActionPlan("start_source_bundle", values=args, flow=command)


def _source_run_arg(args: tuple[str, ...]) -> str | None:
    if not args:
        return None
    if args[0] == "--from-run" and len(args) > 1:
        return args[1]
    return args[0]


def _plan_ci_mode(args: tuple[str, ...]) -> ActionPlan:
    if len(args) > 1:
        return ActionPlan("error", code=2, message="error: ci-mode accepts at most one mode")
    if not args:
        return ActionPlan("select_ci_mode_prompt")
    selected = args[0].strip().lower()
    if selected not in GITHUB_CI_MODES:
        return ActionPlan("error", code=2, message="error: GitHub CI mode must be off, baseline, or branch")
    return ActionPlan("select_ci_mode", target=selected)


def _plan_install_ci(args: tuple[str, ...], *, interactive: bool, stdin_tty: bool) -> ActionPlan:
    force = "--force" in args
    targets = tuple(item for item in args if item != "--force")
    if len(targets) > 1:
        return ActionPlan("error", code=2, message="error: install-ci accepts at most one target")
    target = targets[0] if targets else None
    if target is None and interactive and stdin_tty:
        return ActionPlan("install_ci_prompt", force=force)
    return ActionPlan("install_ci", target=target, force=force)


def _plan_install_packages(args: tuple[str, ...], *, interactive: bool, stdin_tty: bool) -> ActionPlan:
    try:
        optionals, all_optional, dry_install = package_install_args(list(args))
    except ValueError as exc:
        return ActionPlan("error", code=2, message=f"error: {exc}")
    if not optionals and not all_optional and interactive and stdin_tty:
        return ActionPlan("install_packages_prompt", dry_install=dry_install)
    return ActionPlan("install_packages", optionals=tuple(optionals), all_optional=all_optional, dry_install=dry_install)


def parse_resume_action_args(args: list[str]) -> tuple[str | None, str | None, str | None]:
    run_id: str | None = None
    answer: str | None = None
    selected_option: str | None = None
    index = 0
    while index < len(args):
        value = args[index]
        if value == "--answer":
            index += 1
            if index >= len(args):
                raise ValueError("--answer requires a value")
            answer = args[index]
        elif value == "--selected-option":
            index += 1
            if index >= len(args):
                raise ValueError("--selected-option requires a value")
            selected_option = args[index]
        elif value.startswith("--"):
            raise ValueError(f"unknown resume option: {value}")
        elif run_id is None:
            run_id = value
        else:
            raise ValueError(f"unexpected resume argument: {value}")
        index += 1
    if answer is not None and selected_option is not None:
        raise ValueError("resume accepts only one of --answer or --selected-option")
    return run_id, answer, selected_option


def package_install_args(args: list[str]) -> tuple[list[str], bool, bool]:
    all_optional = False
    dry_install = False
    optionals: list[str] = []
    for arg in args:
        if arg in {"--all", "--all-optional"}:
            all_optional = True
        elif arg == "--dry-install":
            dry_install = True
        elif arg.startswith("--"):
            raise ValueError(f"unknown install-packages option: {arg}")
        else:
            optionals.append(arg)
    return optionals, all_optional, dry_install
