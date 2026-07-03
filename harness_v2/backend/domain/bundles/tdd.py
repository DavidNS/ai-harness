"""TDD_BUNDLE composition."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec, PhaseName, PhaseRef

TDD_BUNDLE = BundleSpec(
    BundleName.TDD_BUNDLE,
    children=(
        PhaseRef(PhaseName.TDD_EXECUTE),
        PhaseRef(PhaseName.TDD_HANDOFF),
    ),
)
