"""TDD_BUNDLE composition."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec, PhaseName, PhaseRef

TDD_BUNDLE = BundleSpec(
    BundleName.TDD_BUNDLE,
    children=(
        PhaseRef(PhaseName.TDD_CREATE_TEST),
        PhaseRef(PhaseName.TDD_IMPLEMENT),
        PhaseRef(PhaseName.TDD_REVIEW),
        PhaseRef(PhaseName.TDD_HANDOFF),
    ),
)
