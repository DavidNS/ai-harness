"""Console controller for interactive launcher commands."""

from __future__ import annotations

import argparse
import sys
import termios
from collections.abc import Callable
from dataclasses import dataclass

from ai_harness.bundle_inputs import compatible_runs
from ai_harness.recommended_packages import load_recommended_package_groups

from .backend_client import BackendClient
from .job_runner import BackgroundJobRunner
from .bootstrap import GITHUB_CI_MODES, _default_provider
from .console_actions import (
    CONSOLE_ACTIONS,
    ConsoleAction,
    action_names,
    parse_console_line,
    suggest_console_actions,
    visible_actions,
)
from .ui_primitives import _MenuItem


StartCallback = Callable[..., int]
StartJobCallback = Callable[..., int]
ResumeCallback = Callable[[argparse.Namespace, str | None], int]
ArchiveCallback = Callable[[argparse.Namespace, str | None], int]
RefreshCallback = Callable[[argparse.Namespace], None]
PromptModelCallback = Callable[[str], str | None]
PromptReasoningCallback = Callable[[str], str | None]
MenuPromptCallback = Callable[..., _MenuItem]
MultiSelectPromptCallback = Callable[..., list[_MenuItem]]
LinePromptCallback = Callable[..., str | None]
InteractiveRequestCallback = Callable[..., str]
ReadKeyCallback = Callable[[], str]
InteractiveStdinCallback = Callable[[], bool]
RawTerminalFactory = Callable[[], object]


_REQUEST_PROMPT_ACTIONS = {"model", "ci-mode"}


@dataclass(frozen=True, slots=True)
class ConsoleControllerDependencies:
    start: StartCallback
    start_job: StartJobCallback
    resume: ResumeCallback
    archive: ArchiveCallback
    refresh_recovery_block: RefreshCallback
    prompt_for_model: PromptModelCallback
    prompt_for_reasoning_effort: PromptReasoningCallback
    menu_prompt: MenuPromptCallback
    multi_select_prompt: MultiSelectPromptCallback
    line_prompt: LinePromptCallback
    interactive_request: InteractiveRequestCallback
    interactive_stdin: InteractiveStdinCallback
    raw_terminal: RawTerminalFactory
    read_key: ReadKeyCallback
    launcher_exit: type[BaseException]


class ConsoleController:
    def __init__(self, namespace: argparse.Namespace, backend: BackendClient, deps: ConsoleControllerDependencies, jobs: BackgroundJobRunner | None = None) -> None:
        self.namespace = namespace
        self.backend = backend
        self.deps = deps
        self.jobs = jobs or BackgroundJobRunner(namespace.cwd.resolve())

    def console_help(self) -> None:
        print("Controls:", file=sys.stderr)
        print("  / or /menu: open the action menu", file=sys.stderr)
        for action in visible_actions(CONSOLE_ACTIONS):
            aliases = ", ".join(f"/{alias}" for alias in action.aliases)
            suffix = f" ({aliases})" if aliases else ""
            print(f"  /{action.name}: {action.label}{suffix}", file=sys.stderr)
        print("  Any other text starts a harness run", file=sys.stderr)

    def console_action_menu(self) -> int:
        items = [
            _MenuItem(action.key, action.label, action.name, action_names(action))
            for action in visible_actions(CONSOLE_ACTIONS)
        ]
        selected = self.deps.menu_prompt(["Console actions"], items, help_kind="console").value
        return self.dispatch_console_action(selected, [], selected)

    def dispatch_console_action(self, command: str, args: list[str], raw_line: str) -> int:
        if command == "exit":
            raise self.deps.launcher_exit
        if command == "help":
            self.console_help()
            return 0
        if command == "status":
            return self.backend.status()
        if command == "runs":
            return self.backend.runs()
        if command == "jobs":
            return self.show_jobs()
        if command == "attach":
            return self.attach_job(args[0] if args else None)
        if command == "detach":
            print("No attached job.", file=sys.stderr)
            return 0
        if command == "cancel":
            return self.cancel_job(args[0] if args else None)
        if command == "resume":
            return self.deps.resume(self.namespace, args[0] if args else None)
        if command == "archive":
            return self.deps.archive(self.namespace, args[0] if args else None)
        if command == "start":
            self.deps.refresh_recovery_block(self.namespace)
            if getattr(self.namespace, "_recovery_blocked", False):
                print("error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work", file=sys.stderr)
                return 1
            request = raw_line.split(None, 1)[1].strip() if args else self.interactive_start_request()
            if not request:
                print("error: request is empty", file=sys.stderr)
                return 2
            return self.deps.start_job(self.namespace, [], request_override=request)
        if command in {"sdd", "explore", "proposal", "spec", "design", "tasks", "tdd"}:
            self.deps.refresh_recovery_block(self.namespace)
            if getattr(self.namespace, "_recovery_blocked", False):
                print("error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work", file=sys.stderr)
                return 1
            request = raw_line.split(None, 1)[1].strip() if args and command in {"sdd", "explore"} else None
            source_run = self.source_run_for_bundle(command, args) if command not in {"sdd", "explore"} else None
            return self.deps.start_job(self.namespace, [], request_override=request, flow=command, source_run=source_run)
        if command == "artifacts":
            run_id = args[0] if args else (self.deps.line_prompt("Run id: ", help_kind="console") or "").strip()
            root = self.namespace.cwd.resolve() / ".ai-harness" / "artifacts" / "runs" / run_id
            if not root.is_dir():
                print(f"error: run not found: {run_id}", file=sys.stderr)
                return 1
            for item in sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()):
                print(item)
            return 0
        if command == "ci-mode":
            return self.select_github_ci_mode(args)
        if command == "install-ci":
            force = "--force" in args
            targets = [item for item in args if item != "--force"]
            target = targets[0] if targets else None
            if len(targets) > 1:
                print("error: install-ci accepts at most one target", file=sys.stderr)
                return 2
            if target is None and sys.stdin.isatty():
                target = self.deps.menu_prompt(
                    ["Install CI templates"],
                    [
                        _MenuItem("g", "GitHub Actions", "github", ("github",)),
                        _MenuItem("l", "GitLab CI", "gitlab", ("gitlab",)),
                        _MenuItem("b", "Both", "both", ("both",)),
                    ],
                    help_kind="console",
                ).value
            return self.backend.install_ci(target=target, force=force)
        if command == "install-packages":
            optionals, all_optional, dry_install = package_install_args(args)
            if not optionals and not all_optional and sys.stdin.isatty():
                selected = self.deps.multi_select_prompt(
                    ["Optional recommended packages", "Required groups are always included."],
                    package_group_items(),
                    help_kind="multi",
                )
                optionals = [item.value for item in selected]
            return self.backend.install_packages(optionals=optionals, all_optional=all_optional, dry_install=dry_install)
        if command == "model":
            provider = _default_provider(self.namespace.provider)
            selected = self.deps.prompt_for_model(provider)
            setattr(self.namespace, "model", selected)
            print(f"Selected model: {selected or 'provider default'}", file=sys.stderr)
            effort = self.deps.prompt_for_reasoning_effort(provider)
            if effort is not None:
                setattr(self.namespace, "reasoning_effort", effort)
                print(f"Selected reasoning effort: {effort or 'provider default'}", file=sys.stderr)
            return 0
        raise ValueError(f"unsupported console action: {command}")


    def show_jobs(self) -> int:
        jobs = self.jobs.store.list_jobs()
        if not jobs:
            print("No background jobs.", file=sys.stderr)
            return 0
        for job in jobs[:20]:
            job_id = str(job.get("job_id", ""))
            status = str(job.get("status", "unknown"))
            pid = job.get("pid")
            exit_code = job.get("exit_code")
            suffix = f" pid={pid}" if pid else ""
            if exit_code is not None:
                suffix += f" exit={exit_code}"
            print(f"{job_id} [{status}]{suffix}", file=sys.stderr)
        return 0

    def _latest_job_id(self) -> str | None:
        jobs = self.jobs.store.list_jobs()
        if not jobs:
            return None
        value = jobs[0].get("job_id")
        return str(value) if isinstance(value, str) else None

    def attach_job(self, job_id: str | None) -> int:
        selected = job_id or self._latest_job_id()
        if not selected:
            print("No background jobs.", file=sys.stderr)
            return 1
        metadata = self.jobs.store.read_metadata(selected)
        if metadata is None:
            print(f"error: job not found: {selected}", file=sys.stderr)
            return 1
        print(f"Attached to job {selected}. Ctrl-C detaches.", file=sys.stderr)
        offset = 0
        try:
            while True:
                offset, events = self.jobs.store.read_events(selected, start=offset)
                for event in events:
                    self._print_job_event(event)
                metadata = self.jobs.store.read_metadata(selected) or metadata
                if metadata.get("status") != "running":
                    return int(metadata.get("exit_code") or 0)
                import time

                time.sleep(0.2)
        except KeyboardInterrupt:
            print("Detached.", file=sys.stderr)
            return 0

    def cancel_job(self, job_id: str | None) -> int:
        selected = job_id or self._latest_job_id()
        if not selected:
            print("No background jobs.", file=sys.stderr)
            return 1
        if not self.jobs.cancel(selected):
            print(f"error: job is not running in this console: {selected}", file=sys.stderr)
            return 1
        print(f"Cancelled job {selected}.", file=sys.stderr)
        return 0

    def _print_job_event(self, event: dict[str, object]) -> None:
        kind = str(event.get("type", "event"))
        if kind in {"stdout", "stderr", "progress"}:
            text = str(event.get("text", ""))
            if text:
                print(text, file=sys.stderr)
            return
        if kind == "started":
            print("job started", file=sys.stderr)
            return
        if kind == "decision_requested":
            print(f"decision required for run {event.get('run_id')}", file=sys.stderr)
            return
        if kind == "finished":
            print(f"job finished exit={event.get('exit_code')}", file=sys.stderr)
            return
        if kind == "cancelled":
            print("job cancelled", file=sys.stderr)
            return
        print(kind, file=sys.stderr)

    def interactive_start_request(self) -> str:
        def handle_request_command(value: str) -> bool:
            parsed = parse_console_line(value, context="request")
            if parsed.kind == "error":
                print(f"error: {parsed.error}", file=sys.stderr)
                return True
            if parsed.kind != "action" or parsed.action is None or parsed.action.name not in _REQUEST_PROMPT_ACTIONS:
                return False
            self.dispatch_console_action(parsed.action.name, list(parsed.args), parsed.raw_line.lstrip("/"))
            return True

        return self.deps.interactive_request(slash_handler=handle_request_command)

    def console_command(self, line: str) -> int:
        parsed = parse_console_line(line)
        if parsed.kind == "menu":
            return self.console_action_menu()
        if parsed.kind == "empty":
            return 0
        if parsed.kind == "error":
            print(f"error: {parsed.error}", file=sys.stderr)
            return 2
        if parsed.kind == "action" and parsed.action is not None:
            return self.dispatch_console_action(parsed.action.name, list(parsed.args), parsed.raw_line.lstrip("/"))
        if parsed.kind == "unknown_slash":
            print(parsed.error, file=sys.stderr)
            return 0
        self.deps.refresh_recovery_block(self.namespace)
        if getattr(self.namespace, "_recovery_blocked", False):
            print("error: resolve unfinished runs with resume <RUN_ID> or archive <RUN_ID> before starting new work", file=sys.stderr)
            return 1
        return self.deps.start_job(self.namespace, [], request_override=parsed.request or line)

    def console_loop(self, startup_recovery: Callable[[argparse.Namespace], int | None]) -> int:
        print("AI Code Harness console. Type `/` for actions or enter a request.", file=sys.stderr)
        last_status = 0
        try:
            recovered = startup_recovery(self.namespace)
            if recovered is not None:
                last_status = recovered
        except KeyboardInterrupt:
            print("\nPrompt cancelled.", file=sys.stderr)
            return 130
        while True:
            try:
                line = interactive_console_line(self.deps)
                if line is None:
                    print(file=sys.stderr)
                    return last_status
                if not line:
                    continue
                try:
                    last_status = self.console_command(line)
                except ValueError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    last_status = 1
            except EOFError:
                print(file=sys.stderr)
                return last_status
            except KeyboardInterrupt:
                print("\nPrompt cancelled.", file=sys.stderr)
                last_status = 130
            except self.deps.launcher_exit:
                return 0

    def select_github_ci_mode(self, args: list[str]) -> int:
        if len(args) > 1:
            print("error: ci-mode accepts at most one mode", file=sys.stderr)
            return 2
        current = getattr(self.namespace, "github_ci_mode", None) or "baseline"
        if args:
            selected = args[0].strip().lower()
            if selected not in GITHUB_CI_MODES:
                print("error: GitHub CI mode must be off, baseline, or branch", file=sys.stderr)
                return 2
        else:
            selected = self.deps.menu_prompt(
                ["GitHub CI mode", f"Current: {current}"],
                [
                    _MenuItem("o", "Off", "off", ("off",)),
                    _MenuItem("b", "Baseline", "baseline", ("baseline",)),
                    _MenuItem("r", "Branch", "branch", ("branch",)),
                ],
                help_kind="console",
                default_index=GITHUB_CI_MODES.index(current),
            ).value
        setattr(self.namespace, "github_ci_mode", selected)
        print(f"Selected GitHub CI mode: {selected}", file=sys.stderr)
        return 0

    def source_run_for_bundle(self, bundle: str, args: list[str]) -> str | None:
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
        runs = compatible_runs(self.namespace.cwd.resolve(), required)[:10]
        if not runs:
            return (self.deps.line_prompt("Source run id/path: ", help_kind="console") or "").strip() or None
        items = [_MenuItem(str(index), f"{item['run_id']} - has {required}", str(item["run_id"]), (str(item["run_id"]),)) for index, item in enumerate(runs, 1)]
        items.append(_MenuItem("m", "Enter run id/path", "__manual__", ("manual",)))
        selected = self.deps.menu_prompt([f"Source run for {bundle}"], items, help_kind="console").value
        if selected == "__manual__":
            return (self.deps.line_prompt("Source run id/path: ", help_kind="console") or "").strip() or None
        return selected


def package_group_items() -> list[_MenuItem]:
    optional_groups = [group for group in load_recommended_package_groups() if not group.required]
    return [
        _MenuItem(str(index), f"{group.label} [{group.id}] - {group.description}", group.id, (group.id,))
        for index, group in enumerate(optional_groups, 1)
    ]


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


def console_suggestion_label(action: ConsoleAction) -> str:
    aliases = ", ".join(f"/{alias}" for alias in action.aliases[:2])
    suffix = f"  {aliases}" if aliases else ""
    return f"/{action.name:<16} {action.label}{suffix}"


def render_console_prompt(buffer: list[str], slash_mode: bool, selected: int, previous_lines: int) -> int:
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
        print(f"\x1b[2K{marker} {console_suggestion_label(action)}", file=sys.stderr)
    for _ in range(rows - rendered):
        print("\x1b[2K", file=sys.stderr)
    print("\x1b[2K", end="", file=sys.stderr)
    return rows


def interactive_console_line(deps: ConsoleControllerDependencies) -> str | None:
    if not deps.interactive_stdin():
        try:
            print("aih> ", end="", file=sys.stderr, flush=True)
            return input().strip()
        except EOFError:
            return None
    try:
        with deps.raw_terminal():
            buffer: list[str] = []
            slash_mode = False
            selected = 0
            rendered_lines = render_console_prompt(buffer, slash_mode, selected, 0)
            while True:
                key = deps.read_key()
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
                        rendered_lines = render_console_prompt(buffer, slash_mode, selected, rendered_lines)
                    continue
                if key == "down" and slash_mode:
                    suggestions = suggest_console_actions("".join(buffer)[1:])
                    if suggestions:
                        selected = (selected + 1) % len(suggestions)
                        rendered_lines = render_console_prompt(buffer, slash_mode, selected, rendered_lines)
                    continue
                if key == "escape":
                    if slash_mode:
                        buffer.clear()
                        slash_mode = False
                        selected = 0
                        rendered_lines = render_console_prompt(buffer, slash_mode, selected, rendered_lines)
                    continue
                if key in {"left", "right", "home", "end", "delete", "unknown"}:
                    continue
                if key in {"\x7f", "\b"}:
                    if buffer:
                        buffer.pop()
                        if not buffer:
                            slash_mode = False
                        selected = 0
                        rendered_lines = render_console_prompt(buffer, slash_mode, selected, rendered_lines)
                    continue
                if len(key) == 1 and key.isprintable():
                    if not buffer and key == "/":
                        slash_mode = True
                    buffer.append(key)
                    selected = 0
                    rendered_lines = render_console_prompt(buffer, slash_mode, selected, rendered_lines)
                    continue
    except (OSError, termios.error):
        try:
            print("aih> ", end="", file=sys.stderr, flush=True)
            return input().strip()
        except EOFError:
            return None
