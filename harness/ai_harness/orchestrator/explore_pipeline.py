"""Internal EXPLORE pipeline orchestration."""

from __future__ import annotations

import json
from typing import Callable, Mapping, Protocol, Sequence

from ..errors import HarnessError
from ..phases import get_phase
from .context import RunContext
from .exploration_map import ExplorationMapBuilder


class ExplorePipelineCallbacks(Protocol):
    explorer_scope: Callable[[], dict[str, object]]
    request_brief: Callable[[], str]
    related_improvements: Callable[[], list[dict[str, str | int]]]
    repository_observations: Callable[[Sequence[Mapping[str, object]], Mapping[str, object] | None], list[dict[str, object]]]


class ExplorePipelineService:
    """Run the internal EXPLORE stages and publish the PURPOSE handoff bundle."""

    def __init__(
        self,
        context: RunContext,
        callbacks: ExplorePipelineCallbacks,
        invoke_with_repair: Callable[..., str],
    ) -> None:
        self._ctx = context
        self._callbacks = callbacks
        self._invoke_with_repair = invoke_with_repair

    def run(self) -> None:
        request_understanding = self._invoke_json("explore_request_understanding", self._base_inputs())
        clarification_gate = self._invoke_json("explore_clarification_gate", {
            "request_understanding": request_understanding,
        })
        triage = self._invoke_json("explore_triage", {
            "request_understanding": request_understanding,
            "clarification_gate": clarification_gate,
        })
        evidence_plan = self._invoke_json("explore_evidence_plan", {
            **self._base_inputs(),
            "request_understanding": request_understanding,
            "triage": triage,
        })
        related = self._callbacks.related_improvements()
        observations = self._callbacks.repository_observations(related, request_understanding)
        self._ctx.repository_observations = observations
        evidence_collection = self._invoke_json("explore_evidence_collection", {
            **self._base_inputs(),
            "request_understanding": request_understanding,
            "triage": triage,
            "evidence_plan": evidence_plan,
            "related_improvements": related,
            "repository_observations": observations,
        })
        ci_barrier = self._invoke_json("explore_ci_barrier", {
            "evidence_plan": evidence_plan,
            "ci_status": self._artifact_json("ci-status.json"),
            "git_run": self._artifact_json("git-run.json"),
            "ci_signals": self._artifact_json("ci-signals.json"),
        })
        evidence_normalization = self._invoke_json("explore_evidence_normalization", {
            "evidence_collection": evidence_collection,
            "ci_barrier": ci_barrier,
        })
        exploration_map = ExplorationMapBuilder(
            request_understanding=request_understanding,
            triage=triage,
            evidence_plan=evidence_plan,
            evidence_collection=evidence_collection,
            ci_barrier=ci_barrier,
            evidence_normalization=evidence_normalization,
            repository_observations=observations,
            related_improvements=related,
        ).build()
        self._ctx.artifacts.write_json("explore/exploration_map.json", exploration_map)
        self._ctx.state.record_artifact("explore/exploration_map.json", "EXPLORE")
        outcome_bundle = self._invoke_json("explore_outcome_synthesis", {
            "request": self._callbacks.request_brief(),
            "request_understanding": request_understanding,
            "clarification_gate": clarification_gate,
            "triage": triage,
            "evidence_plan": evidence_plan,
            "evidence_collection": evidence_collection,
            "ci_barrier": ci_barrier,
            "evidence_normalization": evidence_normalization,
            "exploration_map": exploration_map,
        })
        if "exploration_map" not in outcome_bundle:
            outcome_bundle["exploration_map"] = exploration_map
            get_phase("explore_outcome_synthesis").validate(json.dumps(outcome_bundle))
            self._ctx.artifacts.write_json("explore/outcome_bundle.json", outcome_bundle)
            self._ctx.state.record_artifact("explore/outcome_bundle.json", "EXPLORE_OUTCOME_SYNTHESIS")
        review = self._invoke_text("explore_review", {
            "outcome_bundle": outcome_bundle,
            "request_understanding": request_understanding,
            "triage": triage,
            "evidence_plan": evidence_plan,
            "evidence_normalization": evidence_normalization,
        })
        if self._review_verdict(review) != "APPROVE":
            raise HarnessError("explore review did not approve outcome bundle")

    def _base_inputs(self) -> dict[str, object]:
        return {
            "request": self._callbacks.request_brief(),
            "knowledge": [entry.summary for entry in self._ctx.knowledge_context],
            "repository": str(self._ctx.target),
            "explorer_scope": self._callbacks.explorer_scope(),
        }

    def _artifact_json(self, name: str) -> object:
        if not self._ctx.artifacts.exists(name):
            return {}
        try:
            return self._ctx.artifacts.read_json(name)
        except Exception:
            return {}

    def _invoke_json(self, name: str, inputs: Mapping[str, object]) -> dict[str, object]:
        output = self._invoke_text(name, inputs)
        value = json.loads(output)
        if not isinstance(value, dict):
            raise HarnessError(f"{name} returned a non-object JSON artifact")
        return value

    def _invoke_text(self, name: str, inputs: Mapping[str, object]) -> str:
        output = self._invoke_with_repair(name, inputs, parse_control=False)
        artifact = get_phase(name).artifact
        self._ctx.artifacts.write(artifact, output)
        self._ctx.state.record_artifact(artifact, name.upper())
        return output

    @staticmethod
    def _review_verdict(candidate: str) -> str:
        marker = "## Verdict"
        if marker not in candidate:
            return ""
        tail = candidate.split(marker, 1)[1].strip().splitlines()
        return tail[0].strip() if tail else ""
