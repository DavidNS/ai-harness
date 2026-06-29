"""ResumeContextLoader — reconstruct run context from persisted artifacts.

Single responsibility: read route.json / strategy.json / explorer_gate.json and
build the typed objects needed to continue an interrupted run. Previously
_hydrate_resume_context on the Orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..explorer_gate import ExplorerGateDecision
from ..models import RunState
from ..router import RouteDecision
from ..stores.artifact import ArtifactStore
from ..strategy import StrategyDecision


@dataclass
class ResumeContext:
    route: RouteDecision
    strategy: StrategyDecision
    explorer_gate: ExplorerGateDecision | None


class ResumeContextLoader:
    """Load and reconstruct persisted routing state for a resumed run."""

    def __init__(self, artifacts: ArtifactStore) -> None:
        self._artifacts = artifacts

    def load(self, state: RunState) -> ResumeContext:
        route = self._artifacts.read_json("route.json") if self._artifacts.exists("route.json") else {}
        strategy = self._artifacts.read_json("strategy.json") if self._artifacts.exists("strategy.json") else {}
        if not strategy and isinstance(route.get("pending_strategy"), dict):
            strategy = dict(route["pending_strategy"])
        explorer_gate = self._load_explorer_gate()
        resolved_route = RouteDecision(
            state.mode.value,
            state.intent,
            float(route.get("confidence", 0)),
            str(route.get("source", "persisted")),
            tuple(route.get("matched_signals", ())),
            route.get("error"),
        )
        resolved_strategy = StrategyDecision(
            state.strategy.value,
            state.complexity.value,
            int(strategy.get("score", 0)),
            str(strategy.get("reason", "Persisted strategy")),
            tuple(strategy.get("matched_signals", ())),
            strategy.get("recommended_strategy"),
            strategy.get("recommended_complexity"),
            bool(strategy.get("confirmation_required", False)),
            bool(strategy.get("prompted", False)),
            bool(strategy.get("overridden", False)),
            str(strategy.get("selection_source", "persisted")),
            strategy.get("override_text"),
        )
        return ResumeContext(resolved_route, resolved_strategy, explorer_gate)

    def _load_explorer_gate(self) -> ExplorerGateDecision | None:
        gate = self._artifacts.read_json("explorer_gate.json") if self._artifacts.exists("explorer_gate.json") else None
        if not isinstance(gate, dict) or not gate:
            return None
        raw_score_signals = gate.get("score_signals", {})
        score_signals = (
            {str(key): tuple(value) for key, value in raw_score_signals.items()}
            if isinstance(raw_score_signals, dict) else {}
        )
        raw_scores = gate.get("scores", {})
        scores = (
            {str(key): int(value) for key, value in raw_scores.items()}
            if isinstance(raw_scores, dict) else {}
        )
        return ExplorerGateDecision(
            str(gate.get("path", "")),
            str(gate.get("reason", "Persisted explorer gate")),
            tuple(gate.get("matched_signals", ())),
            gate.get("required_artifact"),
            gate.get("supplied_artifact"),
            str(gate.get("source", "heuristic")),
            int(gate.get("classifier_version", 1)),
            scores,
            score_signals,
        )
