"""Shared explorer context built from discovery artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ..errors import HarnessError


@dataclass
class ExplorerContext:
    related_improvements: list[dict[str, object]]
    repository_observations: list[dict[str, object]]

    @classmethod
    def from_discovery(cls, discovery: Mapping[str, object]) -> ExplorerContext:
        related = discovery.get("related_improvements", [])
        observations = discovery.get("repository_observations", [])
        if not isinstance(related, list) or not isinstance(observations, list):
            raise HarnessError("explorer discovery context is malformed")
        return cls(list(related), list(observations))

    def to_dict(self) -> dict[str, object]:
        return {
            "related_improvements": list(self.related_improvements),
            "repository_observations": list(self.repository_observations),
        }


@dataclass
class ExplorerExtractionContext:
    entry_id: str
    artifact_kind: str
    learning: str
    entry_content: str
    intake: Mapping[str, object]
    discovery: Mapping[str, object]
    decision: Mapping[str, object]
    review: str
    related_improvements: list[dict[str, object]]
    repository_observations: list[dict[str, object]]
    evidence_sources_checked: Sequence[str]

    def synthesis_context(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "artifact_kind": self.artifact_kind,
            "learning": self.learning,
            "entry_content": self.entry_content,
            "intake": dict(self.intake),
            "discovery": dict(self.discovery),
            "decision": dict(self.decision),
            "review": self.review,
            "related_improvements": list(self.related_improvements),
            "repository_observations": list(self.repository_observations),
            "evidence_sources_checked": list(self.evidence_sources_checked),
        }

    def distill_inputs(self, request: str) -> dict[str, object]:
        return {
            "request": request,
            "artifact_candidate": self.entry_content,
            "decision": dict(self.decision),
            "discovery": dict(self.discovery),
            "review": self.review,
            "related_improvements": list(self.related_improvements),
            "repository_observations": list(self.repository_observations),
        }
