"""Append-only EXPLORE evidence deltas."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Callable

from ..control_outputs import EvidenceRequest
from ..phases import get_phase
from .context import RunContext
from .explore_evidence import ci_evidence_from_artifacts, compact_context_pack, context_pack, evidence_from_digest, merge_evidence


class ExploreDeltaService:
    def __init__(
        self,
        context: RunContext,
        *,
        request_brief: Callable[[], str],
        explorer_scope: Callable[[], dict[str, object]],
        related_improvements: Callable[[], list[dict[str, str | int]]],
        repository_observations: Callable[[Sequence[Mapping[str, object]], Mapping[str, object] | None], list[dict[str, object]]],
        invoke_with_repair: Callable[..., str],
    ) -> None:
        self._ctx = context
        self._request_brief = request_brief
        self._explorer_scope = explorer_scope
        self._related_improvements = related_improvements
        self._repository_observations = repository_observations
        self._invoke_with_repair = invoke_with_repair

    def run(self, request_id: str, request: EvidenceRequest) -> dict[str, object]:
        profile = self._safe_json("explore/request_profile.json")
        related = self._related_improvements()
        observations = self._repository_observations(related, profile)
        pack = context_pack(
            request=self._request_brief(),
            profile=profile,
            knowledge=[entry.summary for entry in self._ctx.knowledge_context],
            related_improvements=related,
            repository_observations=observations,
            artifacts=self._ctx.artifacts,
            explorer_scope=self._explorer_scope(),
        )
        pack["evidence_request"] = request.to_dict() | {"request_id": request_id}
        ci_digest = pack.get("ci_digest", {}) if isinstance(pack.get("ci_digest"), dict) else {}
        relevant_paths = set(ci_digest.get("relevant_paths", [])) if isinstance(ci_digest.get("relevant_paths"), list) else set()
        controller_evidence = ci_evidence_from_artifacts(self._ctx.artifacts, relevant_paths=relevant_paths)
        output = self._invoke_with_repair("explore_delta", {
            "evidence_request": request.to_dict() | {"request_id": request_id},
            "context_pack": compact_context_pack(pack),
            "controller_evidence": controller_evidence,
        }, parse_control=False)
        value = json.loads(output)
        if not isinstance(value, dict):
            raise TypeError("explore_delta returned non-object JSON")
        value["request_id"] = request_id
        value["evidence"] = merge_evidence(evidence_from_digest(value))
        get_phase("explore_delta").validate(json.dumps(value))
        artifact = f"explore/deltas/ED{request_id.removeprefix('ER')}.json"
        self._ctx.artifacts.write_json(artifact, value)
        self._ctx.state.record_artifact(artifact, "EXPLORE_DELTA")
        return value

    def _safe_json(self, name: str) -> dict[str, object]:
        if not self._ctx.artifacts.exists(name):
            return {}
        value = self._ctx.artifacts.read_json(name)
        return dict(value) if isinstance(value, Mapping) else {}
