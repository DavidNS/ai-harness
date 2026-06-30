"""Structured run lookup API for launcher UI code."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime import _completed_runs, _decision_request, _find_run, _unfinished_runs


@dataclass(frozen=True, slots=True)
class RunRef:
    root: Path
    state: dict[str, Any]

    @property
    def run_id(self) -> str:
        return str(self.state.get("run_id") or self.root.name)

    @property
    def status(self) -> str:
        return str(self.state.get("status") or "unknown")


class RunIndex:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()

    def unfinished(self) -> list[RunRef]:
        return [RunRef(Path(root), dict(state)) for root, state in _unfinished_runs(self.repository)]

    def completed(self) -> list[RunRef]:
        return [RunRef(Path(root), dict(state)) for root, state in _completed_runs(self.repository)]

    def find_unfinished(self, run_id: str | None) -> RunRef | None:
        selected = _find_run(self.repository, run_id)
        if selected is None:
            return None
        root, state = selected
        return RunRef(Path(root), dict(state))

    def waiting(self, *, exclude_ids: set[str] | None = None, run_id: str | None = None) -> list[RunRef]:
        excluded = exclude_ids or set()
        result = [item for item in self.unfinished() if item.status == "waiting_for_user"]
        if run_id is not None:
            result = [item for item in result if item.run_id == run_id]
        if excluded:
            result = [item for item in result if item.run_id not in excluded]
        return result

    def decision_request(self, ref: RunRef) -> dict[str, Any] | None:
        return _decision_request(ref.root, ref.state)
