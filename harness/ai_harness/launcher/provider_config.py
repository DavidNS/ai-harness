"""Provider configuration helpers for launcher backend runs."""

from __future__ import annotations

import shlex

from ..models import RunState
from ..providers.cli_provider import CliProvider


def provider_from_config(config, environment: dict[str, str]) -> CliProvider | None:
    if config.provider_command == (config.provider,) and config.provider in {"claude", "codex"}:
        return CliProvider.for_name(
            config.provider,
            timeout_seconds=config.timeout_seconds,
            environment=environment,
        )
    return (
        CliProvider(config.provider_command, config.timeout_seconds, environment=environment)
        if config.provider_command
        else None
    )


def apply_resume_provider_config(
    values: dict[str, str],
    state: RunState,
    *,
    explicit_provider: bool,
    explicit_model: bool,
) -> None:
    provider = state.selected_provider.strip().lower()
    configured_provider = values.get("AI_HARNESS_PROVIDER", "").strip().lower()
    if not explicit_provider and provider and provider != "unknown" and configured_provider in {"", "unknown"}:
        values["AI_HARNESS_PROVIDER"] = provider
    if not explicit_model:
        selected_model = state.selected_model.strip()
        if selected_model:
            values.setdefault("AI_HARNESS_MODEL", selected_model)
            values.setdefault("AI_HARNESS_CODEX_MODEL", selected_model)
            values.setdefault("AI_HARNESS_CLAUDE_MODEL", selected_model)
    if values.get("AI_HARNESS_PROVIDER_COMMAND", "").strip():
        return
    command = tuple(state.selected_provider_command)
    if command:
        values["AI_HARNESS_PROVIDER_COMMAND"] = shlex.join(command)
    elif provider in {"claude", "codex"}:
        values["AI_HARNESS_PROVIDER_COMMAND"] = provider
