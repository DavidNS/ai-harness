"""Console loop and command dispatch for the AI Harness launcher."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ai_harness.ci_support import ci_preflight
from .backend_client import BackendClient, ResumeBackendRequest, StartBackendRequest
from .bootstrap import ACTIONS, RUNNER, _default_provider, _parser, _prompt_for_model, _prompt_for_reasoning_effort
from .console_session import ConsoleSession
from .console_actions import (
    CONSOLE_ACTIONS,
    parse_console_line,
    suggest_console_actions,
)
from .job_runner import BackgroundJobRunner
from .console_controller import (
    ConsoleController,
    ConsoleControllerDependencies,
    console_suggestion_label as _controller_console_suggestion_label,
    interactive_console_line as _controller_interactive_console_line,
    package_group_items as _controller_package_group_items,
    package_install_args as _controller_package_install_args,
    render_console_prompt as _controller_render_console_prompt,
)
from .runtime import (
    _completed_runs,
    _decision_request,
    _find_run,
    _print_unfinished_runs,
    _run,
    _run_line,
    _run_title,
    _unfinished_runs,
)
from .ui import (
    _discover_improvement_candidates,
    _interactive_request,
    _ordered_options,
    _prepare_console_request,
    _prompt_for_decision,
    _validate_explorer_scope,
)
from .ui_primitives import (
    _handle_slash_command,
    _interactive_stdin,
    _LauncherExit,
    _line_prompt,
    _menu_prompt,
    _multi_select_prompt,
    _MenuItem,
    _RawTerminal,
    _read_key,
    _text_prompt,
)

_CONSOLE_ACTIONS = CONSOLE_ACTIONS
def _backend_client(namespace: argparse.Namespace) -> BackendClient:
    def run_backend(args: list[str]) -> int:
        return _run(args, verbose=namespace.verbose, dry_run=namespace.dry_run)

    return BackendClient(namespace.cwd.resolve(), run_backend)


def _controller_dependencies() -> ConsoleControllerDependencies:
    return ConsoleControllerDependencies(
        start=_start,
        start_job=_start_job,
        resume=_resume,
        archive=_archive,
        refresh_recovery_block=_refresh_recovery_block,
        prompt_for_model=_prompt_for_model,
        prompt_for_reasoning_effort=_prompt_for_reasoning_effort,
        menu_prompt=_menu_prompt,
        multi_select_prompt=_multi_select_prompt,
        line_prompt=_line_prompt,
        interactive_request=_interactive_request,
        interactive_stdin=_interactive_stdin,
        raw_terminal=_RawTerminal,
        read_key=_read_key,
        launcher_exit=_LauncherExit,
    )


def _job_runner(namespace: argparse.Namespace) -> BackgroundJobRunner:
    runner = getattr(namespace, "_job_runner", None)
    if not isinstance(runner, BackgroundJobRunner):
        runner = BackgroundJobRunner(namespace.cwd.resolve())
        setattr(namespace, "_job_runner", runner)
    return runner


def _console_session(namespace: argparse.Namespace) -> ConsoleSession:
    session = ConsoleSession.from_namespace(namespace)
    session.sync_namespace(namespace)
    return session


def _controller(namespace: argparse.Namespace) -> ConsoleController:
    _console_session(namespace)
    return ConsoleController(namespace, _backend_client(namespace), _controller_dependencies(), _job_runner(namespace))


def _waiting_run_ids(repository) -> set[str]:
    return {
        str(state.get("run_id"))
        for _, state in _unfinished_runs(repository)
        if state.get("status") == "waiting_for_user" and isinstance(state.get("run_id"), str)
    }


def _run_and_follow_decisions(namespace: argparse.Namespace, args: list[str], *, request: str | None = None) -> int:
    previous_waiting = _waiting_run_ids(namespace.cwd.resolve()) if sys.stdin.isatty() else set()
    code = _run(args, request=request, verbose=namespace.verbose, dry_run=namespace.dry_run)
    if namespace.dry_run or not sys.stdin.isatty():
        return code
    return _follow_waiting_decisions(namespace, code, previous_waiting_ids=previous_waiting)


def _follow_waiting_decisions(namespace: argparse.Namespace, code: int, *, run_id: str | None = None, previous_waiting_ids: set[str] | None = None) -> int:
    repository = namespace.cwd.resolve()
    while True:
        waiting = [(current, state) for current, state in _unfinished_runs(repository) if state.get("status") == "waiting_for_user"]
        if run_id is not None:
            waiting = [(current, state) for current, state in waiting if state.get("run_id") == run_id]
        elif previous_waiting_ids:
            waiting = [(current, state) for current, state in waiting if state.get("run_id") not in previous_waiting_ids]
        if not waiting:
            return code
        if len(waiting) > 1:
            _print_unfinished_runs(repository, waiting, heading="Multiple waiting runs need explicit selection")
            print("Use `resume <RUN_ID>` to answer one waiting run.", file=sys.stderr)
            return code
        current, state = waiting[0]
        run_id = str(state.get("run_id"))
        if _decision_request(current, state) is None:
            print(f"Run {run_id} is waiting, but its decision request could not be read.", file=sys.stderr)
            return code
        code = _resume(namespace, run_id, follow_decisions=False)


def _has_unfinished_runs(namespace: argparse.Namespace) -> bool:
    return bool(_unfinished_runs(namespace.cwd.resolve()))


def _refresh_recovery_block(namespace: argparse.Namespace) -> None:
    setattr(namespace, "_recovery_blocked", _has_unfinished_runs(namespace))


def _select_run(title: str, runs: list[tuple[object, dict[str, object]]]) -> tuple[object, dict[str, object]] | None:
    if not runs:
        print(f"No {title.casefold()} found.", file=sys.stderr)
        return None
    items = []
    for index, (root, state) in enumerate(runs, 1):
        label = _run_line(None, state, root).removeprefix("- ")
        run_id = str(state.get("run_id") or getattr(root, "name", ""))
        items.append(_MenuItem(str(index), label, str(index - 1), (run_id,)))
    items.append(_MenuItem("b", "Back", "__back__", ("back",)))
    selected = _menu_prompt([title], items, help_kind="action").value
    if selected == "__back__":
        return None
    try:
        return runs[int(selected)]
    except (ValueError, IndexError):
        return None


def _next_flow_for_completed_run(root: object) -> str | None:
    path = Path(root)
    handoffs = (
        ("published/tdd-handoff.json", None),
        ("published/tasks-handoff.json", "tdd"),
        ("published/design-handoff.json", "tasks"),
        ("published/spec-handoff.json", "design"),
        ("published/proposal-handoff.json", "spec"),
        ("published/explore-handoff.json", "proposal"),
    )
    for artifact, flow in handoffs:
        if (path / artifact).is_file():
            return flow
    return None


def _continue_unfinished_run(namespace: argparse.Namespace) -> int | None:
    selected = _select_run("Unfinished runs", _unfinished_runs(namespace.cwd.resolve()))
    if selected is None:
        return None
    _, state = selected
    run_id = str(state.get("run_id"))
    return _resume(namespace, run_id)


def _continue_completed_run(namespace: argparse.Namespace) -> int | None:
    _refresh_recovery_block(namespace)
    if getattr(namespace, "_recovery_blocked", False):
        _print_unfinished_runs(namespace.cwd.resolve(), heading="Unfinished runs must be resolved before continuing a completed run")
        print("Resume or archive unfinished runs before starting the next bundle from a completed run.", file=sys.stderr)
        return None
    selected = _select_run("Completed runs", _completed_runs(namespace.cwd.resolve()))
    if selected is None:
        return None
    root, state = selected
    flow = _next_flow_for_completed_run(root)
    if flow is None:
        print("Selected run has no next bundle to continue.", file=sys.stderr)
        print(f"Artifacts: {root}", file=sys.stderr)
        return None
    source_run = Path(root).name
    title = _run_title(Path(root), state)
    request = f"Continue {flow} from {source_run}: {title}"
    return _start(namespace, [], request_override=request, flow=flow, source_run=source_run)


def _continue_run_menu(namespace: argparse.Namespace) -> int | None:
    while True:
        selected = _menu_prompt(
            ["Continue run"],
            [
                _MenuItem("u", "Unfinished runs", "unfinished", ("unfinished", "open")),
                _MenuItem("c", "Completed runs", "completed", ("completed", "done")),
                _MenuItem("b", "Back", "back", ("back",)),
            ],
            help_kind="action",
            default_index=0,
        ).value
        if selected == "back":
            return None
        if selected == "unfinished":
            result = _continue_unfinished_run(namespace)
        else:
            result = _continue_completed_run(namespace)
        _refresh_recovery_block(namespace)
        if result is not None:
            return result


def _startup_recovery(namespace: argparse.Namespace) -> int | None:
    repository = namespace.cwd.resolve()
    _refresh_recovery_block(namespace)
    while True:
        selected = _menu_prompt(
            ["AI Harness runs"],
            [
                _MenuItem("c", "Continue run", "continue", ("continue", "resume")),
                _MenuItem("n", "New run", "new", ("new", "start")),
                _MenuItem("o", "Open console", "console", ("console", "shell")),
                _MenuItem("s", "Show runs", "show", ("show", "runs")),
                _MenuItem("x", "Exit launcher", "exit", ("exit", "quit")),
            ],
            help_kind="action",
            default_index=0 if getattr(namespace, "_recovery_blocked", False) else 1,
        ).value
        if selected == "exit":
            raise _LauncherExit
        if selected == "show":
            _backend_client(namespace).runs()
            continue
        if selected == "console":
            return None
        if selected == "continue":
            result = _continue_run_menu(namespace)
            if result is not None:
                return result
            _refresh_recovery_block(namespace)
            continue
        if selected == "new":
            _refresh_recovery_block(namespace)
            if getattr(namespace, "_recovery_blocked", False):
                _print_unfinished_runs(repository, heading="Unfinished runs must be resolved before a new run")
                print("Resume or archive unfinished runs before starting unrelated work.", file=sys.stderr)
                continue
            return _dispatch_console_action(namespace, "start", [], "start")


def _package_group_items() -> list[_MenuItem]:
    return _controller_package_group_items()


def _package_install_args(args: list[str]) -> tuple[list[str], bool, bool]:
    return _controller_package_install_args(args)


def _select_github_ci_mode(namespace: argparse.Namespace, args: list[str]) -> int:
    return _controller(namespace).select_github_ci_mode(args)


def _startup_ci_preflight(namespace: argparse.Namespace) -> None:
    if getattr(namespace, "skip_warnings", False) or not sys.stdin.isatty():
        return
    repository = namespace.cwd.resolve()
    preflight = ci_preflight(repository, environment=dict(os.environ))
    if not preflight.ci_ok:
        lines = ["CI setup check"]
        lines.extend(preflight.ci_warnings or ("AI Harness CI is not installed for this repository.",))
        selected = _menu_prompt(
            lines,
            [
                _MenuItem("i", "Install AI Harness CI", "install", ("install",)),
                _MenuItem("c", "Continue without installing", "continue", ("continue",)),
                _MenuItem("x", "Exit launcher", "exit", ("exit", "quit")),
            ],
            help_kind="action",
        ).value
        if selected == "exit":
            raise _LauncherExit
        if selected == "install":
            code = _dispatch_console_action(namespace, "install-ci", [], "install-ci")
            if code != 0:
                raise _LauncherExit
            if namespace.dry_run:
                return
            preflight = ci_preflight(repository, environment=dict(os.environ))
            if not preflight.ci_ok:
                print("CI setup still needs attention; continuing without CI artifact checks.", file=sys.stderr)
                return
        else:
            return
    if preflight.signal_ok:
        return
    lines = [
        "CI artifact check",
        f"AI Harness CI signals are {preflight.signal_status}.",
        "Continue if the pipeline has not published AI Harness artifacts yet.",
    ]
    if preflight.signal_reason:
        lines.append(preflight.signal_reason)
    lines.extend(preflight.signal_warnings)
    selected = _menu_prompt(
        lines,
        [
            _MenuItem("c", "Continue without CI artifacts", "continue", ("continue",)),
            _MenuItem("x", "Exit launcher", "exit", ("exit", "quit")),
        ],
        help_kind="action",
        default_index=0,
    ).value
    if selected == "exit":
        raise _LauncherExit


def _console_help() -> None:
    namespace = argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=True)
    _controller(namespace).console_help()


def _console_action_menu(namespace: argparse.Namespace) -> int:
    return _controller(namespace).console_action_menu()


def _console_suggestion_label(action) -> str:
    return _controller_console_suggestion_label(action)


def _render_console_prompt(buffer: list[str], slash_mode: bool, selected: int, previous_lines: int) -> int:
    return _controller_render_console_prompt(buffer, slash_mode, selected, previous_lines)


def _interactive_console_line() -> str | None:
    return _controller_interactive_console_line(_controller_dependencies())


def _source_run_for_bundle(namespace: argparse.Namespace, bundle: str, args: list[str]) -> str | None:
    return _controller(namespace).source_run_for_bundle(bundle, args)


def _dispatch_console_action(namespace: argparse.Namespace, command: str, args: list[str], raw_line: str) -> int:
    return _controller(namespace).dispatch_console_action(command, args, raw_line)


def _interactive_start_request(namespace: argparse.Namespace) -> str:
    return _controller(namespace).interactive_start_request()


def _console_command(namespace: argparse.Namespace, line: str) -> int:
    return _controller(namespace).console_command(line)


def _console_loop(namespace: argparse.Namespace) -> int:
    return _controller(namespace).console_loop(_startup_recovery)


def _branch_args(namespace: argparse.Namespace) -> list[str]:
    selected = getattr(namespace, "branch", None)
    if selected in {"current", "create-from-main"}:
        return ["--branch", selected]
    if not sys.stdin.isatty():
        return ["--branch", "current"]
    selected = _menu_prompt(
        ["Git branch"],
        [
            _MenuItem("c", "Use current branch", "current", ("current",)),
            _MenuItem("n", "Create run branch from main", "create-from-main", ("create", "new")),
        ],
        help_kind="console",
        default_index=0,
    ).value
    setattr(namespace, "branch", selected)
    return ["--branch", selected]


def _select_route_for_start() -> str:
    return _menu_prompt(
        ["Request route"],
        [
            _MenuItem("c", "Code harness", "code", ("code",)),
            _MenuItem("n", "Non-code", "non-code", ("non_code", "non-code")),
        ],
        help_kind="console",
        default_index=0,
    ).value


def _select_code_flow() -> str:
    return _menu_prompt(
        ["Code flow"],
        [
            _MenuItem("f", "Full SDD", "sdd", ("sdd", "full")),
            _MenuItem("e", "EXPLORE_BUNDLE", "explore", ("explore", "explore_bundle")),
            _MenuItem("o", "PROPOSAL_BUNDLE", "proposal", ("proposal", "proposal_bundle")),
            _MenuItem("s", "SPEC_BUNDLE", "spec", ("spec", "spec_bundle")),
            _MenuItem("d", "DESIGN_BUNDLE", "design", ("design", "design_bundle")),
            _MenuItem("t", "TASKS_BUNDLE", "tasks", ("tasks", "tasks_bundle")),
            _MenuItem("r", "TDD_BUNDLE", "tdd", ("tdd", "tdd_bundle")),
        ],
        help_kind="console",
        default_index=0,
    ).value


def _prepare_start_backend(
    namespace: argparse.Namespace,
    prompt_args: list[str],
    *,
    request_override: str | None = None,
    route: str | None = None,
    flow: str | None = None,
    source_run: str | None = None,
    allow_console_loop: bool = True,
) -> tuple[int | None, list[str] | None, str | None]:
    provider = _default_provider(namespace.provider)
    request: str | None = request_override
    if namespace.prompt_file is not None:
        if prompt_args or request_override is not None:
            print("error: --file cannot be combined with an inline request", file=sys.stderr)
            return 2, None, None
    elif request is None:
        request = " ".join(prompt_args).strip()
        if not request and not sys.stdin.isatty():
            request = sys.stdin.read().strip()
    if namespace.prompt_file is None and not request:
        if source_run and flow:
            request = f"Run {flow} bundle from {source_run}"
        elif sys.stdin.isatty() and allow_console_loop:
            return _console_loop(namespace), None, None
        else:
            print("error: a request is required", file=sys.stderr)
            return 2, None, None
    if sys.stdin.isatty():
        _startup_ci_preflight(namespace)
    branch_args = _branch_args(namespace)
    branch = branch_args[1] if len(branch_args) == 2 and branch_args[0] == "--branch" else None
    if namespace.prompt_file is None and request and sys.stdin.isatty():
        request = _prepare_console_request(namespace, request)
    if route is None and flow is not None:
        route = "code"
    if route is None and sys.stdin.isatty():
        route = _select_route_for_start()
    if route in {"code", None} and flow is None and sys.stdin.isatty():
        flow = _select_code_flow()
    if source_run is None and flow in {"proposal", "spec", "design", "tasks", "tdd"}:
        source_run = _source_run_for_bundle(namespace, flow, [])
    backend = _backend_client(namespace).start_args(
        StartBackendRequest(
            provider=provider,
            model=getattr(namespace, "model", None),
            reasoning_effort=getattr(namespace, "reasoning_effort", None),
            github_ci_mode=getattr(namespace, "github_ci_mode", None),
            branch=branch,
            route=route,
            flow=flow,
            source_run=source_run,
            prompt_file=namespace.prompt_file,
        )
    )
    return None, backend, request


def _start(
    namespace: argparse.Namespace,
    prompt_args: list[str],
    *,
    request_override: str | None = None,
    route: str | None = None,
    flow: str | None = None,
    source_run: str | None = None,
) -> int:
    code, backend, request = _prepare_start_backend(
        namespace, prompt_args, request_override=request_override, route=route, flow=flow, source_run=source_run
    )
    if code is not None or backend is None:
        return int(code or 0)
    return _run_and_follow_decisions(namespace, backend, request=request)


def _start_job(
    namespace: argparse.Namespace,
    prompt_args: list[str],
    *,
    request_override: str | None = None,
    route: str | None = None,
    flow: str | None = None,
    source_run: str | None = None,
) -> int:
    code, backend, request = _prepare_start_backend(
        namespace,
        prompt_args,
        request_override=request_override,
        route=route,
        flow=flow,
        source_run=source_run,
        allow_console_loop=False,
    )
    if code is not None or backend is None:
        return int(code or 0)
    if namespace.dry_run:
        return _run_and_follow_decisions(namespace, backend, request=request)
    handle = _job_runner(namespace).submit(backend, request=request)
    print(f"Started background job {handle.job_id}. Use /attach {handle.job_id} or /jobs.", file=sys.stderr)
    return 0


def _resume(namespace: argparse.Namespace, run_id: str | None, *, follow_decisions: bool = True) -> int:
    repository = namespace.cwd.resolve()
    selected_run = _find_run(repository, run_id)
    if selected_run is None:
        if run_id:
            print(f"error: no unfinished run found for {run_id}", file=sys.stderr)
        else:
            print("error: no unfinished run found", file=sys.stderr)
        return 1
    current, state = selected_run
    actual_run_id = str(state["run_id"])
    model = getattr(namespace, "model", None)
    if model is None and isinstance(state, dict):
        model = state.get("selected_model") or None
    answer: str | None = None
    selected: str | None = None
    if state.get("status") == "waiting_for_user" and sys.stdin.isatty():
        request = _decision_request(current, state)
        if request is not None:
            answer, selected = _prompt_for_decision(actual_run_id, request)
    backend = _backend_client(namespace).resume_args(
        ResumeBackendRequest(
            provider=_default_provider(namespace.provider),
            run_id=actual_run_id,
            model=model,
            reasoning_effort=getattr(namespace, "reasoning_effort", None),
            github_ci_mode=getattr(namespace, "github_ci_mode", None),
            answer=answer,
            selected_option=selected,
        )
    )
    code = _run(backend, verbose=namespace.verbose, dry_run=namespace.dry_run)
    if follow_decisions:
        _refresh_recovery_block(namespace)
    if follow_decisions and not namespace.dry_run and sys.stdin.isatty():
        return _follow_waiting_decisions(namespace, code, run_id=actual_run_id)
    return code


def _archive(namespace: argparse.Namespace, run_id: str | None) -> int:
    if not run_id:
        selected = _find_run(namespace.cwd.resolve(), None)
        if selected is None:
            print("error: no unfinished run found", file=sys.stderr)
            return 1
        run_id = str(selected[1]["run_id"])
    code = _backend_client(namespace).archive(run_id)
    _refresh_recovery_block(namespace)
    return code


def main(argv: list[str] | None = None) -> int:
    if not RUNNER.is_file():
        print(f"error: runner not found: {RUNNER}", file=sys.stderr)
        return 1
    parser = _parser()
    namespace, rest = parser.parse_known_args(argv)
    if rest and rest[0] in ACTIONS:
        action, args = rest[0], rest[1:]
    else:
        action, args = "start", rest
    try:
        if action == "status":
            return _backend_client(namespace).status()
        if action == "runs":
            return _backend_client(namespace).runs()
        if action == "resume":
            return _resume(namespace, args[0] if args else None)
        if action == "archive":
            return _archive(namespace, args[0] if args else None)
        if action == "install-ci":
            return _dispatch_console_action(namespace, "install-ci", args, "install-ci " + " ".join(args))
        if action == "install-packages":
            return _dispatch_console_action(namespace, "install-packages", args, "install-packages " + " ".join(args))
        if action in {"sdd", "explore", "proposal", "spec", "design", "tasks", "tdd", "artifacts"}:
            return _dispatch_console_action(namespace, action, args, action + " " + " ".join(args))
        if action == "raw":
            raw = args[1:] if args[:1] == ["--"] else args
            return _backend_client(namespace).raw(raw)
        return _start(namespace, args)
    except _LauncherExit:
        return 0
    except KeyboardInterrupt:
        print("\nPrompt cancelled.", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
