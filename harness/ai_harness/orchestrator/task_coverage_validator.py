"""TaskCoverageValidator — verify every artifact in the explorer scope is covered by a task.

Previously _validate_full_sdd_task_coverage on AnalysisQualityMixin.
Pure data validation followed by a single artifact write.
"""
from __future__ import annotations

from typing import Mapping

from ..errors import HarnessError
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore


class TaskCoverageValidator:
    """Validate that every analysis-scope artifact is assigned to a task or deferred."""

    def __init__(self, artifacts: ArtifactStore, state: StateStore) -> None:
        self._artifacts = artifacts
        self._state = state

    def validate(self, document: Mapping[str, object], scope: Mapping[str, object]) -> None:
        raw_artifacts = scope.get("artifacts")
        if not isinstance(raw_artifacts, list) or not raw_artifacts:
            raise HarnessError("explorer_scope has no artifacts")
        ordered_scope = [str(item.get("path")) for item in raw_artifacts if isinstance(item, Mapping) and item.get("path")]
        scope_paths = set(ordered_scope)
        if len(scope_paths) != len(ordered_scope):
            raise HarnessError("explorer_scope contains duplicate artifacts")
        tasks = document.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise HarnessError("tasks document has no tasks")
        covered: set[str] = set()
        task_sources: dict[str, list[str]] = {}
        for task in tasks:
            if not isinstance(task, Mapping):
                raise HarnessError("task has invalid shape")
            task_id = str(task.get("id", ""))
            sources = task.get("source_artifacts")
            if not isinstance(sources, list) or not sources or any(not isinstance(item, str) or not item for item in sources):
                raise HarnessError(f"full SDD task {task_id or '<unknown>'} requires source_artifacts")
            unknown = sorted(set(sources) - scope_paths)
            if unknown:
                raise HarnessError(f"task {task_id} references unknown source_artifacts: {unknown}")
            task_sources[task_id] = list(sources)
            covered.update(sources)
        deferred: dict[str, str] = {}
        raw_deferrals = document.get("deferrals")
        for deferral in (raw_deferrals if isinstance(raw_deferrals, list) else []):
            if not isinstance(deferral, Mapping):
                raise HarnessError("task deferral has invalid shape")
            source = str(deferral.get("source_artifact", ""))
            reason = str(deferral.get("reason", "")).strip()
            if source not in scope_paths:
                raise HarnessError(f"task deferral references unknown source_artifact: {source}")
            if not reason:
                raise HarnessError(f"task deferral requires a reason: {source}")
            if source in deferred:
                raise HarnessError(f"task deferral is duplicated: {source}")
            deferred[source] = reason
        missing = [source for source in ordered_scope if source not in covered and source not in deferred]
        if missing:
            raise HarnessError(f"explorer scope artifacts are not covered by tasks: {missing}")
        audit: dict[str, object] = {
            "schema_version": 1,
            "phase": "task_coverage",
            "explorer_scope_artifacts": ordered_scope,
            "covered_artifacts": [source for source in ordered_scope if source in covered],
            "deferred_artifacts": [{"source_artifact": source, "reason": deferred[source]} for source in ordered_scope if source in deferred],
            "task_source_artifacts": task_sources,
        }
        self._artifacts.write_json("task_coverage.json", audit)
        self._state.record_artifact("task_coverage.json", "TASKS")
