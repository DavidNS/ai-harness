"""RunInitializer — set up state, route, and strategy for a new run.

Previously _initialize on the Orchestrator plus the module-level
_routing_permissions helper. Zero mixin/cross-component coupling;
all deps are constructor-injected.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..explorer_gate import ExplorerGateDecision, classify_explorer_gate
from ..config import HarnessConfig
from ..ci_support import record_ci_and_git_artifacts
from ..models import Complexity, Mode, RunState, Strategy
from ..providers.base import Provider
from ..router import RouteDecision, route_request
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from ..strategy import StrategyDecision, explorer_strategy_decision


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
    ) -> None:
        self._target = target
        self._provider = provider
        self._config = config
        self._external_runtime = external_runtime
        self._artifacts = artifacts
        self._state = state
        self._resolve_fn = resolve_fn
        self._warnings = warnings

    def initialize(self, request: str, *, strategy_decision: StrategyDecision | None = None) -> InitResult:
        run_id = uuid.uuid4().hex
        if not self._external_runtime:
            self._artifacts = ArtifactStore.for_run(self._target, run_id)
            self._state = StateStore(self._target, self._artifacts)
        route = route_request(
            request,
            provider=self._provider,
            cwd=self._target,
            permissions=_routing_permissions(self._config.timeout_seconds),
        )
        explorer_gate: ExplorerGateDecision | None = None
        if strategy_decision is not None:
            strategy = strategy_decision
        elif route.source == "needs_user":
            route_intent = route.intent if route.mode == "code" else "modify_code"
            route = RouteDecision("code", route_intent, 0.0, "needs_user", route.matched_signals, route.error)
            strategy = explorer_strategy_decision(request, route.matched_signals)
        elif route.mode == "non_code":
            strategy = StrategyDecision("NON_CODE_STUB", "LOW", 0, "Non-code requests use the v1 stub", ())
        else:
            explorer_gate = classify_explorer_gate(request, repository=self._target)
            if explorer_gate.path == "ask_user":
                strategy = explorer_strategy_decision(request, explorer_gate.matched_signals)
            else:
                strategy = self._resolve_fn(request, explorer_gate)
        run_state = RunState(
            run_id, request, "INITIALIZING",
            Strategy(strategy.strategy), Mode(route.mode), route.intent,
            Complexity(strategy.complexity),
            self._config.provider, tuple(self._config.provider_command), self._config.model,
        )
        self._state.save(run_state)
        record_ci_and_git_artifacts(
            self._target,
            self._artifacts,
            self._state,
            run_id=run_id,
            request=request,
            branch_mode=self._config.git_branch_mode,
            warnings=self._warnings,
        )
        return InitResult(route, strategy, explorer_gate, self._artifacts, self._state, run_state)
