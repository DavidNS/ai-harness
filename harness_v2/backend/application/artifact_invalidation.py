"""Backend-owned artifact invalidation for lifecycle rewinds."""

from __future__ import annotations

from dataclasses import dataclass

from harness_v2.backend.domain.lifecycle import PhaseName
from harness_v2.backend.ports.artifact_store import ArtifactStorePort

@dataclass(frozen=True, slots=True)
class ArtifactInvalidationRule:
    artifacts: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "prefixes", tuple(self.prefixes))


@dataclass(frozen=True, slots=True)
class InvalidatedArtifact:
    artifact_id: str
    content: bytes


def invalidate_phase_artifacts(
    artifact_store: ArtifactStorePort,
    run_id: str,
    phases: tuple[PhaseName, ...],
    rules: dict[PhaseName, ArtifactInvalidationRule] | None = None,
) -> tuple[InvalidatedArtifact, ...]:
    existing = artifact_store.list(run_id)
    invalidated: list[InvalidatedArtifact] = []
    exact = set()
    prefixes = []
    rules = rules or {}
    for phase in phases:
        rule = rules.get(phase, ArtifactInvalidationRule())
        exact.update(rule.artifacts)
        exact.add(f"validation/{phase.value}-failure.json")
        prefixes.append(f"workers/{phase.value}/")
        prefixes.extend(rule.prefixes)
    for metadata in existing:
        artifact_id = metadata.artifact_id
        if artifact_id in exact or any(artifact_id.startswith(prefix) for prefix in prefixes):
            invalidated.append(InvalidatedArtifact(artifact_id, artifact_store.read(run_id, artifact_id)))
            artifact_store.delete(run_id, artifact_id)
    return tuple(invalidated)


def restore_invalidated_artifacts(
    artifact_store: ArtifactStorePort,
    run_id: str,
    artifacts: tuple[InvalidatedArtifact, ...],
) -> None:
    for artifact in artifacts:
        artifact_store.write(run_id, artifact.artifact_id, artifact.content)
