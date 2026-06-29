"""LearningContextBuilder — assemble the learning context for knowledge synthesis.

Single responsibility: select relevant run artifacts and snapshot the repository
state into the context dictionary consumed by the knowledge_synthesis worker.

Previously _learning_context on AnalysisQualityMixin.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..contracts.limits import LEARNING as _LEARNING_LIMITS
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from .repository_scan import RepositoryScanner


def _clip_text(value: object, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[clipped {len(text) - limit} chars]"


class LearningContextBuilder:
    """Assemble the learning context dict from run artifacts and repository state."""

    def __init__(
        self,
        artifacts: ArtifactStore,
        state: StateStore,
        target: Path,
        warnings: list[str],
        task_documents: dict[str, Mapping[str, object]],
        repository_observations: list[dict[str, object]],
    ) -> None:
        self._artifacts = artifacts
        self._state = state
        self._target = target
        self._warnings = warnings
        self._task_documents = task_documents
        self._repository_observations = repository_observations

    def build(self) -> dict[str, object]:
        inventory = self._artifacts.list()
        selected: dict[str, str] = {}
        remaining = _LEARNING_LIMITS.context
        preferred = [
            "route.json", "strategy.json", "explorer_gate.json", "explorer_scope.json", "task_coverage.json",
            "published/learning-proposals.json", "published/learning-learning.json",
            "published/explorer-learning.json",
            "tasks.json", "implementation/T1/1.md", "review.md", "result.json",
        ]
        names = sorted(
            inventory,
            key=lambda name: (
                0 if name in preferred or name.startswith("attempts/") or name.startswith("implementation/") else 1,
                name,
            ),
        )
        for name in names:
            if name in {"learning.json", "learning.md"} or remaining <= 0:
                continue
            if not (
                name in {
                    "route.json", "strategy.json", "explorer_gate.json", "explorer_scope.json",
                    "task_coverage.json", "tasks.json", "review.md", "result.json",
                }
                or name.startswith("implementation/")
                or name.startswith("attempts/")
                or name.startswith("analysis/")
                or name in {"explore/outcome_bundle.json", "purpose.md", "spec.md", "design.md", "non_code.md"}
            ):
                continue
            try:
                content = self._artifacts.read(name)
            except Exception:
                continue
            clipped = _clip_text(content, min(_LEARNING_LIMITS.artifact, remaining))
            selected[name] = clipped
            remaining -= len(clipped)
        state = self._state.load()
        return {
            "run": {
                "run_id": state.run_id,
                "strategy": state.strategy.value,
                "mode": state.mode.value,
                "current_phase": state.current_phase,
                "completed_phases": state.completed_phases,
                "warnings": self._warnings,
            },
            "tasks": state.to_dict()["tasks"],
            "artifact_inventory": inventory,
            "selected_artifacts": selected,
            "repository_snapshot": RepositoryScanner(self._target, self._warnings).snapshot(
                self._task_documents, self._repository_observations
            ),
        }
