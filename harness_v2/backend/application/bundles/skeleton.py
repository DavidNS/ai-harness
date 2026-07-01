"""Minimal non-EXPLORE SDD bundle definitions for the v2 skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.bundle_orchestration import BundleContext, BundleExecutionResult
from harness_v2.backend.domain.lifecycle import PhaseName
from harness_v2.backend.domain.tasks import TaskStatus, TaskSummary


@dataclass(frozen=True, slots=True)
class ProposalBundleDefinition:
    phase: PhaseName = PhaseName.PROPOSAL_BUNDLE
    failure_code: str = "PROPOSAL_BUNDLE_FAILED"
    produced_artifacts: tuple[str, ...] = ("purpose/bundle.json", "published/proposal-handoff.json")
    produced_prefixes: tuple[str, ...] = ()

    def execute(self, context: BundleContext) -> BundleExecutionResult:
        run = context.run
        bundle = context.artifacts.ensure_worker_json(
            run,
            self.phase,
            "purpose",
            "purpose/bundle.json",
            {"request": run.request, "explore_bundle_view": _explore_view(context), "explorer_scope": {}},
            validate_purpose_bundle,
        )
        context.artifacts.ensure_controller_json(
            run.run_id,
            "published/proposal-handoff.json",
            lambda: _handoff("proposal", ["purpose/bundle.json"], "SPEC_BUNDLE", extra={"summary": bundle["summary"]}),
            validate_handoff,
        )
        return BundleExecutionResult()


@dataclass(frozen=True, slots=True)
class SpecBundleDefinition:
    phase: PhaseName = PhaseName.SPEC_BUNDLE
    failure_code: str = "SPEC_BUNDLE_FAILED"
    produced_artifacts: tuple[str, ...] = ("spec.md", "published/spec-handoff.json")
    produced_prefixes: tuple[str, ...] = ()

    def execute(self, context: BundleContext) -> BundleExecutionResult:
        run = context.run
        context.artifacts.ensure_worker_text(
            run,
            self.phase,
            "spec",
            "spec.md",
            {"explore_bundle_view": _explore_view(context), "purpose/bundle.json": _purpose(context), "explorer_scope": {}},
            validate_spec,
        )
        context.artifacts.ensure_controller_json(
            run.run_id,
            "published/spec-handoff.json",
            lambda: _handoff("spec", ["spec.md"], "DESIGN_BUNDLE"),
            validate_handoff,
        )
        return BundleExecutionResult()


@dataclass(frozen=True, slots=True)
class DesignBundleDefinition:
    phase: PhaseName = PhaseName.DESIGN_BUNDLE
    failure_code: str = "DESIGN_BUNDLE_FAILED"
    produced_artifacts: tuple[str, ...] = ("design.md", "published/design-handoff.json")
    produced_prefixes: tuple[str, ...] = ()

    def execute(self, context: BundleContext) -> BundleExecutionResult:
        run = context.run
        context.artifacts.ensure_worker_text(
            run,
            self.phase,
            "design",
            "design.md",
            {
                "explore_bundle_view": _explore_view(context),
                "purpose/bundle.json": _purpose(context),
                "spec.md": _required_text(context, "spec.md", validate_spec),
                "explorer_scope": {},
            },
            validate_design,
        )
        context.artifacts.ensure_controller_json(
            run.run_id,
            "published/design-handoff.json",
            lambda: _handoff("design", ["design.md"], "TASKS_BUNDLE"),
            validate_handoff,
        )
        return BundleExecutionResult()


@dataclass(frozen=True, slots=True)
class TasksBundleDefinition:
    phase: PhaseName = PhaseName.TASKS_BUNDLE
    failure_code: str = "TASKS_BUNDLE_FAILED"
    produced_artifacts: tuple[str, ...] = ("tasks.json", "published/tasks-handoff.json")
    produced_prefixes: tuple[str, ...] = ()

    def execute(self, context: BundleContext) -> BundleExecutionResult:
        run = context.run
        document = context.artifacts.ensure_worker_json(
            run,
            self.phase,
            "tasks",
            "tasks.json",
            {
                "explore_bundle_view": _explore_view(context),
                "purpose/bundle.json": _purpose(context),
                "spec.md": _required_text(context, "spec.md", validate_spec),
                "design.md": _required_text(context, "design.md", validate_design),
                "explorer_scope": {},
            },
            validate_tasks_document,
        )
        tasks = tuple(
            TaskSummary(str(item["id"]), str(item["title"]), TaskStatus.PENDING)
            for item in _object_list(document.get("tasks"), "tasks")
        )
        context.artifacts.ensure_controller_json(
            run.run_id,
            "published/tasks-handoff.json",
            lambda: _handoff("tasks", ["tasks.json"], "TDD_BUNDLE"),
            validate_handoff,
        )
        return BundleExecutionResult(tasks=tasks)


@dataclass(frozen=True, slots=True)
class TddBundleDefinition:
    phase: PhaseName = PhaseName.TDD_BUNDLE
    failure_code: str = "TDD_BUNDLE_FAILED"
    produced_artifacts: tuple[str, ...] = ("published/tdd-handoff.json",)
    produced_prefixes: tuple[str, ...] = ()

    def execute(self, context: BundleContext) -> BundleExecutionResult:
        run = context.run
        if not run.tasks:
            raise BundleValidationError("TDD_BUNDLE requires tasks from TASKS_BUNDLE")
        completed = tuple(
            task.replace(status=TaskStatus.COMPLETED)
            if hasattr(task, "replace")
            else TaskSummary(task.task_id, task.title, TaskStatus.COMPLETED)
            for task in run.tasks
        )
        context.artifacts.ensure_controller_json(
            run.run_id,
            "published/tdd-handoff.json",
            lambda: _handoff(
                "tdd",
                ["tasks.json"],
                None,
                extra={
                    "mode": "stage_6_placeholder",
                    "deferred_to_stage": "08-tdd-loop-subsystem",
                    "completed_tasks": [task.task_id for task in completed],
                },
            ),
            validate_handoff,
        )
        return BundleExecutionResult(tasks=completed)


def validate_explore_outcome_bundle(value: dict[str, Any]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_equal(value, "kind", "explore_outcome_bundle")
    _require_text(value.get("status"), "status")
    if not isinstance(value.get("normalized_request"), dict):
        raise BundleValidationError("normalized_request must be an object")
    if not isinstance(value.get("triage"), dict):
        raise BundleValidationError("triage must be an object")
    if not isinstance(value.get("exploration_map"), dict):
        raise BundleValidationError("exploration_map must be an object")
    _object_list(value.get("evidence"), "evidence")
    _object_list(value.get("entries"), "entries")


def validate_purpose_bundle(value: dict[str, Any]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_equal(value, "kind", "purpose_bundle")
    for field in ("summary", "implementation_mode", "problem", "scope", "approach"):
        _require_text(value.get(field), field)
    for field in ("selected_entries", "structural_work", "exclusions", "acceptance_outline", "evidence_refs"):
        _string_list(value.get(field), field)


def validate_spec(value: str) -> None:
    _require_heading(value, "# Spec v1")
    _require_section(value, "Behavioral Requirements")
    _require_section(value, "Acceptance Criteria")


def validate_design(value: str) -> None:
    _require_heading(value, "# Design v1")
    for section in ("Boundaries", "Invariants", "Implementation Approach", "Unit Test Design", "Integration Test Design", "End-to-End Test Design"):
        _require_section(value, section)


def validate_tasks_document(value: dict[str, Any]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_equal(value, "phase", "tasks")
    tasks = _object_list(value.get("tasks"), "tasks")
    if not tasks:
        raise BundleValidationError("tasks must not be empty")
    seen: set[str] = set()
    completed: set[str] = set()
    for task in tasks:
        task_id = _require_text(task.get("id"), "task id")
        if task_id in seen:
            raise BundleValidationError("task ids must be unique")
        seen.add(task_id)
        _require_text(task.get("title"), "task title")
        depends_on = _string_list(task.get("depends_on"), "depends_on")
        if any(dep not in completed for dep in depends_on):
            raise BundleValidationError("tasks must be dependency ordered")
        _string_list(task.get("acceptance_criteria"), "acceptance_criteria")
        _string_list(task.get("touched_paths"), "touched_paths")
        _command_list(task.get("focused_tests"), "focused_tests")
        _command_list(task.get("broader_tests"), "broader_tests")
        if task.get("status") != "pending":
            raise BundleValidationError("new tasks must be pending")
        completed.add(task_id)


def validate_handoff(value: dict[str, Any]) -> None:
    _require_equal(value, "schema_version", 1)
    _require_text(value.get("bundle"), "bundle")
    artifacts = _string_list(value.get("artifacts"), "artifacts")
    if not artifacts:
        raise BundleValidationError("handoff requires at least one artifact")
    next_bundle = value.get("next_bundle")
    if next_bundle is not None:
        _require_text(next_bundle, "next_bundle")


def _handoff(bundle: str, artifacts: list[str], next_bundle: str | None, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"schema_version": 1, "bundle": bundle, "artifacts": artifacts, "next_bundle": next_bundle, **(extra or {})}


def _explore_view(context: BundleContext) -> dict[str, Any]:
    value = context.artifacts.read_json(context.run.run_id, "explore/outcome_bundle.json")
    if value is None:
        raise BundleValidationError("required artifact explore/outcome_bundle.json is missing")
    validate_explore_outcome_bundle(value)
    return value


def _purpose(context: BundleContext) -> dict[str, Any]:
    value = context.artifacts.read_json(context.run.run_id, "purpose/bundle.json")
    if value is None:
        raise BundleValidationError("required artifact purpose/bundle.json is missing")
    validate_purpose_bundle(value)
    return value


def _required_text(context: BundleContext, artifact_id: str, validator: Any) -> str:
    value = context.artifacts.read_text(context.run.run_id, artifact_id)
    if value is None:
        raise BundleValidationError(f"required artifact {artifact_id} is missing")
    validator(value)
    return value


def _require_heading(value: str, heading: str) -> None:
    if not value.startswith(heading):
        raise BundleValidationError(f"document must start with {heading}")


def _require_section(value: str, section: str) -> None:
    marker = f"## {section}\n"
    if marker not in value:
        raise BundleValidationError(f"document missing section {section}")


def _require_equal(value: dict[str, Any], field: str, expected: object) -> None:
    if value.get(field) != expected:
        raise BundleValidationError(f"{field} must be {expected!r}")


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BundleValidationError(f"{field} is required")
    return value.strip()


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise BundleValidationError(f"{field} must be a list of nonempty strings")
    return tuple(item.strip() for item in value)


def _object_list(value: object, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise BundleValidationError(f"{field} must be a list of objects")
    return value


def _command_list(value: object, field: str) -> None:
    if not isinstance(value, list):
        raise BundleValidationError(f"{field} must be a list of commands")
    for command in value:
        if not isinstance(command, list) or any(not isinstance(part, str) or not part.strip() for part in command):
            raise BundleValidationError(f"{field} must contain commands as nonempty string lists")
