"""Bundle and executable phase declarations for v2 runs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from harness_v2.backend.domain.errors import DomainValidationError


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BundleName(StrEnum):
    SDD_BUNDLE = "SDD_BUNDLE"
    EXPLORE_BUNDLE = "EXPLORE_BUNDLE"
    KNOWLEDGE_EXTRACT_EXPLORE = "KNOWLEDGE_EXTRACT_EXPLORE"
    PROPOSAL_BUNDLE = "PROPOSAL_BUNDLE"
    SPEC_BUNDLE = "SPEC_BUNDLE"
    DESIGN_BUNDLE = "DESIGN_BUNDLE"
    TASKS_BUNDLE = "TASKS_BUNDLE"
    TDD_BUNDLE = "TDD_BUNDLE"
    KNOWLEDGE_EXTRACT_TDD = "KNOWLEDGE_EXTRACT_TDD"


class PhaseName(StrEnum):
    EXPLORE_REQUEST_UNDERSTANDING = "EXPLORE_REQUEST_UNDERSTANDING"
    EXPLORE_CONTEXT_PACK = "EXPLORE_CONTEXT_PACK"
    EXPLORE_EVIDENCE_DIGEST = "EXPLORE_EVIDENCE_DIGEST"
    EXPLORE_EXPLORATION_MAP = "EXPLORE_EXPLORATION_MAP"
    EXPLORE_OUTCOME_SYNTHESIS = "EXPLORE_OUTCOME_SYNTHESIS"
    EXPLORE_HANDOFF = "EXPLORE_HANDOFF"
    KNOWLEDGE_EXTRACT_SYNTHESIS = "KNOWLEDGE_EXTRACT_SYNTHESIS"
    KNOWLEDGE_EXTRACT_PATCH = "KNOWLEDGE_EXTRACT_PATCH"
    PROPOSAL_DRAFT = "PROPOSAL_DRAFT"
    VALIDATE_JSON = "VALIDATE_JSON"
    PROPOSAL_HANDOFF = "PROPOSAL_HANDOFF"
    SPEC_DRAFT = "SPEC_DRAFT"
    SPEC_HANDOFF = "SPEC_HANDOFF"
    DESIGN_DRAFT = "DESIGN_DRAFT"
    DESIGN_HANDOFF = "DESIGN_HANDOFF"
    TASKS_DRAFT = "TASKS_DRAFT"
    TASKS_HANDOFF = "TASKS_HANDOFF"
    TDD_EXECUTE = "TDD_EXECUTE"
    TDD_HANDOFF = "TDD_HANDOFF"


class ExecutorKind(StrEnum):
    AI_WORKER = "AI_WORKER"
    DETERMINISTIC_FUNCTION = "DETERMINISTIC_FUNCTION"


class TerminalState(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class BundleRef:
    name: BundleName

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", BundleName(self.name))


@dataclass(frozen=True, slots=True)
class PhaseRef:
    name: PhaseName

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", PhaseName(self.name))


BundleChild = BundleRef | PhaseRef


@dataclass(frozen=True, slots=True)
class PhaseSpec:
    name: PhaseName
    executor: ExecutorKind
    task_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", PhaseName(self.name))
        object.__setattr__(self, "executor", ExecutorKind(self.executor))
        if self.executor is ExecutorKind.AI_WORKER and not self.task_id:
            raise DomainValidationError("AI worker phases require task_id")
        if self.executor is ExecutorKind.DETERMINISTIC_FUNCTION and self.task_id is not None:
            raise DomainValidationError("deterministic function phases must not declare task_id")


@dataclass(frozen=True, slots=True)
class BundleSpec:
    name: BundleName
    children: tuple[BundleChild, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", BundleName(self.name))
        object.__setattr__(self, "children", tuple(self.children))
        if not self.children:
            raise DomainValidationError("bundle specs require children")


@dataclass(frozen=True, slots=True)
class ExecutableStep:
    step_id: str
    step_index: int
    root_bundle: BundleName
    bundle_path: tuple[BundleName, ...]
    bundle_name: BundleName
    phase: PhaseSpec

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", str(self.step_id))
        object.__setattr__(self, "step_index", int(self.step_index))
        object.__setattr__(self, "root_bundle", BundleName(self.root_bundle))
        object.__setattr__(self, "bundle_path", tuple(BundleName(bundle) for bundle in self.bundle_path))
        object.__setattr__(self, "bundle_name", BundleName(self.bundle_name))
        object.__setattr__(self, "phase", PhaseSpec(self.phase.name, self.phase.executor, self.phase.task_id))
        if self.step_index < 0:
            raise DomainValidationError("step_index must be nonnegative")
        if not self.step_id.strip():
            raise DomainValidationError("step_id is required")
        if self.bundle_path and self.bundle_path[-1] is not self.bundle_name:
            raise DomainValidationError("bundle_path must end at bundle_name")

    @property
    def phase_name(self) -> PhaseName:
        return self.phase.name


PHASE_SPECS: dict[PhaseName, PhaseSpec] = {
    PhaseName.EXPLORE_REQUEST_UNDERSTANDING: PhaseSpec(PhaseName.EXPLORE_REQUEST_UNDERSTANDING, ExecutorKind.AI_WORKER, "explore_request_profile"),
    PhaseName.EXPLORE_CONTEXT_PACK: PhaseSpec(PhaseName.EXPLORE_CONTEXT_PACK, ExecutorKind.DETERMINISTIC_FUNCTION),
    PhaseName.EXPLORE_EVIDENCE_DIGEST: PhaseSpec(PhaseName.EXPLORE_EVIDENCE_DIGEST, ExecutorKind.AI_WORKER, "explore_evidence_digest"),
    PhaseName.EXPLORE_EXPLORATION_MAP: PhaseSpec(PhaseName.EXPLORE_EXPLORATION_MAP, ExecutorKind.DETERMINISTIC_FUNCTION),
    PhaseName.EXPLORE_OUTCOME_SYNTHESIS: PhaseSpec(PhaseName.EXPLORE_OUTCOME_SYNTHESIS, ExecutorKind.AI_WORKER, "explore_outcome_synthesis"),
    PhaseName.EXPLORE_HANDOFF: PhaseSpec(PhaseName.EXPLORE_HANDOFF, ExecutorKind.DETERMINISTIC_FUNCTION),
    PhaseName.KNOWLEDGE_EXTRACT_SYNTHESIS: PhaseSpec(PhaseName.KNOWLEDGE_EXTRACT_SYNTHESIS, ExecutorKind.AI_WORKER, "knowledge_synthesis"),
    PhaseName.KNOWLEDGE_EXTRACT_PATCH: PhaseSpec(PhaseName.KNOWLEDGE_EXTRACT_PATCH, ExecutorKind.DETERMINISTIC_FUNCTION),
    PhaseName.PROPOSAL_DRAFT: PhaseSpec(PhaseName.PROPOSAL_DRAFT, ExecutorKind.AI_WORKER, "purpose"),
    PhaseName.VALIDATE_JSON: PhaseSpec(PhaseName.VALIDATE_JSON, ExecutorKind.DETERMINISTIC_FUNCTION),
    PhaseName.PROPOSAL_HANDOFF: PhaseSpec(PhaseName.PROPOSAL_HANDOFF, ExecutorKind.DETERMINISTIC_FUNCTION),
    PhaseName.SPEC_DRAFT: PhaseSpec(PhaseName.SPEC_DRAFT, ExecutorKind.AI_WORKER, "spec"),
    PhaseName.SPEC_HANDOFF: PhaseSpec(PhaseName.SPEC_HANDOFF, ExecutorKind.DETERMINISTIC_FUNCTION),
    PhaseName.DESIGN_DRAFT: PhaseSpec(PhaseName.DESIGN_DRAFT, ExecutorKind.AI_WORKER, "design"),
    PhaseName.DESIGN_HANDOFF: PhaseSpec(PhaseName.DESIGN_HANDOFF, ExecutorKind.DETERMINISTIC_FUNCTION),
    PhaseName.TASKS_DRAFT: PhaseSpec(PhaseName.TASKS_DRAFT, ExecutorKind.AI_WORKER, "tasks"),
    PhaseName.TASKS_HANDOFF: PhaseSpec(PhaseName.TASKS_HANDOFF, ExecutorKind.DETERMINISTIC_FUNCTION),
    PhaseName.TDD_EXECUTE: PhaseSpec(PhaseName.TDD_EXECUTE, ExecutorKind.DETERMINISTIC_FUNCTION),
    PhaseName.TDD_HANDOFF: PhaseSpec(PhaseName.TDD_HANDOFF, ExecutorKind.DETERMINISTIC_FUNCTION),
}


def phase_spec(name: PhaseName | str) -> PhaseSpec:
    return PHASE_SPECS[PhaseName(name)]


from harness_v2.backend.domain.bundles import BUNDLE_SPECS  # noqa: E402


def bundle_spec(name: BundleName | str) -> BundleSpec:
    return BUNDLE_SPECS[BundleName(name)]
