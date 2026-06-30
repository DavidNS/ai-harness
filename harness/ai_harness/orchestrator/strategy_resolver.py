"""StrategyResolver — maps explorer gate path to a StrategyDecision.

Single responsibility: given an explorer gate decision and the current run
request, choose the appropriate strategy. Previously _strategy_for_explorer_gate
and _strategy_from_user_gate on the Orchestrator.
"""
from __future__ import annotations

from dataclasses import replace

from ..explorer_gate import ExplorerGateDecision
from ..router import RouteDecision
from ..strategy import StrategyDecision, select_strategy
from .explorer_scope import explorer_scope_target_tokens


class StrategyResolver:
    """Choose a StrategyDecision from an ExplorerGateDecision and request string."""

    def __init__(self, route: RouteDecision | None, warnings: list[str]) -> None:
        self._route = route
        self._warnings = warnings

    def resolve(self, request: str, gate: ExplorerGateDecision) -> StrategyDecision:
        bundle_paths = {
            "explore_bundle": "EXPLORE_BUNDLE",
            "proposal_bundle": "PROPOSAL_BUNDLE",
            "spec_bundle": "SPEC_BUNDLE",
            "design_bundle": "DESIGN_BUNDLE",
            "tasks_bundle": "TASKS_BUNDLE",
            "tdd_bundle": "TDD_BUNDLE",
        }
        if gate.path in bundle_paths:
            assert self._route is not None
            strategy = bundle_paths[gate.path]
            return self._from_user_gate(
                StrategyDecision(
                    strategy,
                    "HIGH",
                    max(gate.scores.get(gate.path, 1), 1),
                    f"User selected {strategy} bundle flow",
                    tuple(dict.fromkeys((*self._route.matched_signals, *gate.matched_signals))),
                    strategy,
                    "HIGH",
                    False,
                ),
                gate,
            )
        if gate.path == "sdd":
            recommendation = select_strategy(request)
            return self._from_user_gate(
                StrategyDecision(
                    "SDD",
                    "HIGH",
                    max(recommendation.score, gate.scores.get(gate.path, 1)),
                    gate.reason,
                    tuple(dict.fromkeys((*recommendation.matched_signals, *gate.matched_signals))),
                    "SDD",
                    "HIGH",
                    False,
                ),
                gate,
            )
        return select_strategy(request)

    def _from_user_gate(self, decision: StrategyDecision, gate: ExplorerGateDecision) -> StrategyDecision:
        if gate.source != "user_decision":
            return decision
        return replace(
            decision,
            prompted=True,
            overridden=False,
            selection_source="user_decision",
            override_text=gate.path,
        )
