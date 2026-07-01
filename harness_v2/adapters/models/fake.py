"""Deterministic model provider adapters for v2 tests."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic

from harness_v2.backend.ports.model_provider import ModelProviderRequest, ModelProviderResult


class FakeModelProvider:
    """Queue-backed provider that records requests and returns canned results."""

    def __init__(self, results: tuple[ModelProviderResult, ...] | list[ModelProviderResult] | None = None) -> None:
        self._results = deque(results or ())
        self.requests: list[ModelProviderRequest] = []

    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        self.requests.append(request)
        if self._results:
            return self._results.popleft()
        return ModelProviderResult(stdout=request.prompt, stderr="", exit_code=0, duration_seconds=0.0)


@dataclass(frozen=True, slots=True)
class ScriptedModelProvider:
    """Prompt-prefix scripted provider for deterministic integration tests."""

    output_limit: int = 1_000_000

    def run(self, request: ModelProviderRequest) -> ModelProviderResult:
        started = monotonic()
        limit = min(self.output_limit, request.truncation.output_bytes)
        prompt = request.prompt
        if prompt.startswith("FAIL"):
            return ModelProviderResult("", "scripted provider failure", 7, monotonic() - started)
        if prompt.startswith("TIMEOUT"):
            return ModelProviderResult("", "", None, monotonic() - started, timed_out=True)
        if prompt.startswith("MALFORMED"):
            return ModelProviderResult("not json", "", 0, monotonic() - started)
        if prompt.startswith("LARGE"):
            stdout, truncated = _truncate("x" * (limit + 100), limit)
            return ModelProviderResult(stdout, "", 0, monotonic() - started, truncated=truncated)
        stdout, truncated = _truncate(prompt, limit)
        return ModelProviderResult(stdout, "", 0, monotonic() - started, truncated=truncated)


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text.encode("utf-8")) <= limit:
        return text, False
    encoded = text.encode("utf-8")[:limit]
    return encoded.decode("utf-8", "ignore") + "\n[output truncated]", True
