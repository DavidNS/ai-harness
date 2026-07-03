"""Backend-owned artifact invalidation for lifecycle rewinds."""

from __future__ import annotations

from dataclasses import dataclass

from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName
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


def invalidate_step_artifacts(
    artifact_store: ArtifactStorePort,
    run_id: str,
    root_bundle: BundleName | str,
    step_ids: tuple[str, ...],
    rules: dict[PhaseName, ArtifactInvalidationRule] | None = None,
) -> tuple[InvalidatedArtifact, ...]:
    existing = artifact_store.list(run_id)
    invalidated: list[InvalidatedArtifact] = []
    exact = set()
    prefixes = []
    rules = rules or {}
    for step_id in step_ids:
        step = bundle_catalog.step_for_step_id(root_bundle, step_id)
        rule = rules.get(step.phase_name, ArtifactInvalidationRule())
        exact.update(_step_artifact(artifact_id, step) for artifact_id in rule.artifacts)
        exact.add(f"validation/{_safe_step_id(step.step_id)}-failure.json")
        prefixes.append(f"workers/{_safe_step_id(step.step_id)}/")
        prefixes.extend(_step_prefix(prefix, step.step_id) for prefix in rule.prefixes)
    for metadata in existing:
        artifact_id = metadata.artifact_id
        if artifact_id in exact or any(artifact_id.startswith(prefix) for prefix in prefixes):
            invalidated.append(InvalidatedArtifact(artifact_id, artifact_store.read(run_id, artifact_id)))
            artifact_store.delete(run_id, artifact_id)
    return tuple(invalidated)


def _step_artifact(artifact_id: str, step) -> str:
    return artifact_id.format(
        bundle=step.bundle_name.value,
        phase=step.phase_name.value,
        step_id=_safe_step_id(step.step_id),
    )


def _safe_step_id(step_id: str) -> str:
    return step_id.replace(":", "_")


def _step_prefix(prefix: str, step_id: str) -> str:
    if prefix.startswith("workers/"):
        parts = prefix.rstrip("/").split("/")
        if len(parts) >= 4:
            return f"workers/{_safe_step_id(step_id)}/{parts[-1]}/"
    return prefix


def restore_invalidated_artifacts(
    artifact_store: ArtifactStorePort,
    run_id: str,
    artifacts: tuple[InvalidatedArtifact, ...],
) -> None:
    for artifact in artifacts:
        artifact_store.write(run_id, artifact.artifact_id, artifact.content)
