"""Provider model choices for launcher prompts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ModelChoice:
    label: str
    value: str


CLAUDE_FALLBACK_MODELS = (
    ModelChoice("Sonnet", "sonnet"),
    ModelChoice("Opus", "opus"),
    ModelChoice("Haiku", "haiku"),
    ModelChoice("Fable", "fable"),
)


def _choice_env(provider: str) -> str:
    return f"AI_HARNESS_{provider.upper()}_MODEL_CHOICES"


def _env_model_choices(provider: str, environment: Mapping[str, str]) -> list[ModelChoice]:
    raw = environment.get(_choice_env(provider), "")
    choices: list[ModelChoice] = []
    for item in raw.split(","):
        value = item.strip()
        if value:
            choices.append(ModelChoice(value, value))
    return choices


def _codex_catalog_choices() -> list[ModelChoice]:
    if shutil.which("codex") is None:
        return []
    try:
        completed = subprocess.run(
            ["codex", "debug", "models", "--bundled"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    models = data.get("models")
    if not isinstance(models, list):
        return []
    choices: list[ModelChoice] = []
    for item in models:
        if not isinstance(item, dict) or item.get("visibility") != "list":
            continue
        slug = item.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            continue
        display = item.get("display_name")
        label = display if isinstance(display, str) and display.strip() else slug
        choices.append(ModelChoice(label.strip(), slug.strip()))
    return choices


def model_choices(provider: str, environment: Mapping[str, str] | None = None) -> list[ModelChoice]:
    env = os.environ if environment is None else environment
    normalized = provider.strip().lower()
    explicit = _env_model_choices(normalized, env)
    if explicit:
        return explicit
    if normalized == "codex":
        return _codex_catalog_choices()
    if normalized == "claude":
        return list(CLAUDE_FALLBACK_MODELS)
    return []
