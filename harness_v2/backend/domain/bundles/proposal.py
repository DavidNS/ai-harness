"""PROPOSAL_BUNDLE composition."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec, PhaseName, PhaseRef

PROPOSAL_BUNDLE = BundleSpec(
    BundleName.PROPOSAL_BUNDLE,
    children=(
        PhaseRef(PhaseName.PROPOSAL_DRAFT),
        PhaseRef(PhaseName.VALIDATE_JSON),
        PhaseRef(PhaseName.PROPOSAL_HANDOFF),
    ),
)
