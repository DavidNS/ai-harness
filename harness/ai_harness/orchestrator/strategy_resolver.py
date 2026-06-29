"""StrategyResolver — maps explorer gate path to a StrategyDecision.

Single responsibility: given an explorer gate decision and the current run
request, choose the appropriate strategy. Previously _strategy_for_explorer_gate
and _strategy_from_user_gate on the Orchestrator.
"""
from __future__ import annotations

from dataclasses import replace

from ..explorer_gate import ExplorerGateDecision
from ..router import RouteDecision
from ..strategy import StrategyDecision, explorer_strategy_decision, select_strategy
from .explorer_scope import explorer_scope_target_tokens


class StrategyResolver:
    """Choose a StrategyDecision from an ExplorerGateDecision and request string."""

    def __init__(self, route: RouteDecision | None, warnings: list[str]) -> None:
        self._route = route
        self._warnings = warnings

    def resolve(self, request: str, gate: ExplorerGateDecision) -> StrategyDecision:
        if gate.path == "explorer":
            assert self._route is not None
            return self._from_user_gate(
                explorer_strategy_decision(
                    request,
                    tuple(dict.fromkeys((*self._route.matched_signals, *gate.matched_signals))),
                ),
                gate,
            )
        if gate.path in {"sdd_low", "sdd_medium", "sdd_high"}:
            levels = {"sdd_low": "LOW", "sdd_medium": "MEDIUM", "sdd_high": "HIGH"}
            complexity = levels[gate.path]
            recommendation = select_strategy(request)
            return self._from_user_gate(
                StrategyDecision(
                    "SDD",
                    complexity,
                    max(recommendation.score, gate.scores.get(gate.path, 1)),
                    gate.reason,
                    tuple(dict.fromkeys((*recommendation.matched_signals, *gate.matched_signals))),
                    "SDD",
                    complexity,
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
