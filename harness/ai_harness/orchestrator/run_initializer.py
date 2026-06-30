"""RunInitializer — set up state, route, and strategy for a new run.

Previously _initialize on the Orchestrator plus the module-level
_routing_permissions helper. Zero mixin/cross-component coupling;
all deps are constructor-injected.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..explorer_gate import ExplorerGateDecision, classify_explorer_gate
from ..config import HarnessConfig
from ..ci_support import record_ci_and_git_artifacts
from ..bundle_inputs import import_source_run_artifacts
from ..models import Complexity, Mode, RunState, RunStatus, Strategy
from ..providers.base import Provider
from ..router import RouteDecision, route_request
from ..run_identity import new_run_id
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from ..strategy import StrategyDecision, explorer_strategy_decision, strategy_audit
from ..pipeline.state_machine import graph_for


def _title_from_request(request: str) -> str:
    for line in request.splitlines():
        title = " ".join(line.strip().split())
        if title:
            return title[:120]
    return "Untitled harness run"


def _routing_permissions(timeout_seconds: float) -> dict[str, object]:
    return {
        "paths": [{"pattern": "**", "mode": "read"}],
        "commands": [],
        "skills": [],
        "mcp_tools": [],
        "timeout_seconds": max(1, int(timeout_seconds)),
        "output_bytes": 1_000_000,
    }


@dataclass
class InitResult:
    route: RouteDecision
    strategy: StrategyDecision
    explorer_gate: ExplorerGateDecision | None
    artifacts: ArtifactStore
    state: StateStore
    run_state: RunState


class RunInitializer:
    """Initialize a new run: create stores, route the request, resolve strategy."""

    def __init__(
        self,
        target: Path,
        provider: Provider,
        config: HarnessConfig,
        *,
        external_runtime: bool,
        artifacts: ArtifactStore,
        state: StateStore,
        resolve_fn: Callable[[str, ExplorerGateDecision], StrategyDecision],
        warnings: list[str],
        source_run: str | None = None,
    ) -> None:
        self._target = target
        self._provider = provider
        self._config = config
        self._external_runtime = external_runtime
        self._artifacts = artifacts
        self._state = state
        self._resolve_fn = resolve_fn
        self._warnings = warnings
        self._source_run = source_run

    def initialize(
        self,
        request: str,
        *,
        route_decision: RouteDecision | None = None,
        strategy_decision: StrategyDecision | None = None,
    ) -> InitResult:
        run_id = new_run_id()
        if not self._external_runtime:
            self._artifacts = ArtifactStore.for_run(self._target, run_id)
            self._state = StateStore(self._target, self._artifacts)
        self._artifacts.write_json("run-title.json", {
            "schema_version": 1,
            "title": _title_from_request(request),
            "source": "prompt_first_line",
        })
        route = route_decision or route_request(
            request,
            provider=self._provider,
            cwd=self._target,
            permissions=_routing_permissions(self._config.timeout_seconds),
        )
        explorer_gate: ExplorerGateDecision | None = None
        if strategy_decision is not None:
            strategy = strategy_decision
        elif route.source == "needs_user":
            strategy = explorer_strategy_decision(request, route.matched_signals)
        elif route.mode == "non_code":
            strategy = StrategyDecision("NON_CODE_STUB", "LOW", 0, "Non-code requests use the v1 stub", ())
        else:
            explorer_gate = classify_explorer_gate(request, repository=self._target)
            if explorer_gate.path == "ask_user":
                strategy = explorer_strategy_decision(request, explorer_gate.matched_signals)
            else:
                strategy = self._resolve_fn(request, explorer_gate)
        selected_strategy = Strategy(strategy.strategy)
        graph = graph_for(selected_strategy, strategy.complexity)
        current_phase = graph[0] if graph else "COMPLETED"
        status = RunStatus.ACTIVE
        run_state = RunState(
            run_id, request, current_phase,
            selected_strategy, Mode(route.mode), route.intent,
            Complexity(strategy.complexity),
            self._config.provider, tuple(self._config.provider_command), self._config.model,
            status=status,
        )
        self._state.save(run_state)
        self._state.record_artifact("run-title.json", current_phase)
        self._artifacts.write_json("route.json", {
            "mode": route.mode,
            "intent": route.intent,
            "confidence": route.confidence,
            "source": route.source,
            "matched_signals": list(route.matched_signals),
            "error": route.error,
        })
        self._state.record_artifact("route.json", current_phase)
        self._artifacts.write_json("strategy.json", {
            "strategy": strategy.strategy,
            "complexity": strategy.complexity,
            "score": strategy.score,
            "reason": strategy.reason,
            "matched_signals": list(strategy.matched_signals),
            **strategy_audit(strategy),
        })
        self._state.record_artifact("strategy.json", current_phase)
        if explorer_gate is not None:
            self._artifacts.write_json("explorer_gate.json", explorer_gate.to_dict())
            self._state.record_artifact("explorer_gate.json", current_phase)
        if self._source_run:
            import_source_run_artifacts(self._target, self._artifacts, self._state, self._source_run)
        record_ci_and_git_artifacts(
            self._target,
            self._artifacts,
            self._state,
            run_id=run_id,
            request=request,
            branch_mode=self._config.git_branch_mode,
            warnings=self._warnings,
            github_ci_mode=self._config.github_ci_mode,
        )
        return InitResult(route, strategy, explorer_gate, self._artifacts, self._state, run_state)
