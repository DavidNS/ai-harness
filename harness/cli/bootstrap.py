"""Bootstrap values and parser/provider helpers for the AI Harness launcher."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from .actions import top_level_action_names

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "harness" / "run.py"
_PROVIDERS = ("codex", "claude", "local", "unknown")
ACTIONS = top_level_action_names() | {"raw"}
OPEN_STATUSES = {"active", "waiting_for_user"}
CODEX_REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
GITHUB_CI_MODES = ("off", "baseline", "branch")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Run AI Code Harness from the current repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="target repository, default: current directory")
    parser.add_argument("--provider", choices=_PROVIDERS, help="provider for live start/resume runs")
    parser.add_argument("--model", help="model for live Codex or Claude runs")
    parser.add_argument("--reasoning-effort", choices=CODEX_REASONING_EFFORTS, help="Codex reasoning effort")
    parser.add_argument("--github-ci-mode", choices=GITHUB_CI_MODES, help="GitHub CI evidence mode: off, baseline, or branch")
    parser.add_argument("--branch", choices=("current", "create-from-main"), help="git branch behavior for new runs")
    parser.add_argument("--file", dest="prompt_file", type=Path, help="read the request from a file")
    parser.add_argument("--verbose", action="store_true", help="print the delegated backend command")
    parser.add_argument("--dry-run", action="store_true", help="print the delegated command without running it")
    parser.add_argument("--skip-warnings", action="store_true", help="skip interactive startup CI warning prompts")
    parser.epilog = (
        "examples:\n"
        "  aih 'Fix the failing tests'\n"
        "  aih --file request.md\n"
        "  aih --github-ci-mode branch 'Fix the failing tests'\n"
        "  aih status\n"
        "  aih runs\n"
        "  aih resume [RUN_ID]\n"
        "  aih resume RUN_ID --answer 'Use option A'\n"
        "  aih resume RUN_ID --selected-option option-a\n"
        "  aih archive RUN_ID\n"
        "  aih install-packages [security github]\n"
        "  aih raw -- --cwd /repo --status\n"
        "  aihui"
    )
    return parser


def _default_provider(explicit: str | None) -> str:
    if explicit:
        return explicit
    configured = os.environ.get("AI_HARNESS_PROVIDER", "").strip().lower()
    if configured in _PROVIDERS:
        return configured
    for provider in ("codex", "claude"):
        if shutil.which(provider):
            return provider
    return "unknown"
