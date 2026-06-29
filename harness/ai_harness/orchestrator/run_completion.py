"""Terminal run completion transaction."""

from __future__ import annotations

import json
from typing import Protocol

from ..models import RunState
from ..output import RunResult
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from .result_publication import ResultPublication


class _CompletionHost(Protocol):
    state: StateStore
    artifacts: ArtifactStore


class RunCompletion:
    """Complete a run atomically from terminal state through publication cleanup."""

    def __init__(self, host: _CompletionHost, publication: ResultPublication) -> None:
        self._host = host
        self._publication = publication

    def complete(self, state: RunState) -> RunResult:
        terminal = self._host.state.prepare_completion()
        terminal_json = json.dumps(terminal.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        snapshot = self._publication.snapshot_run(
            state.run_id,
            {"state.json": terminal_json},
            terminal.artifacts.keys(),
        )
        self._host.state.commit_completion(terminal)
        artifacts = tuple(self._host.artifacts.list())
        result = self._publication.completed(snapshot, state=terminal, artifacts=artifacts)
        self._host.artifacts.cleanup_run_temp(state.run_id)
        self._host.artifacts.clear_live(state.run_id, "completed")
        return result
