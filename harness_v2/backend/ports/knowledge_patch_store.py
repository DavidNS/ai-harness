"""Knowledge patch persistence port for v2 candidate learning."""

from __future__ import annotations

from typing import Protocol

from harness_v2.backend.domain.knowledge import (
    KnowledgePatchRecord,
    KnowledgePatchStatus,
    LearningProposalBundle,
)
from harness_v2.backend.domain.lifecycle import BundleName


class KnowledgePatchStoreError(RuntimeError):
    """Base error for knowledge patch store failures."""


class KnowledgePatchNotFoundError(KnowledgePatchStoreError):
    """Raised when a requested knowledge patch does not exist."""


class KnowledgePatchStorePort(Protocol):
    """Candidate knowledge patch boundary."""

    def create_patch(
        self,
        run_id: str,
        origin_bundle: BundleName,
        proposal: LearningProposalBundle,
        created_at: str,
    ) -> KnowledgePatchRecord: ...

    def get_patch(self, patch_id: str) -> KnowledgePatchRecord: ...

    def list_patches(
        self,
        run_id: str | None = None,
        status: KnowledgePatchStatus | None = None,
    ) -> tuple[KnowledgePatchRecord, ...]: ...

    def reject_patch(self, patch_id: str, reason: str, rejected_at: str) -> KnowledgePatchRecord: ...
