"""Console loop and command dispatch for the AI Harness launcher."""

from __future__ import annotations

import argparse
import os
import sys
import termios
from pathlib import Path

from ai_harness.ci_support import ci_preflight
from ai_harness.bundle_inputs import compatible_runs
from ai_harness.recommended_packages import load_recommended_package_groups

from .backend_client import BackendClient
from .bootstrap import ACTIONS, GITHUB_CI_MODES, RUNNER, _default_provider, _parser, _prompt_for_model, _prompt_for_reasoning_effort
from .console_actions import (
    CONSOLE_ACTIONS,
    ConsoleAction,
    action_names,
    actions_by_name,
    parse_console_line,
    suggest_console_actions,
    visible_actions,
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
_CONSOLE_ACTION_BY_NAME = actions_by_name(CONSOLE_ACTIONS)
_REQUEST_PROMPT_ACTIONS = {"model", "ci-mode"}


def _backend_client(namespace: argparse.Namespace) -> BackendClient:
    def run_backend(args: list[str]) -> int:
        return _run(args, verbose=namespace.verbose, dry_run=namespace.dry_run)

    return BackendClient(namespace.cwd.resolve(), run_backend)


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
    optional_groups = [group for group in load_recommended_package_groups() if not group.required]
    return [
        _MenuItem(str(index), f"{group.label} [{group.id}] - {group.description}", group.id, (group.id,))
        for index, group in enumerate(optional_groups, 1)
    ]


def _package_install_args(args: list[str]) -> tuple[list[str], bool, bool]:
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


def _select_github_ci_mode(namespace: argparse.Namespace, args: list[str]) -> int:
    if len(args) > 1:
        print("error: ci-mode accepts at most one mode", file=sys.stderr)
        return 2
    current = getattr(namespace, "github_ci_mode", None) or "baseline"
    if args:
        selected = args[0].strip().lower()
        if selected not in GITHUB_CI_MODES:
            print("error: GitHub CI mode must be off, baseline, or branch", file=sys.stderr)
            return 2
    else:
        selected = _menu_prompt(
            ["GitHub CI mode", f"Current: {current}"],
            [
                _MenuItem("o", "Off", "off", ("off",)),
                _MenuItem("b", "Baseline", "baseline", ("baseline",)),
                _MenuItem("r", "Branch", "branch", ("branch",)),
            ],
            help_kind="console",
            default_index=GITHUB_CI_MODES.index(current),
        ).value
    setattr(namespace, "github_ci_mode", selected)
    print(f"Selected GitHub CI mode: {selected}", file=sys.stderr)
    return 0


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
    print("Controls:", file=sys.stderr)
    print("  / or /menu: open the action menu", file=sys.stderr)
    for action in visible_actions(_CONSOLE_ACTIONS):
        aliases = ", ".join(f"/{alias}" for alias in action.aliases)
        suffix = f" ({aliases})" if aliases else ""
        print(f"  /{action.name}: {action.label}{suffix}", file=sys.stderr)
    print("  Any other text starts a harness run", file=sys.stderr)


def _console_action_menu(namespace: argparse.Namespace) -> int:
    items = [
        _MenuItem(action.key, action.label, action.name, action_names(action))
        for action in visible_actions(_CONSOLE_ACTIONS)
    ]
    selected = _menu_prompt(["Console actions"], items, help_kind="console").value
    return _dispatch_console_action(namespace, selected, [], selected)


def _console_suggestion_label(action: ConsoleAction) -> str:
    aliases = ", ".join(f"/{alias}" for alias in action.aliases[:2])
    suffix = f"  {aliases}" if aliases else ""
    return f"/{action.name:<16} {action.label}{suffix}"


def _render_console_prompt(buffer: list[str], slash_mode: bool, selected: int, previous_lines: int) -> int:
    query = "".join(buffer)[1:] if slash_mode else ""
    suggestions = suggest_console_actions(query) if slash_mode else []
    rendered = 1 + len(suggestions) + 1
    rows = max(previous_lines, rendered)
    if previous_lines:
        print(f"\x1b[{previous_lines}F", end="", file=sys.stderr)
    prompt = "aih> "
    value = "".join(buffer)
    if slash_mode:
        if not value.startswith("/"):
            value = "/" + value
        line = f"{prompt}\x1b[36m{value}\x1b[0m"
    else:
        line = f"{prompt}{value}"
    print(f"\x1b[2K{line}", file=sys.stderr)
    for index, action in enumerate(suggestions):
        marker = ">" if index == selected else " "
        print(f"\x1b[2K{marker} {_console_suggestion_label(action)}", file=sys.stderr)
    for _ in range(rows - rendered):
        print("\x1b[2K", file=sys.stderr)
    print("\x1b[2K", end="", file=sys.stderr)
    return rows


def _interactive_console_line() -> str | None:
    if not _interactive_stdin():
        try:
            print("aih> ", end="", file=sys.stderr, flush=True)
            return input().strip()
        except EOFError:
            return None
    try:
        with _RawTerminal():
            buffer: list[str] = []
            slash_mode = False
            selected = 0
            rendered_lines = _render_console_prompt(buffer, slash_mode, selected, 0)
            while True:
                key = _read_key()
                if key == "\x04":
                    print(file=sys.stderr)
                    return None
                if key in {"\r", "\n"}:
                    value = "".join(buffer).strip()
                    if slash_mode:
                        query = value[1:] if value.startswith("/") else value
                        if not query:
                            print(file=sys.stderr)
                            return "/"
                        suggestions = suggest_console_actions(query)
                        if suggestions:
                            print(file=sys.stderr)
                            return "/" + suggestions[min(selected, len(suggestions) - 1)].name
                    print(file=sys.stderr)
                    return value
                if key == "up" and slash_mode:
                    suggestions = suggest_console_actions("".join(buffer)[1:])
                    if suggestions:
                        selected = (selected - 1) % len(suggestions)
                        rendered_lines = _render_console_prompt(buffer, slash_mode, selected, rendered_lines)
                    continue
                if key == "down" and slash_mode:
                    suggestions = suggest_console_actions("".join(buffer)[1:])
                    if suggestions:
                        selected = (selected + 1) % len(suggestions)
                        rendered_lines = _render_console_prompt(buffer, slash_mode, selected, rendered_lines)
                    continue
                if key.startswith("\x1b"):
                    if slash_mode:
                        buffer.clear()
                        slash_mode = False
                        selected = 0
                        rendered_lines = _render_console_prompt(buffer, slash_mode, selected, rendered_lines)
                    continue
                if key in {"\x7f", "\b"}:
                    if buffer:
                        buffer.pop()
                        if not buffer:
                            slash_mode = False
                        selected = 0
                        rendered_lines = _render_console_prompt(buffer, slash_mode, selected, rendered_lines)
                    continue
                if len(key) == 1 and key.isprintable():
                    if not buffer and key == "/":
                        slash_mode = True
                    buffer.append(key)
                    selected = 0
                    rendered_lines = _render_console_prompt(buffer, slash_mode, selected, rendered_lines)
                    continue
    except (OSError, termios.error):
        try:
            print("aih> ", end="", file=sys.stderr, flush=True)
            return input().strip()
        except EOFError:
            return None


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


def _source_run_for_bundle(namespace: argparse.Namespace, bundle: str, args: list[str]) -> str | None:
    if args:
        if args[0] == "--from-run" and len(args) > 1:
            return args[1]
        return args[0]
    required = {
        "proposal": "published/explore-handoff.json",
        "spec": "published/proposal-handoff.json",
        "design": "published/spec-handoff.json",
        "tasks": "published/design-handoff.json",
        "tdd": "published/tasks-handoff.json",
    }.get(bundle)
    if required is None or not sys.stdin.isatty():
        return None
    runs = compatible_runs(namespace.cwd.resolve(), required)[:10]
    if not runs:
        return _line_prompt("Source run id/path: ", help_kind="console").strip() or None
    items = [_MenuItem(str(index), f"{item['run_id']} - has {required}", str(item["run_id"]), (str(item["run_id"]),)) for index, item in enumerate(runs, 1)]
    items.append(_MenuItem("m", "Enter run id/path", "__manual__", ("manual",)))
    selected = _menu_prompt([f"Source run for {bundle}"], items, help_kind="console").value
    if selected == "__manual__":
        return _line_prompt("Source run id/path: ", help_kind="console").strip() or None
    return selected


def _dispatch_console_action(namespace: argparse.Namespace, command: str, args: list[str], raw_line: str) -> int:
    repository = str(namespace.cwd.resolve())
    if command == "exit":
        raise _LauncherExit
    if command == "help":
        _console_help()
        return 0
    client = _backend_client(namespace)
    if command == "status":
        return client.status()
    if command == "runs":
        return client.runs()
    if command == "resume":
        return _resume(namespace, args[0] if args else None)
    if command == "archive":
        return _archive(namespace, args[0] if args else None)
    if command == "start":
        _refresh_recovery_block(namespace)
        if getattr(namespace, "_recovery_blocked", False):
            print("error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work", file=sys.stderr)
            return 1
        request = raw_line.split(None, 1)[1].strip() if args else _interactive_start_request(namespace)
        if not request:
            print("error: request is empty", file=sys.stderr)
            return 2
        return _start(namespace, [], request_override=request)
    if command in {"sdd", "explore", "proposal", "spec", "design", "tasks", "tdd"}:
        _refresh_recovery_block(namespace)
        if getattr(namespace, "_recovery_blocked", False):
            print("error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work", file=sys.stderr)
            return 1
        request = raw_line.split(None, 1)[1].strip() if args and command in {"sdd", "explore"} else None
        source_run = _source_run_for_bundle(namespace, command, args) if command not in {"sdd", "explore"} else None
        return _start(namespace, [], request_override=request, flow=command, source_run=source_run)
    if command == "artifacts":
        run_id = args[0] if args else _line_prompt("Run id: ", help_kind="console").strip()
        root = namespace.cwd.resolve() / ".ai-harness" / "artifacts" / "runs" / run_id
        if not root.is_dir():
            print(f"error: run not found: {run_id}", file=sys.stderr)
            return 1
        for item in sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()):
            print(item)
        return 0
    if command == "ci-mode":
        return _select_github_ci_mode(namespace, args)
    if command == "install-ci":
        force = "--force" in args
        targets = [item for item in args if item != "--force"]
        target = targets[0] if targets else None
        if len(targets) > 1:
            print("error: install-ci accepts at most one target", file=sys.stderr)
            return 2
        if target is None and sys.stdin.isatty():
            target = _menu_prompt(
                ["Install CI templates"],
                [
                    _MenuItem("g", "GitHub Actions", "github", ("github",)),
                    _MenuItem("l", "GitLab CI", "gitlab", ("gitlab",)),
                    _MenuItem("b", "Both", "both", ("both",)),
                ],
                help_kind="console",
            ).value
        return client.install_ci(target=target, force=force)
    if command == "install-packages":
        optionals, all_optional, dry_install = _package_install_args(args)
        if not optionals and not all_optional and sys.stdin.isatty():
            selected = _multi_select_prompt(["Optional recommended packages", "Required groups are always included."], _package_group_items(), help_kind="multi")
            optionals = [item.value for item in selected]
        return client.install_packages(optionals=optionals, all_optional=all_optional, dry_install=dry_install)
    if command == "model":
        provider = _default_provider(namespace.provider)
        selected = _prompt_for_model(provider)
        setattr(namespace, "model", selected)
        print(f"Selected model: {selected or 'provider default'}", file=sys.stderr)
        effort = _prompt_for_reasoning_effort(provider)
        if effort is not None:
            setattr(namespace, "reasoning_effort", effort)
            print(f"Selected reasoning effort: {effort or 'provider default'}", file=sys.stderr)
        return 0
    raise ValueError(f"unsupported console action: {command}")


def _interactive_start_request(namespace: argparse.Namespace) -> str:
    def handle_request_command(value: str) -> bool:
        parsed = parse_console_line(value, context="request")
        if parsed.kind == "error":
            print(f"error: {parsed.error}", file=sys.stderr)
            return True
        if parsed.kind != "action" or parsed.action is None or parsed.action.name not in _REQUEST_PROMPT_ACTIONS:
            return False
        _dispatch_console_action(namespace, parsed.action.name, list(parsed.args), parsed.raw_line.lstrip("/"))
        return True

    return _interactive_request(slash_handler=handle_request_command)


def _console_command(namespace: argparse.Namespace, line: str) -> int:
    parsed = parse_console_line(line)
    if parsed.kind == "menu":
        return _console_action_menu(namespace)
    if parsed.kind == "empty":
        return 0
    if parsed.kind == "error":
        print(f"error: {parsed.error}", file=sys.stderr)
        return 2
    if parsed.kind == "action" and parsed.action is not None:
        return _dispatch_console_action(namespace, parsed.action.name, list(parsed.args), parsed.raw_line.lstrip("/"))
    if parsed.kind == "unknown_slash":
        print(parsed.error, file=sys.stderr)
        return 0
    _refresh_recovery_block(namespace)
    if getattr(namespace, "_recovery_blocked", False):
        print("error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work", file=sys.stderr)
        return 1
    return _start(namespace, [], request_override=parsed.request or line)


def _console_loop(namespace: argparse.Namespace) -> int:
    print("AI Code Harness console. Type `/` for actions or enter a request.", file=sys.stderr)
    last_status = 0
    try:
        recovered = _startup_recovery(namespace)
        if recovered is not None:
            last_status = recovered
    except KeyboardInterrupt:
        print("\nPrompt cancelled.", file=sys.stderr)
    while True:
        try:
            line = _interactive_console_line()
            if line is None:
                print(file=sys.stderr)
                return last_status
            if not line:
                continue
            try:
                last_status = _console_command(namespace, line)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                last_status = 1
        except EOFError:
            print(file=sys.stderr)
            return last_status
        except KeyboardInterrupt:
            print("\nPrompt cancelled.", file=sys.stderr)
            last_status = 130
        except _LauncherExit:
            return 0


def _start(
    namespace: argparse.Namespace,
    prompt_args: list[str],
    *,
    request_override: str | None = None,
    route: str | None = None,
    flow: str | None = None,
    source_run: str | None = None,
) -> int:
    provider = _default_provider(namespace.provider)
    backend = ["--cwd", str(namespace.cwd.resolve()), "--provider", provider, "--activated"]
    model = getattr(namespace, "model", None)
    if model:
        backend.extend(["--model", model])
    reasoning_effort = getattr(namespace, "reasoning_effort", None)
    if reasoning_effort:
        backend.extend(["--reasoning-effort", reasoning_effort])
    github_ci_mode = getattr(namespace, "github_ci_mode", None)
    if github_ci_mode:
        backend.extend(["--github-ci-mode", github_ci_mode])
    request: str | None = request_override
    if namespace.prompt_file is not None:
        if prompt_args or request_override is not None:
            print("error: --file cannot be combined with an inline request", file=sys.stderr)
            return 2
        backend.extend(["--prompt-file", str(namespace.prompt_file.expanduser())])
    elif request is None:
        request = " ".join(prompt_args).strip()
        if not request and not sys.stdin.isatty():
            request = sys.stdin.read().strip()
    if namespace.prompt_file is None and not request:
        if source_run and flow:
            request = f"Run {flow} bundle from {source_run}"
        elif sys.stdin.isatty():
            return _console_loop(namespace)
        else:
            print("error: a request is required", file=sys.stderr)
            return 2
    if sys.stdin.isatty():
        _startup_ci_preflight(namespace)
    backend.extend(_branch_args(namespace))
    if namespace.prompt_file is None and request and sys.stdin.isatty():
        request = _prepare_console_request(namespace, request)
    if route is None and flow is not None:
        route = "code"
    if route is None and sys.stdin.isatty():
        route = _select_route_for_start()
    if route:
        backend.extend(["--route", route])
    if route in {"code", None} and flow is None and sys.stdin.isatty():
        flow = _select_code_flow()
    if flow:
        backend.extend(["--flow", flow])
    if source_run is None and flow in {"proposal", "spec", "design", "tasks", "tdd"}:
        source_run = _source_run_for_bundle(namespace, flow, [])
    if source_run:
        backend.extend(["--from-run", source_run])
    return _run_and_follow_decisions(namespace, backend, request=request)


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
    backend = ["--cwd", str(repository), "--provider", _default_provider(namespace.provider), "--activated", "--resume", actual_run_id]
    model = getattr(namespace, "model", None)
    if model is None and isinstance(state, dict):
        model = state.get("selected_model") or None
    if model:
        backend.extend(["--model", model])
    reasoning_effort = getattr(namespace, "reasoning_effort", None)
    if reasoning_effort:
        backend.extend(["--reasoning-effort", reasoning_effort])
    github_ci_mode = getattr(namespace, "github_ci_mode", None)
    if github_ci_mode:
        backend.extend(["--github-ci-mode", github_ci_mode])
    if state.get("status") == "waiting_for_user" and sys.stdin.isatty():
        request = _decision_request(current, state)
        if request is not None:
            answer, selected = _prompt_for_decision(actual_run_id, request)
            if answer is not None:
                backend.extend(["--answer", answer])
            if selected is not None:
                backend.extend(["--selected-option", selected])
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
    code = _run(["--cwd", str(namespace.cwd.resolve()), "--archive", run_id], verbose=namespace.verbose, dry_run=namespace.dry_run)
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
