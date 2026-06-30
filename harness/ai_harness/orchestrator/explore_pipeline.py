"""Internal EXPLORE pipeline orchestration."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Callable, Protocol

from ..phases import get_phase
from .context import RunContext
from .exploration_map import ExplorationMapBuilder
from .explore_evidence import ci_evidence_from_artifacts, compact_context_pack, context_pack, evidence_from_digest, merge_evidence


class ExplorePipelineCallbacks(Protocol):
    explorer_scope: Callable[[], dict[str, object]]
    request_brief: Callable[[], str]
    related_improvements: Callable[[], list[dict[str, str | int]]]
    repository_observations: Callable[[Sequence[Mapping[str, object]], Mapping[str, object] | None], list[dict[str, object]]]


class ExplorePipelineService:
    """Run EXPLORE as evidence acquisition and PURPOSE handoff packaging."""

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
        profile = self._invoke_json("explore_request_profile", self._base_inputs())
        related = self._callbacks.related_improvements()
        observations = self._callbacks.repository_observations(related, profile)
        self._ctx.repository_observations = observations
        pack = context_pack(
            request=self._callbacks.request_brief(),
            profile=profile,
            knowledge=[entry.summary for entry in self._ctx.knowledge_context],
            related_improvements=related,
            repository_observations=observations,
            artifacts=self._ctx.artifacts,
            explorer_scope=self._callbacks.explorer_scope(),
        )
        self._ctx.artifacts.write_json("explore/context_pack.json", pack)
        self._ctx.state.record_artifact("explore/context_pack.json", "EXPLORE")
        ci_digest = pack.get("ci_digest", {}) if isinstance(pack.get("ci_digest"), dict) else {}
        relevant_paths = set(ci_digest.get("relevant_paths", [])) if isinstance(ci_digest.get("relevant_paths"), list) else set()
        controller_evidence = ci_evidence_from_artifacts(self._ctx.artifacts, relevant_paths=relevant_paths)
        prompt_pack = compact_context_pack(pack)
        digest = self._invoke_json("explore_evidence_digest", {
            "request_profile": profile,
            "context_pack": prompt_pack,
            "controller_evidence": controller_evidence,
        })
        evidence = merge_evidence(controller_evidence, evidence_from_digest(digest))
        digest["evidence"] = evidence
        self._ctx.artifacts.write_json("explore/evidence_digest.json", digest)
        self._ctx.state.record_artifact("explore/evidence_digest.json", "EXPLORE_EVIDENCE_DIGEST")
        exploration_map = ExplorationMapBuilder(
            request_understanding=self._profile_as_request_understanding(profile),
            triage=self._profile_as_triage(profile),
            evidence_plan=self._profile_as_evidence_plan(profile),
            evidence_collection={"evidence": evidence, "blockers": digest.get("blockers", [])},
            ci_barrier={"blockers": []},
            evidence_normalization={"evidence": evidence},
            repository_observations=observations,
            related_improvements=related,
        ).build()
        self._ctx.artifacts.write_json("explore/exploration_map.json", exploration_map)
        self._ctx.state.record_artifact("explore/exploration_map.json", "EXPLORE")
        synthesis = self._invoke_json("explore_outcome_synthesis", {
            "request": self._callbacks.request_brief(),
            "request_profile": profile,
            "context_pack": prompt_pack,
            "evidence": evidence,
            "exploration_map": exploration_map,
        })
        outcome_bundle = self._outcome_bundle_from_synthesis(synthesis, evidence, exploration_map)
        self._repair_entry_evidence_refs(outcome_bundle, evidence)
        get_phase("explore").validate(json.dumps(outcome_bundle))
        self._ctx.artifacts.write_json("explore/outcome_bundle.json", outcome_bundle)
        self._ctx.state.record_artifact("explore/outcome_bundle.json", "EXPLORE_OUTCOME_SYNTHESIS")

    @staticmethod
    def _outcome_bundle_from_synthesis(
        synthesis: Mapping[str, object],
        evidence: Sequence[Mapping[str, object]],
        exploration_map: Mapping[str, object],
    ) -> dict[str, object]:
        outcome_bundle = dict(synthesis)
        outcome_bundle["kind"] = "explore_outcome_bundle"
        outcome_bundle["evidence"] = list(evidence)
        outcome_bundle["exploration_map"] = dict(exploration_map)
        return outcome_bundle

    @staticmethod
    def _repair_entry_evidence_refs(outcome_bundle: dict[str, object], evidence: Sequence[Mapping[str, object]]) -> None:
        ordered_ids = [str(item.get("id")) for item in evidence if item.get("id")]
        evidence_ids = set(ordered_ids)
        fallback = ordered_ids[0] if ordered_ids else ""
        entries = outcome_bundle.get("entries", [])
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            refs = entry.get("evidence_refs", [])
            if not isinstance(refs, list):
                entry["evidence_refs"] = [fallback] if fallback else []
                continue
            valid_refs = [ref for ref in refs if isinstance(ref, str) and ref in evidence_ids]
            if valid_refs:
                entry["evidence_refs"] = valid_refs
            elif fallback:
                entry["evidence_refs"] = [fallback]

    def _base_inputs(self) -> dict[str, object]:
        return {
            "request": self._callbacks.request_brief(),
            "knowledge": [entry.summary for entry in self._ctx.knowledge_context],
            "repository": str(self._ctx.target),
            "explorer_scope": self._callbacks.explorer_scope(),
        }

    def _invoke_json(self, name: str, inputs: Mapping[str, object]) -> dict[str, object]:
        output = self._invoke_text(name, inputs)
        value = json.loads(output)
        if not isinstance(value, dict):
            raise TypeError(f"{name} returned a non-object JSON artifact")
        return value

    def _invoke_text(self, name: str, inputs: Mapping[str, object]) -> str:
        output = self._invoke_with_repair(name, inputs, parse_control=False)
        artifact = get_phase(name).artifact
        self._ctx.artifacts.write(artifact, output)
        self._ctx.state.record_artifact(artifact, name.upper())
        return output

    @staticmethod
    def _profile_as_request_understanding(profile: Mapping[str, object]) -> dict[str, object]:
        return {
            "summary": profile.get("summary", ""),
            "explicit_constraints": profile.get("constraints", []),
            "mentioned_surfaces": profile.get("request_parts", []),
        }

    @staticmethod
    def _profile_as_triage(profile: Mapping[str, object]) -> dict[str, object]:
        return {
            "complexity": profile.get("complexity", "local_change"),
            "ambiguity": profile.get("ambiguity", "clear"),
            "risk": profile.get("risk", "low"),
            "evidence_depth": profile.get("evidence_depth", "standard"),
        }

    @staticmethod
    def _profile_as_evidence_plan(profile: Mapping[str, object]) -> dict[str, object]:
        gatherers = profile.get("gatherers", []) if isinstance(profile.get("gatherers"), list) else []
        return {
            "required_gatherers": gatherers,
            "optional_gatherers": [],
            "ci_requirement": "optional" if "ci" in gatherers else "not_needed",
            "questions": profile.get("evidence_questions", []),
        }
