"""RoutingCoordinator — resolve pending routing choice and persist route state.

Three-branch logic: pause-for-user (raises ControlFlowSignal), no-op (returns None),
and apply-choice (returns RoutingResolution). Previously _persist_route and its
_routing_* helpers on the Orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..explorer_gate import ExplorerGateDecision, classify_explorer_gate
from ..control_outputs import ControlFlowSignal, DecisionOption, DecisionRequest
from ..models import Complexity, Mode, Strategy
from ..route_heuristics import score_route
from ..router import RouteDecision
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from ..strategy import StrategyDecision, explorer_strategy_decision, strategy_audit
from .explorer_scope import explorer_scope_target_tokens as _explorer_scope_target_tokens


@dataclass
class RoutingResolution:
    route: RouteDecision
    strategy: StrategyDecision
    explorer_gate: ExplorerGateDecision | None


def _routing_scores(request: str) -> tuple[dict[str, int], dict[str, tuple[str, ...]], tuple[str, ...]]:
    scored = score_route(request)
    scores = {"code": scored.code_score, "non_code": scored.non_code_score}
    signals = {"code": scored.code_signals, "non_code": scored.non_code_signals}
    ranked = tuple(sorted(scores, key=lambda path: (-scores[path], path)))
    return scores, signals, ranked


class RoutingCoordinator:
    """Apply a pending routing choice and persist route.json."""

    def __init__(
        self,
        route: RouteDecision,
        strategy: StrategyDecision,
        explorer_gate: ExplorerGateDecision | None,
        state: StateStore,
        artifacts: ArtifactStore,
        target: Path,
    ) -> None:
        self._route = route
        self._strategy = strategy
        self._explorer_gate = explorer_gate
        self._state = state
        self._artifacts = artifacts
        self._target = target

    def coordinate(self) -> RoutingResolution | None:
        if self._route.source in {"cli_route", "user_decision"}:
            self._artifacts.write_json(
                "route.json",
                {
                    "mode": self._route.mode,
                    "intent": self._route.intent,
                    "confidence": self._route.confidence,
                    "source": self._route.source,
                    "matched_signals": list(self._route.matched_signals),
                    "error": self._route.error,
                },
            )
            self._state.record_artifact("route.json", "ROUTING")
            return None
        choice = self._routing_answer_choice()
        user_input = self._state.load().user_input
        explicit_route = self._route.source in {"cli", "cli_route", "user_decision"}
        requires_route_choice = (
            self._route.source == "needs_user"
            or bool(_explorer_scope_target_tokens(user_input))
            or (self._strategy.prompted and not explicit_route)
        )
        if choice is None and requires_route_choice:
            self._artifacts.write_json(
                "route.json",
                {
                    "mode": self._route.mode,
                    "intent": self._route.intent,
                    "confidence": self._route.confidence,
                    "source": self._route.source,
                    "matched_signals": list(self._route.matched_signals),
                    "error": self._route.error,
                    "pending_strategy": {
                        "strategy": self._strategy.strategy,
                        "complexity": self._strategy.complexity,
                        "score": self._strategy.score,
                        "reason": self._strategy.reason,
                        "matched_signals": list(self._strategy.matched_signals),
                        **strategy_audit(self._strategy),
                    },
                },
            )
            self._state.record_artifact("route.json", "ROUTING")
            raise ControlFlowSignal(self._routing_decision_request())
        if choice is None:
            self._artifacts.write_json(
                "route.json",
                {
                    "mode": self._route.mode,
                    "intent": self._route.intent,
                    "confidence": self._route.confidence,
                    "source": self._route.source,
                    "matched_signals": list(self._route.matched_signals),
                    "error": self._route.error,
                },
            )
            self._state.record_artifact("route.json", "ROUTING")
            return None
        if choice == "non_code":
            route = RouteDecision("non_code", "unknown", 1.0, "user_decision", self._route.matched_signals)
            strategy = StrategyDecision("NON_CODE_STUB", "LOW", 0, "User selected non-code routing", ())
            explorer_gate: ExplorerGateDecision | None = None
            self._state.update(mode=Mode.NON_CODE, strategy=Strategy.NON_CODE_STUB, complexity=Complexity.LOW)
        else:
            route_intent = (
                self._route.intent
                if self._route.intent in {"build_software", "modify_code", "debug_issue", "explorer_request"}
                else "modify_code"
            )
            route = RouteDecision("code", route_intent, 1.0, "user_decision", self._route.matched_signals)
            current = self._state.load()
            explorer_gate = self._explorer_gate
            if current.strategy is Strategy.SDD and self._explorer_gate is None:
                strategy = StrategyDecision(
                    current.strategy.value,
                    current.complexity.value,
                    self._strategy.score,
                    self._strategy.reason,
                    self._strategy.matched_signals,
                    self._strategy.recommended_strategy,
                    self._strategy.recommended_complexity,
                    self._strategy.confirmation_required,
                    self._strategy.prompted,
                    self._strategy.overridden,
                    self._strategy.selection_source,
                    self._strategy.override_text,
                )
            else:
                strategy = StrategyDecision("SDD", current.complexity.value, self._strategy.score, self._strategy.reason, self._strategy.matched_signals, "SDD", current.complexity.value, False)
                explorer_gate = classify_explorer_gate(self._state.load().user_input, repository=self._target)
            self._state.update(
                mode=Mode.CODE,
                strategy=Strategy(strategy.strategy),
                complexity=Complexity(strategy.complexity),
            )
        self._artifacts.write_json(
            "route.json",
            {
                "mode": route.mode,
                "intent": route.intent,
                "confidence": route.confidence,
                "source": route.source,
                "matched_signals": list(route.matched_signals),
                "error": route.error,
            },
        )
        self._state.record_artifact("route.json", "ROUTING")
        return RoutingResolution(route, strategy, explorer_gate)

    def _routing_answer_choice(self) -> str | None:
        for item in reversed(self._state.decision_history()):
            req = item.get("request")
            answer = item.get("answer")
            if not isinstance(req, dict) or req.get("origin_phase") != "ROUTING":
                continue
            if not isinstance(answer, dict):
                continue
            selected = answer.get("selected_option")
            if selected in {"code", "non_code"}:
                return str(selected)
            text = str(answer.get("answer", "")).casefold()
            if "non" in text and "code" in text:
                return "non_code"
            if "code" in text or "harness" in text:
                return "code"
        return None

    def _routing_decision_request(self) -> DecisionRequest:
        request = self._state.load().user_input
        scores, signals, ranked = _routing_scores(request)
        context: list[str] = ["No route will be selected automatically; the user must choose code or non-code."]
        if self._route.error:
            context.append(self._route.error)
        return DecisionRequest(
            "ROUTING",
            "User must choose whether this request enters the code harness or non-code handling",
            "Should this request run through the code harness?",
            tuple(context),
            (
                DecisionOption("code", "Code harness", "Continue into harness flow selection and code artifacts."),
                DecisionOption("non_code", "Non-code", "Use non-code handling instead of the code workflow."),
            ),
            False,
            None,
            scores,
            signals,
            ranked,
        )
