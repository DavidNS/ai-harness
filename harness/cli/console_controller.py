"""Console controller effect interpreter."""

from __future__ import annotations

import argparse
import sys
import termios
from collections.abc import Callable
from dataclasses import dataclass

from ai_harness.bundle_inputs import compatible_runs
from ai_harness.recommended_packages import load_recommended_package_groups

from .backend_client import BackendClient
from .bootstrap import GITHUB_CI_MODES, _default_provider
from .console.action_plan import ActionPlan, handled_action_names, package_install_args, plan_action, plan_start_request
from .console.terminal_driver import ConsoleTerminalDriver
from .console.model import ConsoleModel
from .console.view import help_lines
from .console_actions import CONSOLE_ACTIONS, action_specs, actions_by_name
from .console_session import ConsoleSession
from .job_runner import BackgroundJobRunner
from .ui_primitives import _MenuItem


StartCallback = Callable[..., int]
StartJobCallback = Callable[..., int]
ResumeCallback = Callable[..., int]
ArchiveCallback = Callable[[argparse.Namespace, str | None], int]
RefreshCallback = Callable[[argparse.Namespace], None]
PromptModelCallback = Callable[[str], str | None]
PromptReasoningCallback = Callable[[str], str | None]
MenuPromptCallback = Callable[..., _MenuItem]
MultiSelectPromptCallback = Callable[..., list[_MenuItem]]
LinePromptCallback = Callable[..., str | None]
InteractiveRequestCallback = Callable[[], str]
ReadKeyCallback = Callable[[], str]
InteractiveStdinCallback = Callable[[], bool]
RawTerminalFactory = Callable[[], object]


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


def handled_console_action_names() -> set[str]:
    return handled_action_names()


class ConsoleController:
    def __init__(self, namespace: argparse.Namespace, backend: BackendClient, deps: ConsoleControllerDependencies, jobs: BackgroundJobRunner | None = None) -> None:
        self.namespace = namespace
        self.session = ConsoleSession.from_namespace(namespace)
        self.session.sync_namespace(self.namespace)
        self.backend = backend
        self.deps = deps
        self.jobs = jobs or BackgroundJobRunner(namespace.cwd.resolve())

    def _console_model(self) -> ConsoleModel:
        return ConsoleModel(actions=action_specs(CONSOLE_ACTIONS))

    def _refresh_recovery_block(self) -> None:
        self.deps.refresh_recovery_block(self.namespace)
        self.session.recovery_blocked = bool(getattr(self.namespace, "_recovery_blocked", False))
        self.session.sync_namespace(self.namespace)

    def console_help(self) -> None:
        for line in help_lines(self._console_model()):
            print(line, file=sys.stderr)

    def console_action_menu(self) -> int:
        return self._driver().run_once("")

    def dispatch_action(self, command: str, args: tuple[str, ...], raw_tail: str = "") -> int:
        return self.dispatch_console_action(command, args, raw_tail=raw_tail)

    def dispatch_console_action(self, command: str, args: tuple[str, ...] | list[str], raw_tail: str = "") -> int:
        canonical = self._canonical_action_name(command)
        if canonical not in handled_action_names():
            print(f"error: unknown console action: {command}", file=sys.stderr)
            return 2
        self._refresh_recovery_block()
        plan = plan_action(
            canonical,
            tuple(args),
            raw_tail=raw_tail,
            recovery_blocked=self.session.recovery_blocked,
            interactive=bool(getattr(self.namespace, "_interactive_ui", False)),
            stdin_tty=sys.stdin.isatty(),
        )
        if plan is None:
            print(f"error: unknown console action: {command}", file=sys.stderr)
            return 2
        return self._run_action_plan(plan)

    def _canonical_action_name(self, command: str) -> str:
        action = actions_by_name(CONSOLE_ACTIONS).get(command.strip().casefold())
        return action.name if action is not None else command.strip()

    def _run_action_plan(self, plan: ActionPlan) -> int:
        if plan.kind == "error":
            print(plan.message, file=sys.stderr)
            return plan.code
        if plan.kind == "exit":
            raise self.deps.launcher_exit
        if plan.kind == "status":
            return self.backend.status()
        if plan.kind == "runs":
            return self.backend.runs()
        if plan.kind == "jobs":
            return self.show_jobs()
        if plan.kind == "attach_job":
            return self.attach_job(plan.values[0] if plan.values else None)
        if plan.kind == "cancel_job":
            return self.cancel_job(plan.values[0] if plan.values else None)
        if plan.kind == "resume":
            return self.deps.resume(self.namespace, plan.target, answer=plan.answer, selected_option=plan.selected_option)
        if plan.kind == "archive":
            return self.deps.archive(self.namespace, plan.values[0] if plan.values else None)
        if plan.kind == "prompt_start_request":
            request = self.interactive_start_request()
            if not request:
                print("error: request is empty", file=sys.stderr)
                return 2
            return self.deps.start_job(self.namespace, [], request_override=request)
        if plan.kind == "start_job":
            return self.deps.start_job(self.namespace, [], request_override=plan.request, flow=plan.flow, source_run=plan.source_run)
        if plan.kind == "start_source_bundle":
            source_run = self.source_run_for_bundle(str(plan.flow), list(plan.values))
            return self.deps.start_job(self.namespace, [], request_override=plan.request, flow=plan.flow, source_run=source_run)
        if plan.kind == "prompt_artifacts_run":
            run_id = (self.deps.line_prompt("Run id: ", help_kind="console") or "").strip()
            return self._list_artifacts(run_id)
        if plan.kind == "list_artifacts":
            return self._list_artifacts(plan.values[0] if plan.values else "")
        if plan.kind == "select_ci_mode_prompt":
            return self._prompt_and_select_github_ci_mode()
        if plan.kind == "select_ci_mode":
            return self._select_github_ci_mode(str(plan.target))
        if plan.kind == "install_ci_prompt":
            target = self.deps.menu_prompt(
                ["Install CI templates"],
                [
                    _MenuItem("g", "GitHub Actions", "github", ("github",)),
                    _MenuItem("l", "GitLab CI", "gitlab", ("gitlab",)),
                    _MenuItem("b", "Both", "both", ("both",)),
                ],
                help_kind="console",
            ).value
            return self.backend.install_ci(target=target, force=plan.force)
        if plan.kind == "install_ci":
            return self.backend.install_ci(target=plan.target, force=plan.force)
        if plan.kind == "install_packages_prompt":
            selected = self.deps.multi_select_prompt(
                ["Optional recommended packages", "Required groups are always included."],
                package_group_items(),
                help_kind="multi",
            )
            return self.backend.install_packages(optionals=[item.value for item in selected], all_optional=False, dry_install=plan.dry_install)
        if plan.kind == "install_packages":
            return self.backend.install_packages(optionals=list(plan.optionals), all_optional=plan.all_optional, dry_install=plan.dry_install)
        if plan.kind == "model_prompt":
            return self._prompt_for_model_settings()
        raise RuntimeError(f"unsupported console action plan: {plan.kind}")

    def _list_artifacts(self, run_id: str) -> int:
        root = self.namespace.cwd.resolve() / ".ai-harness" / "artifacts" / "runs" / run_id
        if not root.is_dir():
            print(f"error: run not found: {run_id}", file=sys.stderr)
            return 1
        for item in sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()):
            print(item)
        return 0

    def _prompt_and_select_github_ci_mode(self) -> int:
        current = self.session.github_ci_mode or "baseline"
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
        return self._select_github_ci_mode(selected)

    def _select_github_ci_mode(self, selected: str) -> int:
        self.session.github_ci_mode = selected
        self.session.sync_namespace(self.namespace)
        print(f"Selected GitHub CI mode: {selected}", file=sys.stderr)
        return 0

    def _prompt_for_model_settings(self) -> int:
        provider = _default_provider(self.namespace.provider)
        selected = self.deps.prompt_for_model(provider)
        self.session.model = selected
        print(f"Selected model: {selected or 'provider default'}", file=sys.stderr)
        effort = self.deps.prompt_for_reasoning_effort(provider)
        if effort is not None:
            self.session.reasoning_effort = effort
            print(f"Selected reasoning effort: {effort or 'provider default'}", file=sys.stderr)
        self.session.sync_namespace(self.namespace)
        return 0

    def start_request(self, request: str) -> int:
        self._refresh_recovery_block()
        return self._run_action_plan(plan_start_request(request, recovery_blocked=self.session.recovery_blocked))

    def interactive_start_request(self) -> str:
        return self.deps.interactive_request()

    def console_command(self, line: str) -> int:
        driver = self._driver()
        return driver.run_once(line)

    def console_loop(self, startup_recovery: Callable[[argparse.Namespace], int | None]) -> int:
        driver = self._driver()
        try:
            return driver.loop(lambda: startup_recovery(self.namespace))
        except KeyboardInterrupt:
            print("\nPrompt cancelled.", file=sys.stderr)
            return 130

    def _driver(self) -> ConsoleTerminalDriver:
        model = ConsoleModel(actions=action_specs(CONSOLE_ACTIONS))
        return ConsoleTerminalDriver(
            model,
            self,
            line_reader=lambda: interactive_console_line(self.deps, model.prompt),
            menu_prompt=self.deps.menu_prompt,
            launcher_exit=self.deps.launcher_exit,
        )

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

    def select_github_ci_mode(self, args: list[str]) -> int:
        plan = plan_action(
            "ci-mode",
            tuple(args),
            interactive=bool(getattr(self.namespace, "_interactive_ui", False)),
            stdin_tty=sys.stdin.isatty(),
        )
        if plan is None:
            print("error: unknown console action: ci-mode", file=sys.stderr)
            return 2
        return self._run_action_plan(plan)

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
        if required is None or not getattr(self.namespace, "_interactive_ui", False) or not sys.stdin.isatty():
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


def render_console_prompt(buffer: list[str], previous_lines: int = 0, prompt: str = ConsoleModel().prompt) -> int:
    if previous_lines:
        print(f"\x1b[{previous_lines}F", end="", file=sys.stderr)
    print(f"\x1b[2K{prompt}{''.join(buffer)}", file=sys.stderr)
    return 1


def interactive_console_line(deps: ConsoleControllerDependencies, prompt: str = ConsoleModel().prompt) -> str | None:
    if not deps.interactive_stdin():
        try:
            print(prompt, end="", file=sys.stderr, flush=True)
            return input().strip()
        except EOFError:
            return None
    try:
        with deps.raw_terminal():
            buffer: list[str] = []
            rendered_lines = render_console_prompt(buffer, 0, prompt)
            while True:
                key = deps.read_key()
                if key == "\x04":
                    print(file=sys.stderr)
                    return None
                if key in {"\r", "\n"}:
                    print(file=sys.stderr)
                    return "".join(buffer).strip()
                if key in {"left", "right", "home", "end", "delete", "unknown", "escape", "up", "down"}:
                    continue
                if key in {"\x7f", "\b"}:
                    if buffer:
                        buffer.pop()
                        rendered_lines = render_console_prompt(buffer, rendered_lines, prompt)
                    continue
                if len(key) == 1 and key.isprintable():
                    buffer.append(key)
                    rendered_lines = render_console_prompt(buffer, rendered_lines, prompt)
                    continue
    except (OSError, termios.error):
        try:
            print(prompt, end="", file=sys.stderr, flush=True)
            return input().strip()
        except EOFError:
            return None
