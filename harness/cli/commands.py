"""Pure non-interactive CLI command dispatch for AI Harness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .backend_client import BackendClient, ResumeBackendRequest, StartBackendRequest
from .bootstrap import ACTIONS, RUNNER, _default_provider, _parser
from .runtime import _find_run, _run

BUNDLE_ACTIONS = {"sdd", "explore", "proposal", "spec", "design", "tasks", "tdd"}
SOURCE_BUNDLES = {"proposal", "spec", "design", "tasks", "tdd"}


def _backend_client(namespace: argparse.Namespace) -> BackendClient:
    def run_backend(args: list[str]) -> int:
        return _run(args, verbose=namespace.verbose, dry_run=namespace.dry_run)

    return BackendClient(namespace.cwd.resolve(), run_backend)


def _run_backend(namespace: argparse.Namespace, args: list[str], *, request: str | None = None) -> int:
    return _run(args, request=request, verbose=namespace.verbose, dry_run=namespace.dry_run)


def _request_from_input(namespace: argparse.Namespace, prompt_args: list[str], request_override: str | None) -> tuple[int | None, str | None]:
    if namespace.prompt_file is not None:
        if prompt_args or request_override is not None:
            print("error: --file cannot be combined with an inline request", file=sys.stderr)
            return 2, None
        return None, None
    request = request_override if request_override is not None else " ".join(prompt_args).strip()
    if not request and not sys.stdin.isatty():
        request = sys.stdin.read().strip()
    if not request:
        print("error: a request is required; use aihui for the interactive console", file=sys.stderr)
        return 2, None
    return None, request


def _start(
    namespace: argparse.Namespace,
    prompt_args: list[str],
    *,
    request_override: str | None = None,
    route: str | None = None,
    flow: str | None = None,
    source_run: str | None = None,
) -> int:
    code, request = _request_from_input(namespace, prompt_args, request_override)
    if code is not None:
        return code
    if route is None and flow is not None:
        route = "code"
    branch = getattr(namespace, "branch", None) or "current"
    backend = _backend_client(namespace).start_args(
        StartBackendRequest(
            provider=_default_provider(namespace.provider),
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
    return _run_backend(namespace, backend, request=request)


def _bundle(namespace: argparse.Namespace, action: str, args: list[str]) -> int:
    source_run: str | None = None
    prompt_args = args
    if action in SOURCE_BUNDLES:
        if args[:1] == ["--from-run"] and len(args) > 1:
            source_run = args[1]
            prompt_args = args[2:]
        elif args and not args[0].startswith("--"):
            source_run = args[0]
            prompt_args = args[1:]
        if source_run and not prompt_args:
            return _start(namespace, [], request_override=f"Run {action} bundle from {source_run}", flow=action, source_run=source_run)
    return _start(namespace, prompt_args, flow=action, source_run=source_run)


def _parse_resume_action_args(args: list[str]) -> tuple[str | None, str | None, str | None]:
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
    return run_id, answer, selected_option


def _resume(
    namespace: argparse.Namespace,
    run_id: str | None,
    *,
    answer: str | None = None,
    selected_option: str | None = None,
) -> int:
    if answer is not None and selected_option is not None:
        raise ValueError("resume accepts only one of --answer or --selected-option")
    selected_run = _find_run(namespace.cwd.resolve(), run_id)
    if selected_run is None:
        if run_id:
            print(f"error: no unfinished run found for {run_id}", file=sys.stderr)
        else:
            print("error: no unfinished run found", file=sys.stderr)
        return 1
    _, state = selected_run
    actual_run_id = str(state["run_id"])
    model = getattr(namespace, "model", None) or state.get("selected_model") or None
    backend = _backend_client(namespace).resume_args(
        ResumeBackendRequest(
            provider=_default_provider(namespace.provider),
            run_id=actual_run_id,
            model=model,
            reasoning_effort=getattr(namespace, "reasoning_effort", None),
            github_ci_mode=getattr(namespace, "github_ci_mode", None),
            answer=answer,
            selected_option=selected_option,
        )
    )
    return _run_backend(namespace, backend)


def _archive(namespace: argparse.Namespace, run_id: str | None) -> int:
    if not run_id:
        selected = _find_run(namespace.cwd.resolve(), None)
        if selected is None:
            print("error: no unfinished run found", file=sys.stderr)
            return 1
        run_id = str(selected[1]["run_id"])
    return _backend_client(namespace).archive(run_id)


def _install_ci(namespace: argparse.Namespace, args: list[str]) -> int:
    force = "--force" in args
    targets = [item for item in args if item != "--force"]
    if len(targets) > 1:
        print("error: install-ci accepts at most one target", file=sys.stderr)
        return 2
    return _backend_client(namespace).install_ci(target=targets[0] if targets else None, force=force)


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


def _install_packages(namespace: argparse.Namespace, args: list[str]) -> int:
    optionals, all_optional, dry_install = _package_install_args(args)
    return _backend_client(namespace).install_packages(optionals=optionals, all_optional=all_optional, dry_install=dry_install)


def _artifacts(namespace: argparse.Namespace, args: list[str]) -> int:
    if len(args) != 1:
        print("error: artifacts requires a run id", file=sys.stderr)
        return 2
    root = namespace.cwd.resolve() / ".ai-harness" / "artifacts" / "runs" / args[0]
    if not root.is_dir():
        print(f"error: run not found: {args[0]}", file=sys.stderr)
        return 1
    for item in sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()):
        print(item)
    return 0


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
            run_id, answer, selected_option = _parse_resume_action_args(args)
            return _resume(namespace, run_id, answer=answer, selected_option=selected_option)
        if action == "archive":
            return _archive(namespace, args[0] if args else None)
        if action == "install-ci":
            return _install_ci(namespace, args)
        if action == "install-packages":
            return _install_packages(namespace, args)
        if action == "artifacts":
            return _artifacts(namespace, args)
        if action in BUNDLE_ACTIONS:
            return _bundle(namespace, action, args)
        if action == "raw":
            raw = args[1:] if args[:1] == ["--"] else args
            return _backend_client(namespace).raw(raw)
        return _start(namespace, args)
    except KeyboardInterrupt:
        print("\nPrompt cancelled.", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
