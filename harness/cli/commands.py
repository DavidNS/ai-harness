"""Console loop and command dispatch for the AI Harness launcher."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from dataclasses import dataclass

from ai_harness.ci_support import ci_preflight
from ai_harness.bundle_inputs import compatible_runs
from ai_harness.recommended_packages import load_recommended_package_groups

from .bootstrap import ACTIONS, GITHUB_CI_MODES, RUNNER, _default_provider, _parser, _prompt_for_model, _prompt_for_reasoning_effort
from .runtime import (
    _decision_request,
    _find_run,
    _print_unfinished_runs,
    _run,
    _run_line,
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


def _startup_recovery(namespace: argparse.Namespace) -> int | None:
    repository = namespace.cwd.resolve()
    runs = _unfinished_runs(repository)
    setattr(namespace, "_recovery_blocked", False)
    if not runs:
        return None
    if len(runs) > 1:
        setattr(namespace, "_recovery_blocked", True)
        _print_unfinished_runs(repository, runs, heading="Unfinished runs found")
        print("Use `resume <RUN_ID>` or `archive <RUN_ID>` before starting unrelated work.", file=sys.stderr)
        return None
    _, state = runs[0]
    run_id = str(state.get("run_id"))
    selected = _menu_prompt(
        ["Unfinished run found", _run_line(None, state)],
        [
            _MenuItem("r", f"Resume {run_id}", "resume", ("resume",)),
            _MenuItem("a", f"Archive {run_id}", "archive", ("archive",)),
            _MenuItem("n", "Start a new request", "new", ("new", "start")),
        ],
        help_kind="action",
    ).value
    if selected == "resume":
        return _resume(namespace, run_id)
    if selected == "archive":
        return _archive(namespace, run_id)
    return None


@dataclass(frozen=True, slots=True)
class _ConsoleAction:
    name: str
    label: str
    key: str
    shortcuts: tuple[str, ...] = ()
    menu_visible: bool = True


_CONSOLE_ACTIONS = (
    _ConsoleAction("status", "Show status", "s"),
    _ConsoleAction("runs", "Show live runs", "r"),
    _ConsoleAction("resume", "Resume run", "u"),
    _ConsoleAction("archive", "Archive run", "a"),
    _ConsoleAction("start", "Start request", "n", ("new",)),
    _ConsoleAction("sdd", "Start full SDD", "f"),
    _ConsoleAction("explore", "Run explore bundle", "e"),
    _ConsoleAction("proposal", "Run proposal bundle", "o"),
    _ConsoleAction("model", "Select model", "m"),
    _ConsoleAction("ci-mode", "Select GitHub CI mode", "g", ("ci", "github-ci")),
    _ConsoleAction("install-ci", "Install CI", "c"),
    _ConsoleAction("install-packages", "Install packages", "p", ("packages",)),
    _ConsoleAction("help", "Show help", "h"),
    _ConsoleAction("exit", "Exit launcher", "x", ("quit",)),
)
_CONSOLE_ACTION_BY_NAME = {
    value: action
    for action in _CONSOLE_ACTIONS
    for value in (action.name, *action.shortcuts)
}


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
    for action in _CONSOLE_ACTIONS:
        if action.menu_visible:
            print(f"  /{action.name}: {action.label}", file=sys.stderr)
    print("  Any other text starts a harness run", file=sys.stderr)


def _console_action_menu(namespace: argparse.Namespace) -> int:
    items = [
        _MenuItem(action.key, action.label, action.name, (action.name, *action.shortcuts))
        for action in _CONSOLE_ACTIONS
        if action.menu_visible
    ]
    selected = _menu_prompt(["Console actions"], items, help_kind="console").value
    return _dispatch_console_action(namespace, selected, [], selected)


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
    if command == "status":
        return _run(["--cwd", repository, "--status"], verbose=namespace.verbose, dry_run=namespace.dry_run)
    if command == "runs":
        return _run(["--cwd", repository, "--show-runs"], verbose=namespace.verbose, dry_run=namespace.dry_run)
    if command == "resume":
        return _resume(namespace, args[0] if args else None)
    if command == "archive":
        return _archive(namespace, args[0] if args else None)
    if command == "start":
        if getattr(namespace, "_recovery_blocked", False):
            print("error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work", file=sys.stderr)
            return 1
        request = raw_line.split(None, 1)[1].strip() if args else _interactive_request()
        if not request:
            print("error: request is empty", file=sys.stderr)
            return 2
        return _start(namespace, [], request_override=request)
    if command in {"sdd", "explore", "proposal", "spec", "design", "tasks", "tdd"}:
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
        backend = ["--cwd", repository, "--install-ci"]
        if target:
            backend.extend(["--ci-target", target])
        if force:
            backend.append("--force")
        return _run(backend, verbose=namespace.verbose, dry_run=namespace.dry_run)
    if command == "install-packages":
        optionals, all_optional, dry_install = _package_install_args(args)
        if not optionals and not all_optional and sys.stdin.isatty():
            selected = _multi_select_prompt(["Optional recommended packages", "Required groups are always included."], _package_group_items(), help_kind="multi")
            optionals = [item.value for item in selected]
        backend = ["--cwd", repository, "--install-packages"]
        for optional in optionals:
            backend.extend(["--package", optional])
        if all_optional:
            backend.append("--all-packages")
        if dry_install:
            backend.append("--dry-install")
        return _run(backend, verbose=namespace.verbose, dry_run=namespace.dry_run)
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


def _console_command(namespace: argparse.Namespace, line: str) -> int:
    is_slash = line.startswith("/")
    normalized_line = line[1:] if is_slash else line
    if normalized_line in {"", "menu"}:
        return _console_action_menu(namespace)
    try:
        parts = shlex.split(normalized_line)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not parts:
        return 0
    command = parts[0].casefold()
    action = _CONSOLE_ACTION_BY_NAME.get(command)
    if action is not None:
        return _dispatch_console_action(namespace, action.name, parts[1:], normalized_line)
    if is_slash:
        print(f"Unknown slash command: /{command}", file=sys.stderr)
        return 0
    if getattr(namespace, "_recovery_blocked", False):
        print("error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work", file=sys.stderr)
        return 1
    return _start(namespace, [], request_override=line)


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
            print("aih> ", end="", file=sys.stderr, flush=True)
            line = input().strip()
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


def _start(namespace: argparse.Namespace, prompt_args: list[str], *, request_override: str | None = None, flow: str | None = None, source_run: str | None = None) -> int:
    provider = _default_provider(namespace.provider)
    backend = ["--cwd", str(namespace.cwd.resolve()), "--provider", provider, "--activated"]
    backend.extend(_branch_args(namespace))
    if flow:
        backend.extend(["--flow", flow])
    if source_run:
        backend.extend(["--from-run", source_run])
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
    if namespace.prompt_file is None and request and sys.stdin.isatty():
        request = _prepare_console_request(namespace, request)
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
    return _run(["--cwd", str(namespace.cwd.resolve()), "--archive", run_id], verbose=namespace.verbose, dry_run=namespace.dry_run)


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
            return _run(["--cwd", str(namespace.cwd.resolve()), "--status"], verbose=namespace.verbose, dry_run=namespace.dry_run)
        if action == "runs":
            return _run(["--cwd", str(namespace.cwd.resolve()), "--show-runs"], verbose=namespace.verbose, dry_run=namespace.dry_run)
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
            return _run(raw, verbose=namespace.verbose, dry_run=namespace.dry_run)
        return _start(namespace, args)
    except _LauncherExit:
        return 0
    except KeyboardInterrupt:
        print("\nPrompt cancelled.", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
