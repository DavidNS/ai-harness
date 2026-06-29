#!/usr/bin/env python3
"""Command line entry point for the deterministic harness."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ai_harness.config import load_config
from ai_harness.ci_support import infer_ci_target, install_ci_templates, render_install_result
from ai_harness.recommended_packages import install_recommended_packages, render_package_install_result
from ai_harness.launcher.context import command_context
from ai_harness.launcher.live_runs import find_unfinished_run, unfinished_run
from ai_harness.launcher.provider_config import apply_resume_provider_config, provider_from_config
from ai_harness.launcher.recovery import archive_run, direct_decision_answer
from ai_harness.launcher.rendering import render_show_runs, render_unfinished_run
from ai_harness.launcher.status import render_status
from ai_harness.models import RunStatus
from ai_harness.orchestrator import Orchestrator
from ai_harness.output import render_result
from ai_harness.stores.artifact import ArtifactStore, cleanup_terminal_live_artifacts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AI Code Harness")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--provider", choices=("claude", "codex", "local", "unknown"))
    parser.add_argument("--prompt-file", type=Path)
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument("--resume", metavar="RUN_ID")
    recovery.add_argument("--archive", metavar="RUN_ID")
    recovery.add_argument("--show-runs", action="store_true")
    recovery.add_argument("--status", action="store_true")
    recovery.add_argument("--install-ci", action="store_true")
    recovery.add_argument("--install-packages", action="store_true")
    parser.add_argument("--ci-target", choices=("github", "gitlab", "both"))
    parser.add_argument("--package", action="append", default=[], help="optional recommended package group to include")
    parser.add_argument("--all-packages", action="store_true", help="include every optional recommended package group")
    parser.add_argument("--dry-install", action="store_true", help="print package installation command without running pip")
    parser.add_argument("--force", action="store_true", help="replace unmanaged files for commands that support it")
    parser.add_argument("--answer-file", type=Path)
    parser.add_argument("--answer")
    parser.add_argument("--selected-option")
    parser.add_argument("--model")
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh"))
    parser.add_argument("--bypass", action="store_true")
    parser.add_argument("--activated", action="store_true", help="recursive activation guard")
    return parser


def _request_from_args(args: argparse.Namespace) -> str:
    requestless = args.show_runs or args.status or args.install_ci or args.install_packages or args.resume is not None or args.archive is not None
    if requestless:
        return ""
    if args.prompt_file:
        return args.prompt_file.read_text(encoding="utf-8").strip()
    return sys.stdin.read().strip()


def _apply_cli_environment(args: argparse.Namespace, values: dict[str, str]) -> None:
    if args.provider:
        values["AI_HARNESS_PROVIDER"] = args.provider
        if args.provider in {"claude", "codex"}:
            values.setdefault("AI_HARNESS_PROVIDER_COMMAND", args.provider)
    if args.model:
        values["AI_HARNESS_MODEL"] = args.model
        values["AI_HARNESS_CODEX_MODEL"] = args.model
        values["AI_HARNESS_CLAUDE_MODEL"] = args.model
    if args.reasoning_effort:
        values["AI_HARNESS_CODEX_REASONING_EFFORT"] = args.reasoning_effort


def _decision_answer(args: argparse.Namespace, artifacts: ArtifactStore, unfinished) -> str | None:
    if (args.answer_file or args.answer or args.selected_option) and not args.resume:
        raise ValueError("decision answers require --resume")
    if args.answer_file and (args.answer or args.selected_option):
        raise ValueError("--answer-file cannot be combined with --answer or --selected-option")
    if not args.resume:
        return None
    if unfinished is None:
        raise ValueError("there is no unfinished run to resume")
    if args.answer_file:
        if unfinished.status is not RunStatus.WAITING_FOR_USER:
            raise ValueError("--answer-file can only resume a waiting run")
        return args.answer_file.read_text(encoding="utf-8")
    if args.answer or args.selected_option:
        return direct_decision_answer(artifacts, unfinished, args.answer, args.selected_option)
    return None


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    request = _request_from_args(args)
    if args.bypass:
        if not request:
            print("error: a request is required", file=sys.stderr)
            return 2
        print(request)
        return 0

    values = dict(os.environ)
    _apply_cli_environment(args, values)
    try:
        repository = args.cwd.resolve()
        if args.status:
            print(render_status(repository), end="")
            return 0
        if args.install_ci:
            target = args.ci_target or infer_ci_target(repository)
            if target is None:
                print("error: could not infer CI target; pass --ci-target github, gitlab, or both", file=sys.stderr)
                return 2
            print(render_install_result(install_ci_templates(repository, target, force=args.force)), end="")
            return 0
        if args.install_packages:
            result = install_recommended_packages(args.package, all_optional=args.all_packages, dry_run=args.dry_install)
            print(render_package_install_result(result), end="")
            return 0 if result.returncode == 0 else result.returncode
        cleanup_terminal_live_artifacts(repository)
        if args.show_runs:
            print(render_show_runs(repository), end="")
            return 0

        config = load_config(values)
        provider = provider_from_config(config, values)
        artifacts = ArtifactStore(repository, create=False)
        unfinished = None
        if args.resume:
            artifacts, unfinished = find_unfinished_run(repository, args.resume)
        elif not args.archive:
            artifacts, unfinished = unfinished_run(repository)
        if unfinished is not None and not args.resume and not args.archive:
            print(render_unfinished_run(artifacts, unfinished, repository), end="", file=sys.stderr)
            return 3
        if args.archive:
            snapshot = archive_run(repository, args.archive)
            print(f"Archived unfinished run {args.archive} at {snapshot}", file=sys.stderr)
            if not request:
                return 0

        decision_answer = _decision_answer(args, artifacts, unfinished)
        if args.resume:
            assert unfinished is not None
            request = unfinished.user_input
            apply_resume_provider_config(
                values,
                unfinished,
                explicit_provider=args.provider is not None,
                explicit_model=getattr(args, "model", None) is not None,
            )
            config = load_config(values)
            provider = provider_from_config(config, values)
            if provider is None and (unfinished.status is RunStatus.ACTIVE or decision_answer is not None):
                print(
                    "error: resume requires a configured provider command; rerun with --provider or AI_HARNESS_PROVIDER_COMMAND",
                    file=sys.stderr,
                )
                return 1
        if not request:
            print("error: a request is required", file=sys.stderr)
            return 2
        result = Orchestrator(
            repository,
            config,
            provider,
            artifacts=artifacts if args.resume else None,
            progress=lambda value: print(value, file=sys.stderr),
        ).run(
            request,
            resume_run_id=args.resume,
            decision_answer=decision_answer,
            strategy_decision=None,
        )
        print(render_result(result, command_context(repository)), end="")
        return 0
    except Exception as exc:
        print(f"error: {' '.join(str(exc).split())[:500]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
