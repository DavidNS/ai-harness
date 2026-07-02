"""SPEC_BUNDLE composition."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec, PhaseName, PhaseRef

SPEC_BUNDLE = BundleSpec(
    BundleName.SPEC_BUNDLE,
    children=(
        PhaseRef(PhaseName.SPEC_DRAFT),
        PhaseRef(PhaseName.VALIDATE_JSON),
        PhaseRef(PhaseName.SPEC_HANDOFF),
    ),
)
