"""Explorer phase artifact access."""

from __future__ import annotations

from ..phases import get_phase
from .context import RunContext
from .explorer_context import ExplorerContext


class ExplorerArtifacts:
    """Read and write staged explorer artifacts."""

    def __init__(self, context: RunContext) -> None:
        self._ctx = context

    def write_phase_artifact(self, name: str, output: str) -> None:
        artifact = get_phase(name).artifact
        self._ctx.artifacts.write(artifact, output)
        self._ctx.state.record_artifact(artifact, name.upper())

    def stage_artifact(self, name: str) -> str:
        return get_phase(name).artifact

    def stage_json(self, name: str) -> dict[str, object]:
        return self._ctx.artifacts.read_json(self.stage_artifact(name))

    def safe_stage_json(self, name: str) -> dict[str, object]:
        try:
            return self.stage_json(name)
        except Exception:
            return {}

    def context_from_discovery(self) -> ExplorerContext:
        return ExplorerContext.from_discovery(self.stage_json("explorer_discovery"))
