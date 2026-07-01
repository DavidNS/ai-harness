"""Default SDD bundle registry construction."""

from __future__ import annotations

from harness_v2.backend.application.bundle_orchestration import BundleRegistry
from harness_v2.backend.application.bundles import (
    DesignBundleDefinition,
    ExploreBundleDefinition,
    explorer_bundle_definitions,
    ProposalBundleDefinition,
    SpecBundleDefinition,
    TasksBundleDefinition,
    TddBundleDefinition,
)


def default_bundle_registry() -> BundleRegistry:
    registry = BundleRegistry(
        (
            ExploreBundleDefinition(),
            ProposalBundleDefinition(),
            SpecBundleDefinition(),
            DesignBundleDefinition(),
            TasksBundleDefinition(),
            TddBundleDefinition(),
            *explorer_bundle_definitions(),
        )
    )
    registry.validate_sdd_coverage()
    return registry
