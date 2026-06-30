"""Bootstrap values and parser/provider helpers for the AI Harness launcher."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from .model_discovery import ModelChoice, model_choices
from .ui_primitives import _interactive_stdin, _line_prompt, _menu_prompt, _MenuItem

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "harness" / "run.py"
_PROVIDERS = ("codex", "claude", "local", "unknown")
ACTIONS = {"status", "runs", "resume", "archive", "install-ci", "install-packages", "raw", "sdd", "explore", "proposal", "spec", "design", "tasks", "tdd", "artifacts"}
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
        "  aih archive RUN_ID\n"
        "  aih install-packages [security github]\n"
        "  aih raw -- --cwd /repo --status"
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


def _configured_model(provider: str) -> str | None:
    explicit = os.environ.get("AI_HARNESS_MODEL", "").strip()
    if explicit:
        return explicit
    if provider == "codex":
        codex = os.environ.get("AI_HARNESS_CODEX_MODEL", "").strip()
        if codex:
            return codex
    if provider == "claude":
        claude = os.environ.get("AI_HARNESS_CLAUDE_MODEL", "").strip()
        if claude:
            return claude
    return None


def _provider_label(provider: str) -> str:
    return provider.strip().capitalize() if provider.strip() else "Provider"


def _dedupe_model_choices(choices: list[ModelChoice], configured: str | None) -> list[ModelChoice]:
    seen = {configured} if configured else set()
    result: list[ModelChoice] = []
    for choice in choices:
        if choice.value in seen:
            continue
        seen.add(choice.value)
        result.append(choice)
    return result


def _prompt_for_model(provider: str, explicit: str | None = None) -> str | None:
    if explicit is not None:
        return explicit.strip() or None
    normalized_provider = provider.strip().lower()
    if normalized_provider not in {"codex", "claude"}:
        return None
    configured = _configured_model(normalized_provider)
    if not _interactive_stdin():
        return configured
    choices = _dedupe_model_choices(model_choices(normalized_provider), configured)
    title_lines = [f"{_provider_label(normalized_provider)} model selection"]
    if configured:
        title_lines.append(f"Configured default: {configured}")
    items: list[_MenuItem] = []
    if configured:
        items.append(_MenuItem("1", f"Use configured model [{configured}]", configured, (configured,)))
    items.append(_MenuItem(str(len(items) + 1), "Use provider default", "", ("default",)))
    for choice in choices:
        items.append(_MenuItem(str(len(items) + 1), choice.label, choice.value, (choice.value,)))
    items.append(_MenuItem(str(len(items) + 1), "Enter custom model", "__custom__", ("custom",)))
    selected = _menu_prompt(title_lines, items, help_kind="model", default_index=0 if configured else 0)
    if selected.value == "__custom__":
        value = _line_prompt("Model: ", help_kind="model")
        return value.strip() or None
    return selected.value or None


def _configured_reasoning_effort() -> str | None:
    value = os.environ.get("AI_HARNESS_CODEX_REASONING_EFFORT", "").strip()
    return value if value in CODEX_REASONING_EFFORTS else None


def _prompt_for_reasoning_effort(provider: str, explicit: str | None = None) -> str | None:
    if explicit is not None:
        return explicit.strip() or None
    if provider.strip().lower() != "codex":
        return None
    configured = _configured_reasoning_effort()
    if not _interactive_stdin():
        return configured
    title_lines = ["Codex reasoning effort"]
    if configured:
        title_lines.append(f"Configured default: {configured}")
    items: list[_MenuItem] = []
    if configured:
        items.append(_MenuItem("1", f"Use configured effort [{configured}]", configured, (configured,)))
    items.append(_MenuItem(str(len(items) + 1), "Use provider default", "", ("default",)))
    labels = {
        "low": "Low",
        "medium": "Medium",
        "high": "High",
        "xhigh": "Extra high",
    }
    for effort in CODEX_REASONING_EFFORTS:
        if effort == configured:
            continue
        items.append(_MenuItem(str(len(items) + 1), labels[effort], effort, (effort,)))
    selected = _menu_prompt(title_lines, items, help_kind="model", default_index=0 if configured else 0)
    return selected.value or None
