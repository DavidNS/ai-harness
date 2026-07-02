"""DESIGN_BUNDLE composition."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec, PhaseName, PhaseRef

DESIGN_BUNDLE = BundleSpec(
    BundleName.DESIGN_BUNDLE,
    children=(
        PhaseRef(PhaseName.DESIGN_DRAFT),
        PhaseRef(PhaseName.VALIDATE_JSON),
        PhaseRef(PhaseName.DESIGN_HANDOFF),
    ),
)
