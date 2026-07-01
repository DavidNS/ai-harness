"""Effect interpreter for the interactive command frontend."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ai_harness.ci_support import ci_preflight

from ..backend_client import BackendClient, ResumeBackendRequest, StartBackendRequest
from ..bootstrap import _default_provider
from ..console_session import ConsoleSession
from ..job_runner import BackgroundJobRunner
from ..model_prompts import _prompt_for_model, _prompt_for_reasoning_effort
from ..runtime import _completed_runs, _decision_request, _find_run, _print_unfinished_runs, _run, _run_line, _run_title, _unfinished_runs
from ..ui import _interactive_request, _prepare_console_request, _prompt_for_decision
from ..ui_primitives import _LauncherExit, _MenuItem, _RawTerminal, _interactive_stdin, _line_prompt, _menu_prompt, _multi_select_prompt, _read_key

LauncherExit = _LauncherExit
from .action_plan import parse_resume_action_args
from ..console_controller import (
    ConsoleController,
    ConsoleControllerDependencies,
    interactive_console_line as _controller_interactive_console_line,
    package_group_items as _controller_package_group_items,
    package_install_args as _controller_package_install_args,
    render_console_prompt as _controller_render_console_prompt,
)


class ConsoleInterpreter:
    """Runs command-frontend effects against terminal/backend adapters."""

    def __init__(self, namespace: argparse.Namespace) -> None:
        self.namespace = namespace
        self.console_session().sync_namespace(namespace)

    def backend_client(self) -> BackendClient:
        namespace = self.namespace

        def run_backend(args: list[str]) -> int:
            return _run(args, verbose=namespace.verbose, dry_run=namespace.dry_run)

        return BackendClient(namespace.cwd.resolve(), run_backend)

    def controller_dependencies(self) -> ConsoleControllerDependencies:
        return ConsoleControllerDependencies(
            start=self.start,
            start_job=self.start_job,
            resume=self.resume_from_controller,
            archive=self.archive_from_controller,
            refresh_recovery_block=self.refresh_recovery_block_for,
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

    def job_runner(self) -> BackgroundJobRunner:
        runner = getattr(self.namespace, "_job_runner", None)
        if not isinstance(runner, BackgroundJobRunner):
            runner = BackgroundJobRunner(self.namespace.cwd.resolve())
            setattr(self.namespace, "_job_runner", runner)
        return runner

    def console_session(self) -> ConsoleSession:
        session = ConsoleSession.from_namespace(self.namespace)
        session.sync_namespace(self.namespace)
        return session

    def controller(self) -> ConsoleController:
        self.console_session()
        return ConsoleController(self.namespace, self.backend_client(), self.controller_dependencies(), self.job_runner())

    def waiting_run_ids(self) -> set[str]:
        repository = self.namespace.cwd.resolve()
        return {
            str(state.get("run_id"))
            for _, state in _unfinished_runs(repository)
            if state.get("status") == "waiting_for_user" and isinstance(state.get("run_id"), str)
        }

    def run_and_follow_decisions(self, args: list[str], *, request: str | None = None) -> int:
        interactive = bool(getattr(self.namespace, "_interactive_ui", False)) and sys.stdin.isatty()
        previous_waiting = self.waiting_run_ids() if interactive else set()
        code = _run(args, request=request, verbose=self.namespace.verbose, dry_run=self.namespace.dry_run)
        if self.namespace.dry_run or not interactive:
            return code
        return self.follow_waiting_decisions(code, previous_waiting_ids=previous_waiting)

    def follow_waiting_decisions(self, code: int, *, run_id: str | None = None, previous_waiting_ids: set[str] | None = None) -> int:
        repository = self.namespace.cwd.resolve()
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
            code = self.resume(run_id, follow_decisions=False)

    def has_unfinished_runs(self) -> bool:
        return bool(_unfinished_runs(self.namespace.cwd.resolve()))

    def refresh_recovery_block(self) -> None:
        setattr(self.namespace, "_recovery_blocked", self.has_unfinished_runs())

    def refresh_recovery_block_for(self, namespace: argparse.Namespace) -> None:
        ConsoleInterpreter(namespace).refresh_recovery_block()

    def select_run(self, title: str, runs: list[tuple[object, dict[str, object]]]) -> tuple[object, dict[str, object]] | None:
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

    @staticmethod
    def next_flow_for_completed_run(root: object) -> str | None:
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

    def continue_unfinished_run(self) -> int | None:
        selected = self.select_run("Unfinished runs", _unfinished_runs(self.namespace.cwd.resolve()))
        if selected is None:
            return None
        _, state = selected
        run_id = str(state.get("run_id"))
        return self.resume(run_id)

    def continue_completed_run(self) -> int | None:
        self.refresh_recovery_block()
        if getattr(self.namespace, "_recovery_blocked", False):
            _print_unfinished_runs(self.namespace.cwd.resolve(), heading="Unfinished runs must be resolved before continuing a completed run")
            print("Resume or archive unfinished runs before starting the next bundle from a completed run.", file=sys.stderr)
            return None
        selected = self.select_run("Completed runs", _completed_runs(self.namespace.cwd.resolve()))
        if selected is None:
            return None
        root, state = selected
        flow = self.next_flow_for_completed_run(root)
        if flow is None:
            print("Selected run has no next bundle to continue.", file=sys.stderr)
            print(f"Artifacts: {root}", file=sys.stderr)
            return None
        source_run = Path(root).name
        title = _run_title(Path(root), state)
        request = f"Continue {flow} from {source_run}: {title}"
        return self.start([], request_override=request, flow=flow, source_run=source_run)

    def continue_run_menu(self) -> int | None:
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
                result = self.continue_unfinished_run()
            else:
                result = self.continue_completed_run()
            self.refresh_recovery_block()
            if result is not None:
                return result

    def startup_recovery(self) -> int | None:
        repository = self.namespace.cwd.resolve()
        self.refresh_recovery_block()
        next_default_index: int | None = None
        while True:
            default_index = next_default_index if next_default_index is not None else (0 if getattr(self.namespace, "_recovery_blocked", False) else 1)
            next_default_index = None
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
                default_index=default_index,
            ).value
            if selected == "exit":
                raise _LauncherExit
            if selected == "show":
                self.backend_client().runs()
                continue
            if selected == "console":
                return None
            if selected == "continue":
                result = self.continue_run_menu()
                if result is not None:
                    return result
                self.refresh_recovery_block()
                continue
            if selected == "new":
                self.refresh_recovery_block()
                if getattr(self.namespace, "_recovery_blocked", False):
                    _print_unfinished_runs(repository, heading="Unfinished runs must be resolved before a new run")
                    print("Resume or archive unfinished runs before starting unrelated work.", file=sys.stderr)
                    next_default_index = 4
                    continue
                return self.dispatch_console_action("start", [], "start")

    def startup_ci_preflight(self) -> None:
        if getattr(self.namespace, "skip_warnings", False) or not getattr(self.namespace, "_interactive_ui", False) or not sys.stdin.isatty():
            return
        repository = self.namespace.cwd.resolve()
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
                code = self.dispatch_console_action("install-ci", [], "install-ci")
                if code != 0:
                    raise _LauncherExit
                if self.namespace.dry_run:
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

    def package_group_items(self) -> list[_MenuItem]:
        return _controller_package_group_items()

    def package_install_args(self, args: list[str]) -> tuple[list[str], bool, bool]:
        return _controller_package_install_args(args)

    def select_github_ci_mode(self, args: list[str]) -> int:
        return self.controller().select_github_ci_mode(args)

    def console_help(self) -> None:
        self.controller().console_help()

    def console_action_menu(self) -> int:
        return self.controller().console_action_menu()

    def render_console_prompt(self, buffer: list[str], previous_lines: int = 0) -> int:
        return _controller_render_console_prompt(buffer, previous_lines)

    def interactive_console_line(self) -> str | None:
        return _controller_interactive_console_line(self.controller_dependencies())

    def source_run_for_bundle(self, bundle: str, args: list[str]) -> str | None:
        return self.controller().source_run_for_bundle(bundle, args)

    @staticmethod
    def legacy_raw_tail(command: str, args: list[str], raw_line: str) -> str:
        raw = raw_line.strip()
        if not raw or raw == command:
            return ""
        prefix = f"{command} "
        if raw.startswith(prefix):
            return raw[len(command):].lstrip()
        return raw if args else ""

    def dispatch_console_action(self, command: str, args: list[str], raw_line: str = "") -> int:
        return self.controller().dispatch_console_action(command, args, raw_tail=self.legacy_raw_tail(command, args, raw_line))

    def interactive_start_request(self) -> str:
        return self.controller().interactive_start_request()

    def console_command(self, line: str) -> int:
        return self.controller().console_command(line)

    def console_loop(self) -> int:
        return self.controller().console_loop(lambda _namespace: self.startup_recovery())

    def branch_args(self) -> list[str]:
        selected = getattr(self.namespace, "branch", None)
        if selected in {"current", "create-from-main"}:
            return ["--branch", selected]
        if not getattr(self.namespace, "_interactive_ui", False) or not sys.stdin.isatty():
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
        setattr(self.namespace, "branch", selected)
        return ["--branch", selected]

    def select_route_for_start(self) -> str:
        return _menu_prompt(
            ["Request route"],
            [
                _MenuItem("c", "Code harness", "code", ("code",)),
                _MenuItem("n", "Non-code", "non-code", ("non_code", "non-code")),
            ],
            help_kind="console",
            default_index=0,
        ).value

    def select_code_flow(self) -> str:
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

    def prepare_start_backend(
        self,
        prompt_args: list[str],
        *,
        request_override: str | None = None,
        route: str | None = None,
        flow: str | None = None,
        source_run: str | None = None,
        allow_console_loop: bool = True,
    ) -> tuple[int | None, list[str] | None, str | None]:
        interactive = bool(getattr(self.namespace, "_interactive_ui", False)) and sys.stdin.isatty()
        provider = _default_provider(self.namespace.provider)
        request: str | None = request_override
        if self.namespace.prompt_file is not None:
            if prompt_args or request_override is not None:
                print("error: --file cannot be combined with an inline request", file=sys.stderr)
                return 2, None, None
        elif request is None:
            request = " ".join(prompt_args).strip()
            if not request and not sys.stdin.isatty():
                request = sys.stdin.read().strip()
        if self.namespace.prompt_file is None and not request:
            if source_run and flow:
                request = f"Run {flow} bundle from {source_run}"
            elif interactive and allow_console_loop:
                return self.console_loop(), None, None
            else:
                print("error: a request is required; use aihui for the interactive console", file=sys.stderr)
                return 2, None, None
        if interactive:
            self.startup_ci_preflight()
        branch_args = self.branch_args()
        branch = branch_args[1] if len(branch_args) == 2 and branch_args[0] == "--branch" else None
        if self.namespace.prompt_file is None and request and interactive:
            request = _prepare_console_request(self.namespace, request)
        if route is None and flow is not None:
            route = "code"
        if route is None and interactive:
            route = self.select_route_for_start()
        if route in {"code", None} and flow is None and interactive:
            flow = self.select_code_flow()
        if source_run is None and flow in {"proposal", "spec", "design", "tasks", "tdd"}:
            source_run = self.source_run_for_bundle(flow, [])
        backend = self.backend_client().start_args(
            StartBackendRequest(
                provider=provider,
                model=getattr(self.namespace, "model", None),
                reasoning_effort=getattr(self.namespace, "reasoning_effort", None),
                github_ci_mode=getattr(self.namespace, "github_ci_mode", None),
                branch=branch,
                route=route,
                flow=flow,
                source_run=source_run,
                prompt_file=self.namespace.prompt_file,
            )
        )
        return None, backend, request

    def start(self, namespace_or_prompt_args, prompt_args: list[str] | None = None, **kwargs) -> int:
        if isinstance(namespace_or_prompt_args, argparse.Namespace):
            return ConsoleInterpreter(namespace_or_prompt_args).start(prompt_args or [], **kwargs)
        prompt_args = namespace_or_prompt_args
        code, backend, request = self.prepare_start_backend(prompt_args, **kwargs)
        if code is not None or backend is None:
            return int(code or 0)
        return self.run_and_follow_decisions(backend, request=request)

    def start_job(self, namespace_or_prompt_args, prompt_args: list[str] | None = None, **kwargs) -> int:
        if isinstance(namespace_or_prompt_args, argparse.Namespace):
            return ConsoleInterpreter(namespace_or_prompt_args).start_job(prompt_args or [], **kwargs)
        prompt_args = namespace_or_prompt_args
        code, backend, request = self.prepare_start_backend(prompt_args, allow_console_loop=False, **kwargs)
        if code is not None or backend is None:
            return int(code or 0)
        if self.namespace.dry_run:
            return self.run_and_follow_decisions(backend, request=request)
        handle = self.job_runner().submit(backend, request=request)
        print(f"Started background job {handle.job_id}. Use attach {handle.job_id} or jobs.", file=sys.stderr)
        return 0

    def resume_from_controller(self, namespace: argparse.Namespace, run_id: str | None, **kwargs) -> int:
        return ConsoleInterpreter(namespace).resume(run_id, **kwargs)

    def archive_from_controller(self, namespace: argparse.Namespace, run_id: str | None) -> int:
        return ConsoleInterpreter(namespace).archive(run_id)

    def resume(self, run_id: str | None, *, follow_decisions: bool = True, answer: str | None = None, selected_option: str | None = None) -> int:
        repository = self.namespace.cwd.resolve()
        selected_run = _find_run(repository, run_id)
        if selected_run is None:
            if run_id:
                print(f"error: no unfinished run found for {run_id}", file=sys.stderr)
            else:
                print("error: no unfinished run found", file=sys.stderr)
            return 1
        current, state = selected_run
        actual_run_id = str(state["run_id"])
        model = getattr(self.namespace, "model", None)
        if model is None and isinstance(state, dict):
            model = state.get("selected_model") or None
        selected: str | None = selected_option
        if answer is not None and selected is not None:
            raise ValueError("resume accepts only one of --answer or --selected-option")
        if answer is None and selected is None and state.get("status") == "waiting_for_user" and getattr(self.namespace, "_interactive_ui", False) and sys.stdin.isatty():
            request = _decision_request(current, state)
            if request is not None:
                answer, selected = _prompt_for_decision(actual_run_id, request)
        backend = self.backend_client().resume_args(
            ResumeBackendRequest(
                provider=_default_provider(self.namespace.provider),
                run_id=actual_run_id,
                model=model,
                reasoning_effort=getattr(self.namespace, "reasoning_effort", None),
                github_ci_mode=getattr(self.namespace, "github_ci_mode", None),
                answer=answer,
                selected_option=selected,
            )
        )
        code = _run(backend, verbose=self.namespace.verbose, dry_run=self.namespace.dry_run)
        if follow_decisions:
            self.refresh_recovery_block()
        if follow_decisions and not self.namespace.dry_run and getattr(self.namespace, "_interactive_ui", False) and sys.stdin.isatty():
            return self.follow_waiting_decisions(code, run_id=actual_run_id)
        return code

    def parse_resume_action_args(self, args: list[str]) -> tuple[str | None, str | None, str | None]:
        return parse_resume_action_args(args)

    def archive(self, run_id: str | None) -> int:
        if not run_id:
            selected = _find_run(self.namespace.cwd.resolve(), None)
            if selected is None:
                print("error: no unfinished run found", file=sys.stderr)
                return 1
            run_id = str(selected[1]["run_id"])
        code = self.backend_client().archive(run_id)
        self.refresh_recovery_block()
        return code


def run_ui(namespace: argparse.Namespace, rest: list[str]) -> int:
    interpreter = ConsoleInterpreter(namespace)
    if rest:
        return interpreter.start(rest)
    return interpreter.console_loop()
