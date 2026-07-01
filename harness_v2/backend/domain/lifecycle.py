"""Lifecycle graph domain model for v2 runs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from harness_v2.backend.domain.errors import DomainValidationError, InvalidTransitionError


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunStrategy(StrEnum):
    SDD = "SDD"
    EXPLORER = "EXPLORER"
    EXPLORE_BUNDLE = "EXPLORE_BUNDLE"
    PROPOSAL_BUNDLE = "PROPOSAL_BUNDLE"
    SPEC_BUNDLE = "SPEC_BUNDLE"
    DESIGN_BUNDLE = "DESIGN_BUNDLE"
    TASKS_BUNDLE = "TASKS_BUNDLE"
    TDD_BUNDLE = "TDD_BUNDLE"


class PhaseName(StrEnum):
    EXPLORE_BUNDLE = "EXPLORE_BUNDLE"
    PROPOSAL_BUNDLE = "PROPOSAL_BUNDLE"
    SPEC_BUNDLE = "SPEC_BUNDLE"
    DESIGN_BUNDLE = "DESIGN_BUNDLE"
    TASKS_BUNDLE = "TASKS_BUNDLE"
    TDD_BUNDLE = "TDD_BUNDLE"
    EXPLORER_INTAKE = "EXPLORER_INTAKE"
    EXPLORER_DISCOVERY = "EXPLORER_DISCOVERY"
    EXPLORER_DECISION = "EXPLORER_DECISION"
    EXPLORER_ARTIFACT = "EXPLORER_ARTIFACT"
    EXPLORER_REVIEW = "EXPLORER_REVIEW"
    EXPLORER_DISTILL = "EXPLORER_DISTILL"


class TerminalState(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


LifecycleNode = PhaseName | TerminalState

# Stage 6 intentionally models the SDD control skeleton without knowledge
# extraction phases. Stage 9 owns knowledge lifecycle nodes and promotion.
SDD_PHASES: tuple[PhaseName, ...] = (
    PhaseName.EXPLORE_BUNDLE,
    PhaseName.PROPOSAL_BUNDLE,
    PhaseName.SPEC_BUNDLE,
    PhaseName.DESIGN_BUNDLE,
    PhaseName.TASKS_BUNDLE,
    PhaseName.TDD_BUNDLE,
)

EXPLORER_PHASES: tuple[PhaseName, ...] = (
    PhaseName.EXPLORER_INTAKE,
    PhaseName.EXPLORER_DISCOVERY,
    PhaseName.EXPLORER_DECISION,
    PhaseName.EXPLORER_ARTIFACT,
    PhaseName.EXPLORER_REVIEW,
    PhaseName.EXPLORER_DISTILL,
)

STRATEGY_GRAPHS: dict[RunStrategy, tuple[PhaseName, ...]] = {
    RunStrategy.SDD: SDD_PHASES,
    RunStrategy.EXPLORER: EXPLORER_PHASES,
    RunStrategy.EXPLORE_BUNDLE: (PhaseName.EXPLORE_BUNDLE,),
    RunStrategy.PROPOSAL_BUNDLE: (PhaseName.PROPOSAL_BUNDLE,),
    RunStrategy.SPEC_BUNDLE: (PhaseName.SPEC_BUNDLE,),
    RunStrategy.DESIGN_BUNDLE: (PhaseName.DESIGN_BUNDLE,),
    RunStrategy.TASKS_BUNDLE: (PhaseName.TASKS_BUNDLE,),
    RunStrategy.TDD_BUNDLE: (PhaseName.TDD_BUNDLE,),
}


def _coerce_node(node: LifecycleNode | str) -> LifecycleNode:
    if isinstance(node, (PhaseName, TerminalState)):
        return node
    try:
        return PhaseName(node)
    except ValueError:
        try:
            return TerminalState(node)
        except ValueError as exc:
            raise DomainValidationError(f"unknown lifecycle node: {node}") from exc


@dataclass(frozen=True, slots=True)
class LifecycleGraph:
    strategy: RunStrategy
    phases: tuple[PhaseName, ...]

    @classmethod
    def for_strategy(cls, strategy: RunStrategy | str) -> "LifecycleGraph":
        normalized = RunStrategy(strategy)
        return cls(strategy=normalized, phases=STRATEGY_GRAPHS[normalized])

    @property
    def start_phase(self) -> PhaseName:
        return self.phases[0]

    def next_after(self, current: LifecycleNode | str) -> LifecycleNode:
        node = _coerce_node(current)
        if isinstance(node, TerminalState):
            raise InvalidTransitionError(f"{node.value} is terminal")
        if node not in self.phases:
            raise InvalidTransitionError(f"{node.value} is not in {self.strategy.value} graph")
        index = self.phases.index(node)
        if index == len(self.phases) - 1:
            return TerminalState.COMPLETED
        return self.phases[index + 1]

    def can_transition(self, source: LifecycleNode | str, target: LifecycleNode | str) -> bool:
        try:
            self.validate_transition(source, target)
        except DomainValidationError:
            return False
        return True

    def validate_transition(self, source: LifecycleNode | str, target: LifecycleNode | str) -> None:
        source_node = _coerce_node(source)
        target_node = _coerce_node(target)
        if isinstance(source_node, TerminalState):
            raise InvalidTransitionError(f"{source_node.value} is terminal")
        if source_node not in self.phases:
            raise InvalidTransitionError(f"{source_node.value} is not in {self.strategy.value} graph")
        if isinstance(target_node, TerminalState) and target_node in {
            TerminalState.FAILED,
            TerminalState.CANCELLED,
        }:
            return
        expected = self.next_after(source_node)
        if target_node != expected:
            raise InvalidTransitionError(
                f"invalid transition for {self.strategy.value}: "
                f"{source_node.value} -> {target_node.value}; expected {expected.value}"
            )

    def phase_index(self, phase: PhaseName | str) -> int:
        node = _coerce_node(phase)
        if not isinstance(node, PhaseName) or node not in self.phases:
            value = node.value if isinstance(node, (PhaseName, TerminalState)) else str(node)
            raise InvalidTransitionError(f"{value} is not in {self.strategy.value} graph")
        return self.phases.index(node)

    def validate_rewind_target(self, source: PhaseName | str, target: PhaseName | str) -> None:
        source_index = self.phase_index(source)
        target_index = self.phase_index(target)
        if target_index >= source_index:
            raise InvalidTransitionError("escalation target must be earlier than the current phase")

    def completed_prefix_before(self, phase: PhaseName | str) -> tuple[PhaseName, ...]:
        return self.phases[: self.phase_index(phase)]

    def phases_from(self, phase: PhaseName | str) -> tuple[PhaseName, ...]:
        return self.phases[self.phase_index(phase) :]

    def validate_completed_prefix(self, completed: tuple[PhaseName, ...]) -> None:
        if len(completed) != len(set(completed)):
            raise DomainValidationError("completed phases must be unique")
        expected = self.phases[: len(completed)]
        if completed != expected:
            expected_values = tuple(phase.value for phase in expected)
            actual_values = tuple(phase.value for phase in completed)
            raise DomainValidationError(
                f"completed phases must be a legal prefix: expected {expected_values}, got {actual_values}"
            )
