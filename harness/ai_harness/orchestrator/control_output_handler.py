"""Control-output handling for orchestration phase execution."""

from __future__ import annotations

from typing import Callable, Protocol

from ..contracts.enums import PhaseName
from ..contracts.vocab import INFRASTRUCTURE_TERMS
from ..control_outputs import (
    ControlOutput,
    DecisionRequest,
    ImpossibleOutcome,
    ExplorerBundle,
    ExplorerBundleEntry,
    PhaseEscalation,
)
from ..errors import HarnessError, StateError
from ..output import RunResult
from ..phases import get_phase
from ..pipeline.state_machine import graph_for
from .context import RunContext
from .explorer_context import ExplorerContext


class ControlOutputCallbacks(Protocol):
    explorer_context_from_discovery: Callable[[], ExplorerContext]
    markdown_section: Callable[[str, str], str]
    publish_explorer_bundle: Callable[..., object]
    waiting_result: Callable[[object], RunResult]


class ControlOutputHandler:
    """Apply parsed control outputs to run state and publication artifacts."""

    def __init__(self, context: RunContext, callbacks: ControlOutputCallbacks) -> None:
        self._ctx = context
        self._callbacks = callbacks

    @staticmethod
    def _invalid_impossible_reason(output: ImpossibleOutcome) -> str | None:
        if not output.origin_phase.startswith("EXPLORER"):
            return "impossible is only valid as an explorer analysis outcome"
        text = "\n".join((output.reason, *output.evidence, *output.remaining_options)).casefold()
        if any(term in text for term in INFRASTRUCTURE_TERMS):
            return "impossible cannot be used for infrastructure, tooling, permission, or evidence-access blockers"
        return None

    def _limitation_from_impossible(self, output: ImpossibleOutcome) -> str:
        state = self._ctx.state.load()
        evidence = "\n".join(f"- {item}" for item in output.evidence) or "- No evidence supplied."
        remaining = "\n".join(f"- {item}" for item in output.remaining_options) or "- Stop; no remaining implementation path was identified."
        return (
            "# Limitation v1\n"
            "## Problem\n"
            f"{state.user_input.strip()}\n"
            "## Context\n"
            "The completed explorer concluded the requested outcome is impossible because of a limitation.\n"
            "## Reasoning\n"
            f"{output.reason.strip()}\n\nEvidence:\n{evidence}\n"
            "## Outcome\n"
            "limitation\n"
            "## Next Step\n"
            f"{remaining}\n"
        )

    def _control_output_explorer_context(self) -> ExplorerContext:
        context = self._callbacks.explorer_context_from_discovery()
        self._ctx.repository_observations = context.repository_observations
        return context

    def _record_impossible_as_limitation(self, output: ImpossibleOutcome, *, target_phase: str) -> None:
        artifact = self._limitation_from_impossible(output)
        get_phase("explorer").validate(artifact)
        entry = ExplorerBundleEntry(
            "impossible",
            "limitation",
            self._callbacks.markdown_section(artifact, "Problem") or self._ctx.state.load().user_input,
            "limitation",
            artifact,
        )
        self._callbacks.publish_explorer_bundle(
            ExplorerBundle("EXPLORER", (entry,), "impossible"),
            self._control_output_explorer_context(),
            target_phase=target_phase,
        )
        self._ctx.state.mark_phase_completed(target_phase)

    def handle(self, output: ControlOutput, *, target_phase: str) -> RunResult | None:
        if isinstance(output, DecisionRequest):
            state = self._ctx.state.record_decision_request(output, target_phase=target_phase)
            assert state.pending_decision is not None
            self._ctx.progress(f"Decision required from {output.origin_phase.lower()}: {state.pending_decision.id}")
            return self._callbacks.waiting_result(state)
        if isinstance(output, PhaseEscalation):
            self._ctx.state.record_phase_escalation(output, active_graph_phase=target_phase)
            self._ctx.progress(f"Escalating {output.origin_phase} to {output.target_phase}")
            return None
        if isinstance(output, ImpossibleOutcome):
            invalid_reason = self._invalid_impossible_reason(output)
            if invalid_reason is not None:
                raise HarnessError(f"invalid impossible control output from {output.origin_phase}: {invalid_reason}")
            self._record_impossible_as_limitation(output, target_phase=target_phase)
            state = self._ctx.state.load()
            graph = graph_for(state.strategy, state.complexity)
            if target_phase.startswith("EXPLORER") and PhaseName.EXPLORER_REVIEW in graph:
                review_index = graph.index(PhaseName.EXPLORER_REVIEW)
                completed = list(dict.fromkeys([*state.completed_phases, *graph[: review_index + 1]]))
                self._ctx.state.update(completed_phases=completed, current_phase=PhaseName.EXPLORER_REVIEW)
            self._ctx.progress("Converted explorer impossible outcome to limitation artifact")
            return None
        if isinstance(output, ExplorerBundle):
            self._callbacks.publish_explorer_bundle(
                output,
                self._control_output_explorer_context(),
                target_phase=target_phase,
            )
            self._ctx.state.mark_phase_completed(target_phase)
            self._ctx.progress("Published explorer bundle manifest")
            return None
        raise StateError("unsupported control output")
