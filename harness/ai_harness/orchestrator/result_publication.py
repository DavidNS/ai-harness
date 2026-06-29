"""Publication of terminal run results and user-facing RunResult values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from ..models import RunState
from ..output import RunResult
from .context import RunContext
from .lifecycle_results import completed_result, impossible_result, run_outcome, waiting_result


class ResultPublication:
    """Build terminal result artifacts and RunResult objects from run context."""

    def __init__(self, context: RunContext) -> None:
        self._ctx = context

    def finalize(self) -> None:
        state = self._ctx.state.load()
        self._ctx.artifacts.write_json(
            "result.json",
            {"run_id": state.run_id, "status": run_outcome(state, self._ctx.warnings), "warnings": self._ctx.warnings},
        )
        self._ctx.state.record_artifact("result.json", "FINALIZING")

    def snapshot_run(self, run_id: str, overrides: Mapping[str, str], artifact_names: object) -> Path:
        try:
            return self._ctx.artifacts.snapshot_run(run_id, overrides, artifact_names=artifact_names)
        except TypeError as exc:
            if "artifact_names" not in str(exc):
                raise
            return self._ctx.artifacts.snapshot_run(run_id, overrides)

    def completed(
        self,
        snapshot: Path,
        *,
        state: RunState | None = None,
        artifacts: Sequence[str] | None = None,
    ) -> RunResult:
        state = state or self._ctx.state.load()
        assert self._ctx.route and self._ctx.strategy
        return completed_result(
            state,
            self._ctx.route,
            self._ctx.strategy,
            artifacts=artifacts if artifacts is not None else tuple(self._ctx.artifacts.list()),
            snapshot=snapshot,
            warnings=self._ctx.warnings,
        )

    def waiting(self, state: RunState) -> RunResult:
        assert self._ctx.route and self._ctx.strategy and state.pending_decision is not None
        request = self._ctx.artifacts.read_json(state.pending_decision.request_artifact)
        return waiting_result(
            state,
            self._ctx.route,
            self._ctx.strategy,
            artifacts=self._ctx.artifacts.list(),
            request=request,
            warnings=self._ctx.warnings,
        )

    def impossible(self, state: RunState) -> RunResult:
        assert self._ctx.route and self._ctx.strategy
        return impossible_result(
            state,
            self._ctx.route,
            self._ctx.strategy,
            artifacts=self._ctx.artifacts.list(),
            warnings=self._ctx.warnings,
        )
