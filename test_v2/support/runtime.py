from __future__ import annotations

from dataclasses import dataclass

from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryKnowledgePatchStore, InMemoryStateStore
from harness_v2.backend.application.phase_executor import default_phase_function_registry
from harness_v2.backend.application.run_orchestrator import RunOrchestrator


@dataclass(slots=True)
class StaticIdGenerator:
    next_id: str = "run-1"

    def new_id(self) -> str:
        return self.next_id


class StaticClock:
    def now_iso(self) -> str:
        return "2026-07-01T00:00:00+00:00"


def memory_orchestrator(run_id: str = "run-1") -> tuple[RunOrchestrator, InMemoryStateStore, InMemoryArtifactStore, InMemoryKnowledgePatchStore]:
    state = InMemoryStateStore()
    artifacts = InMemoryArtifactStore()
    knowledge = InMemoryKnowledgePatchStore()
    registry = default_phase_function_registry()
    service = RunOrchestrator(
        state,
        StaticIdGenerator(run_id),
        clock=StaticClock(),
        artifact_store=artifacts,
        invalidation_rules=registry.invalidation_rules(),
        knowledge_patches=knowledge,
    )
    return service, state, artifacts, knowledge
