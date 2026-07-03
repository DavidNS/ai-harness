"""Knowledge extraction bundle compositions."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec, PhaseName, PhaseRef

KNOWLEDGE_EXTRACT_EXPLORE = BundleSpec(
    BundleName.KNOWLEDGE_EXTRACT_EXPLORE,
    children=(
        PhaseRef(PhaseName.KNOWLEDGE_EXTRACT_SYNTHESIS),
        PhaseRef(PhaseName.KNOWLEDGE_EXTRACT_PATCH),
    ),
)

KNOWLEDGE_EXTRACT_TDD = BundleSpec(
    BundleName.KNOWLEDGE_EXTRACT_TDD,
    children=(
        PhaseRef(PhaseName.KNOWLEDGE_EXTRACT_SYNTHESIS),
        PhaseRef(PhaseName.KNOWLEDGE_EXTRACT_PATCH),
    ),
)
