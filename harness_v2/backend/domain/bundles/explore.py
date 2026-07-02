"""EXPLORE_BUNDLE composition."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec, PhaseName, PhaseRef

EXPLORE_BUNDLE = BundleSpec(
    BundleName.EXPLORE_BUNDLE,
    children=(
        PhaseRef(PhaseName.EXPLORE_REQUEST_UNDERSTANDING),
        PhaseRef(PhaseName.EXPLORE_CONTEXT_PACK),
        PhaseRef(PhaseName.EXPLORE_EVIDENCE_DIGEST),
        PhaseRef(PhaseName.EXPLORE_EXPLORATION_MAP),
        PhaseRef(PhaseName.EXPLORE_OUTCOME_SYNTHESIS),
        PhaseRef(PhaseName.EXPLORE_HANDOFF),
    ),
)
