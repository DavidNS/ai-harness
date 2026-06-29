"""Explorer worker input construction."""

from __future__ import annotations

from typing import Mapping

from ..ci_support import repository_runtime_context
from .context import RunContext
from .explorer_artifacts import ExplorerArtifacts
from .explorer_context import ExplorerContext
from .worker_exchange import WorkerExchange


class ExplorerInputs:
    """Build stable input payloads for explorer workers."""

    def __init__(
        self,
        context: RunContext,
        request_context: WorkerExchange,
        artifacts: ExplorerArtifacts,
    ) -> None:
        self._ctx = context
        self._request_context = request_context
        self._artifacts = artifacts

    def request_brief(self) -> str:
        return self._request_context._request_brief()

    def related_improvements(self) -> list[dict[str, str | int]]:
        return self._request_context._related_improvements()

    def repository_observations(
        self,
        related_improvements,
        intake: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        return self._request_context._repository_observations(related_improvements, intake)

    def explorer_artifact_path(self, candidate: str) -> str:
        return self._request_context._explorer_artifact_path(candidate)

    def knowledge_summaries(self) -> list[str]:
        return [entry.summary for entry in self._ctx.knowledge_context]

    def base(self) -> dict[str, object]:
        return {
            "request": self.request_brief(),
            "knowledge": self.knowledge_summaries(),
            "repository": str(self._ctx.target),
            "runtime_context": repository_runtime_context(self._ctx.artifacts),
        }

    def legacy_explorer(
        self,
        context: ExplorerContext,
        *,
        repair: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            **self.base(),
            "related_improvements": context.related_improvements,
            "repository_observations": context.repository_observations,
            "repair": dict(repair or {}),
        }

    def intake(self) -> dict[str, object]:
        return self.base()

    def discovery_context(self) -> tuple[Mapping[str, object], ExplorerContext]:
        related = self.related_improvements()
        intake = self._artifacts.stage_json("explorer_intake")
        context = ExplorerContext(
            related_improvements=list(related),
            repository_observations=self.repository_observations(related, intake),
        )
        self._ctx.repository_observations = context.repository_observations
        return intake, context

    def discovery(
        self,
        intake: Mapping[str, object],
        context: ExplorerContext,
        *,
        refinement: object,
    ) -> dict[str, object]:
        return {
            **self.base(),
            "intake": intake,
            "related_improvements": context.related_improvements,
            "repository_observations": context.repository_observations,
            "refinement": refinement,
        }

    def decision(self, context: ExplorerContext, *, refinement: object) -> dict[str, object]:
        self._ctx.repository_observations = context.repository_observations
        return {
            **self.base(),
            "intake": self._artifacts.stage_json("explorer_intake"),
            "discovery": self._artifacts.stage_json("explorer_discovery"),
            "related_improvements": context.related_improvements,
            "repository_observations": context.repository_observations,
            "refinement": refinement,
        }

    def artifact(
        self,
        context: ExplorerContext,
        *,
        repair: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        self._ctx.repository_observations = context.repository_observations
        return {
            **self.base(),
            "intake": self._artifacts.stage_json("explorer_intake"),
            "discovery": self._artifacts.stage_json("explorer_discovery"),
            "decision": self._artifacts.stage_json("explorer_decision"),
            "related_improvements": context.related_improvements,
            "repository_observations": context.repository_observations,
            "repair": dict(repair or {}),
        }

    def review(self, candidate: str, context: ExplorerContext) -> dict[str, object]:
        self._ctx.repository_observations = context.repository_observations
        return {
            "request": self.request_brief(),
            "runtime_context": repository_runtime_context(self._ctx.artifacts),
            "intake": self._artifacts.stage_json("explorer_intake"),
            "discovery": self._artifacts.stage_json("explorer_discovery"),
            "decision": self._artifacts.stage_json("explorer_decision"),
            "artifact_candidate": candidate,
            "related_improvements": context.related_improvements,
            "repository_observations": context.repository_observations,
        }
