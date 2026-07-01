"""Interactive command frontend for AI Harness UI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bootstrap import RUNNER, _parser
from .console.interpreter import ConsoleInterpreter, LauncherExit, run_ui


def _interpreter(namespace: argparse.Namespace) -> ConsoleInterpreter:
    return ConsoleInterpreter(namespace)


def _backend_client(namespace: argparse.Namespace):
    return _interpreter(namespace).backend_client()


def _controller_dependencies():
    namespace = argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=True)
    return _interpreter(namespace).controller_dependencies()


def _job_runner(namespace: argparse.Namespace):
    return _interpreter(namespace).job_runner()


def _console_session(namespace: argparse.Namespace):
    return _interpreter(namespace).console_session()


def _controller(namespace: argparse.Namespace):
    return _interpreter(namespace).controller()


def _waiting_run_ids(repository):
    namespace = argparse.Namespace(cwd=Path(repository), provider=None, verbose=False, dry_run=False)
    return _interpreter(namespace).waiting_run_ids()


def _run_and_follow_decisions(namespace: argparse.Namespace, args: list[str], *, request: str | None = None) -> int:
    return _interpreter(namespace).run_and_follow_decisions(args, request=request)


def _follow_waiting_decisions(namespace: argparse.Namespace, code: int, *, run_id: str | None = None, previous_waiting_ids: set[str] | None = None) -> int:
    return _interpreter(namespace).follow_waiting_decisions(code, run_id=run_id, previous_waiting_ids=previous_waiting_ids)


def _has_unfinished_runs(namespace: argparse.Namespace) -> bool:
    return _interpreter(namespace).has_unfinished_runs()


def _refresh_recovery_block(namespace: argparse.Namespace) -> None:
    _interpreter(namespace).refresh_recovery_block()


def _select_run(title: str, runs: list[tuple[object, dict[str, object]]]) -> tuple[object, dict[str, object]] | None:
    namespace = argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=False)
    return _interpreter(namespace).select_run(title, runs)


def _next_flow_for_completed_run(root: object) -> str | None:
    return ConsoleInterpreter.next_flow_for_completed_run(root)


def _continue_unfinished_run(namespace: argparse.Namespace) -> int | None:
    return _interpreter(namespace).continue_unfinished_run()


def _continue_completed_run(namespace: argparse.Namespace) -> int | None:
    return _interpreter(namespace).continue_completed_run()


def _continue_run_menu(namespace: argparse.Namespace) -> int | None:
    return _interpreter(namespace).continue_run_menu()


def _startup_recovery(namespace: argparse.Namespace) -> int | None:
    return _interpreter(namespace).startup_recovery()


def _package_group_items() -> list:
    return _interpreter(argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=True)).package_group_items()


def _package_install_args(args: list[str]) -> tuple[list[str], bool, bool]:
    return _interpreter(argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=True)).package_install_args(args)


def _select_github_ci_mode(namespace: argparse.Namespace, args: list[str]) -> int:
    return _interpreter(namespace).select_github_ci_mode(args)


def _startup_ci_preflight(namespace: argparse.Namespace) -> None:
    _interpreter(namespace).startup_ci_preflight()


def _console_help() -> None:
    namespace = argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=True)
    _interpreter(namespace).console_help()


def _console_action_menu(namespace: argparse.Namespace) -> int:
    return _interpreter(namespace).console_action_menu()


def _render_console_prompt(buffer: list[str], previous_lines: int = 0) -> int:
    namespace = argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=True)
    return _interpreter(namespace).render_console_prompt(buffer, previous_lines)


def _interactive_console_line() -> str | None:
    namespace = argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=True)
    return _interpreter(namespace).interactive_console_line()


def _source_run_for_bundle(namespace: argparse.Namespace, bundle: str, args: list[str]) -> str | None:
    return _interpreter(namespace).source_run_for_bundle(bundle, args)


def _legacy_raw_tail(command: str, args: list[str], raw_line: str) -> str:
    return ConsoleInterpreter.legacy_raw_tail(command, args, raw_line)


def _dispatch_console_action(namespace: argparse.Namespace, command: str, args: list[str], raw_line: str = "") -> int:
    return _interpreter(namespace).dispatch_console_action(command, args, raw_line)


def _interactive_start_request(namespace: argparse.Namespace) -> str:
    return _interpreter(namespace).interactive_start_request()


def _console_command(namespace: argparse.Namespace, line: str) -> int:
    return _interpreter(namespace).console_command(line)


def _console_loop(namespace: argparse.Namespace) -> int:
    return _interpreter(namespace).console_loop()


def _branch_args(namespace: argparse.Namespace) -> list[str]:
    return _interpreter(namespace).branch_args()


def _select_route_for_start() -> str:
    namespace = argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=True)
    return _interpreter(namespace).select_route_for_start()


def _select_code_flow() -> str:
    namespace = argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=True)
    return _interpreter(namespace).select_code_flow()


def _prepare_start_backend(namespace: argparse.Namespace, prompt_args: list[str], **kwargs):
    return _interpreter(namespace).prepare_start_backend(prompt_args, **kwargs)


def _start(namespace: argparse.Namespace, prompt_args: list[str], **kwargs) -> int:
    return _interpreter(namespace).start(prompt_args, **kwargs)


def _start_job(namespace: argparse.Namespace, prompt_args: list[str], **kwargs) -> int:
    return _interpreter(namespace).start_job(prompt_args, **kwargs)


def _resume(namespace: argparse.Namespace, run_id: str | None, **kwargs) -> int:
    return _interpreter(namespace).resume(run_id, **kwargs)


def _parse_resume_action_args(args: list[str]) -> tuple[str | None, str | None, str | None]:
    return _interpreter(argparse.Namespace(cwd=Path.cwd(), provider=None, verbose=False, dry_run=True)).parse_resume_action_args(args)


def _archive(namespace: argparse.Namespace, run_id: str | None) -> int:
    return _interpreter(namespace).archive(run_id)


def ui_main(argv: list[str] | None = None) -> int:
    if not RUNNER.is_file():
        print(f"error: runner not found: {RUNNER}", file=sys.stderr)
        return 1
    parser = _parser(include_ui_options=True)
    namespace, rest = parser.parse_known_args(argv)
    setattr(namespace, "_interactive_ui", True)
    try:
        return run_ui(namespace, rest)
    except LauncherExit:
        return 0
    except KeyboardInterrupt:
        print("\nPrompt cancelled.", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
