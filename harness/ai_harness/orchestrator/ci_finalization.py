"""Final GitHub CI evidence gate for completed implementation runs."""

from __future__ import annotations

from pathlib import Path

from ..ci_support import record_branch_ci_artifacts
from ..config import HarnessConfig
from ..errors import HarnessError
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from .result_publication import ResultPublication


class CiFinalization:
    """Record final CI artifacts and fail completion when required branch CI is bad."""

    def __init__(
        self,
        target: Path,
        config: HarnessConfig,
        artifacts: ArtifactStore,
        state: StateStore,
        warnings: list[str],
        publication: ResultPublication,
    ) -> None:
        self._target = target
        self._config = config
        self._artifacts = artifacts
        self._state = state
        self._warnings = warnings
        self._publication = publication

    def finalize(self) -> None:
        result = record_branch_ci_artifacts(
            self._target,
            self._artifacts,
            self._state,
            github_ci_mode=self._config.github_ci_mode,
            warnings=self._warnings,
        )
        blockers = result.get("blockers", []) if isinstance(result.get("blockers"), list) else []
        if blockers:
            reason = "; ".join(str(item) for item in blockers if isinstance(item, str))
            self._state.mark_phase_failed("FINALIZING", reason)
            raise HarnessError(reason)
        self._publication.finalize()
