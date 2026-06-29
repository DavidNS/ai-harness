"""Strict JSON-object extraction and one-shot structured-output correction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .base import Provider, ProviderResult


class JsonOutputError(ValueError):
    """Provider output did not contain a valid expected JSON object."""


Validator = Callable[[Mapping[str, object]], object]
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def extract_json_object(output: str) -> dict[str, object]:
    """Return the first decodable JSON object, accepting fences and prose."""
    candidates = [match.group(1).strip() for match in _FENCE.finditer(output)]
    candidates.append(output.strip())
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            direct = json.loads(candidate)
        except json.JSONDecodeError:
            direct = None
        if isinstance(direct, dict):
            return direct
        if direct is not None:
            continue
        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    raise JsonOutputError("provider output did not contain a JSON object")


@dataclass(frozen=True, slots=True)
class JsonPromptResult:
    value: object | None
    provider_results: tuple[ProviderResult, ...]
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.value is not None


def run_json_prompt(
    provider: Provider,
    prompt: str,
    *,
    cwd: Path,
    validator: Validator,
    permissions: Mapping[str, object] | None = None,
    correction_prompt: str | None = None,
) -> JsonPromptResult:
    """Run a JSON request, allowing exactly one correction after invalid output."""
    results: list[ProviderResult] = []
    current_prompt = prompt
    last_error = "invalid structured provider output"
    for attempt in range(2):
        result = provider.run_prompt(current_prompt, cwd=cwd, permissions=permissions)
        results.append(result)
        if result.succeeded:
            try:
                return JsonPromptResult(
                    validator(extract_json_object(result.stdout)), tuple(results)
                )
            except (JsonOutputError, TypeError, ValueError, KeyError) as exc:
                last_error = str(exc)
        else:
            last_error = "provider timed out" if result.timed_out else "provider command failed"

        if attempt == 0:
            instruction = correction_prompt or (
                "Return only one valid JSON object matching the requested contract."
            )
            current_prompt = f"{instruction}\n\nOriginal request:\n{prompt}"
    return JsonPromptResult(None, tuple(results), last_error)
