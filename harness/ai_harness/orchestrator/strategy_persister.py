"""StrategyPersister — commit the strategy decision to artifacts.

Previously _persist_strategy + _persist_explorer_gate on the Orchestrator.
Raises ControlFlowSignal when the explorer gate requires user input and no
decision answer has been recorded yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..explorer_gate import ExplorerGateDecision
from ..control_outputs import ControlFlowSignal, DecisionRequest
from ..models import Complexity, Strategy
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from ..strategy import StrategyDecision, strategy_audit


@dataclass
class StrategyPersistResult:
    explorer_gate: ExplorerGateDecision | None
    strategy: StrategyDecision


class StrategyPersister:
    """Persist the route strategy and explorer gate to artifact storage."""

    def __init__(
        self,
        explorer_gate: ExplorerGateDecision | None,
        strategy: StrategyDecision,
        state: StateStore,
        artifacts: ArtifactStore,
        *,
        answer_choice_fn: Callable[[], str | None],
        decision_request_fn: Callable[[ExplorerGateDecision], DecisionRequest],
        resolve_fn: Callable[[str, ExplorerGateDecision], StrategyDecision],
    ) -> None:
        self._explorer_gate = explorer_gate
        self._strategy = strategy
        self._state = state
        self._artifacts = artifacts
        self._answer_choice_fn = answer_choice_fn
        self._decision_request_fn = decision_request_fn
        self._resolve_fn = resolve_fn

    def persist(self) -> StrategyPersistResult | None:
        """Write strategy artifacts; return updated values if state mutated, else None.

        Raises ControlFlowSignal if gate is ask_user and no answer exists yet.
        """
        mutated = False
        if self._explorer_gate is not None and self._explorer_gate.path == "ask_user":
            choice = self._answer_choice_fn()
            if choice is None:
                self._write_explorer_gate()
                raise ControlFlowSignal(self._decision_request_fn(self._explorer_gate))
            self._explorer_gate = self._explorer_gate.with_path(
                choice,
                f"User selected {choice} at the explorer gate",
                source="user_decision",
            )
            self._strategy = self._resolve_fn(self._state.load().user_input, self._explorer_gate)
            self._state.update(
                strategy=Strategy(self._strategy.strategy),
                complexity=Complexity(self._strategy.complexity),
            )
            mutated = True
        self._write_explorer_gate()
        self._artifacts.write_json("strategy.json", {
            "strategy": self._strategy.strategy,
            "complexity": self._strategy.complexity,
            "score": self._strategy.score,
            "reason": self._strategy.reason,
            "matched_signals": list(self._strategy.matched_signals),
            **strategy_audit(self._strategy),
        })
        self._state.record_artifact("strategy.json", "SELECTING_STRATEGY")
        return StrategyPersistResult(self._explorer_gate, self._strategy) if mutated else None

    def _write_explorer_gate(self) -> None:
        if self._explorer_gate is not None:
            self._artifacts.write_json("explorer_gate.json", self._explorer_gate.to_dict())
            self._state.record_artifact("explorer_gate.json", "SELECTING_STRATEGY")
