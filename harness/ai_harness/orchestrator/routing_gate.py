"""RoutingGate — analysis-gate decision-making and scope resolution.

Single responsibility: build the analysis-gate DecisionRequest, find the
user's answer in history, and compute/persist the explorer scope artifact.

Previously four methods on AnalysisQualityMixin:
  _explorer_gate_context_lines, _explorer_gate_decision_request,
  _explorer_gate_answer_choice, _explorer_scope.
"""
from __future__ import annotations

from pathlib import Path

from ..explorer_gate import ExplorerGateDecision
from ..canonical import CanonicalDocs
from ..control_outputs import DecisionOption, DecisionRequest
from ..errors import HarnessError
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from .explorer_scope import ExplorerScopeResolver


class RoutingGate:
    """Computes routing decisions and the explorer scope artifact.

    Cheap to instantiate per call. ``scope()`` does NOT cache — the caller
    (AnalysisQualityMixin._explorer_scope) owns the ``_explorer_scope_cache``
    field on the Orchestrator.
    """

    def __init__(
        self,
        state: StateStore,
        artifacts: ArtifactStore,
        target: Path,
        canonical: CanonicalDocs,
    ) -> None:
        self._state = state
        self._artifacts = artifacts
        self._target = target
        self._canonical = canonical

    # ------------------------------------------------------------------ #
    # Explorer gate: ask-user decision request                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def context_lines(gate: ExplorerGateDecision) -> tuple[str, ...]:
        del gate
        return ("No path will be selected automatically; the user must choose the flow.",)

    def decision_request(self, gate: ExplorerGateDecision) -> DecisionRequest:
        options = [
            DecisionOption(
                "sdd",
                "Full SDD",
                "Run EXPLORE_BUNDLE, PROPOSAL_BUNDLE, SPEC_BUNDLE, DESIGN_BUNDLE, TASKS_BUNDLE, and TDD_BUNDLE.",
            ),
            DecisionOption(
                "explore_bundle",
                "EXPLORE_BUNDLE",
                "Run EXPLORE_BUNDLE only and stop after publishing exploration handoff artifacts.",
            ),
            DecisionOption("proposal_bundle", "PROPOSAL_BUNDLE", "Run PROPOSAL_BUNDLE from imported source-run artifacts."),
            DecisionOption("spec_bundle", "SPEC_BUNDLE", "Run SPEC_BUNDLE from imported source-run artifacts."),
            DecisionOption("design_bundle", "DESIGN_BUNDLE", "Run DESIGN_BUNDLE from imported source-run artifacts."),
            DecisionOption("tasks_bundle", "TASKS_BUNDLE", "Run TASKS_BUNDLE from imported source-run artifacts."),
            DecisionOption("tdd_bundle", "TDD_BUNDLE", "Run TDD_BUNDLE from imported source-run artifacts."),
        ]
        return DecisionRequest(
            "SELECTING_STRATEGY",
            gate.reason,
            "Which bundle flow should the harness run for this request?",
            self.context_lines(gate),
            tuple(options),
            True,
            None,
            gate.scores,
            gate.score_signals,
            gate.ranked_paths,
        )

    # ------------------------------------------------------------------ #
    # Explorer gate: find the user's prior answer                        #
    # ------------------------------------------------------------------ #

    def answer_choice(self) -> str | None:
        for item in reversed(self._state.decision_history()):
            request = item.get("request")
            answer = item.get("answer")
            if not isinstance(request, dict) or request.get("origin_phase") != "SELECTING_STRATEGY":
                continue
            if not isinstance(answer, dict):
                continue
            selected = answer.get("selected_option")
            bundle_options = {"explore_bundle", "proposal_bundle", "spec_bundle", "design_bundle", "tasks_bundle", "tdd_bundle", "sdd"}
            if selected in bundle_options:
                return str(selected)
            aliases = {
                "explorer": "explore_bundle",
                "explore": "explore_bundle",
                "proposal": "proposal_bundle",
                "purpose": "proposal_bundle",
                "spec": "spec_bundle",
                "design": "design_bundle",
                "tasks": "tasks_bundle",
                "tdd": "tdd_bundle",
                "sdd_high": "sdd",
                "sdd_low": "sdd",
            }
            if selected in aliases:
                return aliases[str(selected)]
            text = str(answer.get("answer", "")).casefold()
            if "explor" in text or "analysis" in text or "investigat" in text:
                return "explore_bundle"
            if "high" in text or "hard" in text or "full" in text:
                return "sdd"
            if "low" in text or "simple" in text or "lightweight" in text or "easy" in text:
                return "sdd"
            if "medium" in text or "sdd" in text:
                return "sdd"
        return None

    # ------------------------------------------------------------------ #
    # Explorer scope resolution                                           #
    # ------------------------------------------------------------------ #

    def scope(self) -> dict[str, object]:
        """Return the explorer scope, reading or computing it as needed.

        Does NOT cache the result — the shim in AnalysisQualityMixin._explorer_scope
        owns the cache so the same object is returned on repeated calls within a run.
        """
        if self._artifacts.exists("explorer_scope.json"):
            scope = self._artifacts.read_json("explorer_scope.json")
            if not isinstance(scope, dict):
                raise HarnessError("explorer_scope.json must be an object")
            return scope
        scope = ExplorerScopeResolver(self._target, self._artifacts, self._canonical).resolve(
            self._state.load().user_input
        )
        self._artifacts.write_json("explorer_scope.json", scope)
        self._state.record_artifact("explorer_scope.json", self._state.load().current_phase)
        return scope
