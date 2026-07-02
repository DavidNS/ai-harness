"""SDD_BUNDLE composition."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleRef, BundleSpec

SDD_BUNDLE = BundleSpec(
    BundleName.SDD_BUNDLE,
    children=(
        BundleRef(BundleName.EXPLORE_BUNDLE),
        BundleRef(BundleName.KNOWLEDGE_EXTRACT_EXPLORE),
        BundleRef(BundleName.PROPOSAL_BUNDLE),
        BundleRef(BundleName.SPEC_BUNDLE),
        BundleRef(BundleName.DESIGN_BUNDLE),
        BundleRef(BundleName.TASKS_BUNDLE),
        BundleRef(BundleName.TDD_BUNDLE),
        BundleRef(BundleName.KNOWLEDGE_EXTRACT_TDD),
    ),
)
