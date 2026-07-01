"""Interactive model and reasoning-effort prompts for the UI frontend."""

from __future__ import annotations

import os

from .bootstrap import CODEX_REASONING_EFFORTS
from .model_discovery import ModelChoice, model_choices
from .ui_primitives import _interactive_stdin, _line_prompt, _menu_prompt, _MenuItem


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
    labels = {"low": "Low", "medium": "Medium", "high": "High", "xhigh": "Extra high"}
    for effort in CODEX_REASONING_EFFORTS:
        if effort == configured:
            continue
        items.append(_MenuItem(str(len(items) + 1), labels[effort], effort, (effort,)))
    selected = _menu_prompt(title_lines, items, help_kind="model", default_index=0 if configured else 0)
    return selected.value or None
