"""Phase callbacks for staged explorer."""

from __future__ import annotations

import json
from typing import Callable

from ..contracts.enums import PhaseName
from ..control_outputs import ControlFlowSignal, PhaseEscalation
from .explorer_artifacts import ExplorerArtifacts
from .explorer_decision_reader import ExplorerDecisionReader
from .explorer_decisions import (
    decision_request_from_explorer_decision,
    validate_explorer_value_gate,
)
from .explorer_inputs import ExplorerInputs


class ExplorerPhaseService:
    """Own intake, discovery, decision, and artifact phase callbacks."""

    def __init__(
        self,
        artifacts: ExplorerArtifacts,
        inputs: ExplorerInputs,
        decision_reader: Callable[[], ExplorerDecisionReader],
        invoke_with_repair: Callable[..., str],
    ) -> None:
        self._artifacts = artifacts
        self._inputs = inputs
        self._decision_reader = decision_reader
        self._invoke_with_repair = invoke_with_repair

    def intake(self) -> None:
        output = self._invoke_with_repair("explorer_intake", self._inputs.intake())
        self._artifacts.write_phase_artifact("explorer_intake", output)

    def discovery(self) -> None:
        intake, context = self._inputs.discovery_context()
        output = self._invoke_with_repair(
            "explorer_discovery",
            self._inputs.discovery(
                intake,
                context,
                refinement=self._decision_reader().latest_none_of_above_refinement(),
            ),
        )
        self._artifacts.write_phase_artifact("explorer_discovery", output)

    def decision(self) -> None:
        reader = self._decision_reader()
        none_of_above_count = reader.none_of_above_count()
        if none_of_above_count > reader.refinement_escalation_count():
            raise ControlFlowSignal(PhaseEscalation(
                PhaseName.EXPLORE_BUNDLE,
                PhaseName.EXPLORE_BUNDLE,
                "none_of_above selected; rerun discovery with the user's refinement before choosing a direction.",
            ))
        context = self._artifacts.context_from_discovery()
        output = self._invoke_with_repair(
            "explorer_decision",
            self._inputs.decision(context, refinement=reader.latest_none_of_above_refinement()),
        )
        self._artifacts.write_phase_artifact("explorer_decision", output)
        decision = json.loads(output)
        outcome = decision.get("outcome")
        if outcome == "needs_user_decision":
            raise ControlFlowSignal(decision_request_from_explorer_decision(decision))
        if outcome == "escalate_discovery":
            raise ControlFlowSignal(PhaseEscalation(
                PhaseName.EXPLORE_BUNDLE,
                PhaseName.EXPLORE_BUNDLE,
                str(decision.get("rediscovery_reason", "Discovery needs more evidence.")),
            ))
        validate_explorer_value_gate(decision, self._artifacts.stage_json("explorer_discovery"))

    def artifact(self) -> None:
        context = self._artifacts.context_from_discovery()
        output = self._invoke_with_repair(
            "explorer_artifact",
            self._inputs.artifact(context),
            parse_control=False,
        )
        self._artifacts.write_phase_artifact("explorer_artifact", output)
