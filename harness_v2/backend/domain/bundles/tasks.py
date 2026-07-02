"""TASKS_BUNDLE composition."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec, PhaseName, PhaseRef

TASKS_BUNDLE = BundleSpec(
    BundleName.TASKS_BUNDLE,
    children=(
        PhaseRef(PhaseName.TASKS_DRAFT),
        PhaseRef(PhaseName.VALIDATE_JSON),
        PhaseRef(PhaseName.TASKS_HANDOFF),
    ),
)
