"""PROPOSAL_BUNDLE composition."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec, PhaseName, PhaseRef

PROPOSAL_BUNDLE = BundleSpec(
    BundleName.PROPOSAL_BUNDLE,
    children=(
        PhaseRef(PhaseName.PROPOSAL_PURPOSE),
        PhaseRef(PhaseName.PROPOSAL_HANDOFF),
    ),
)
