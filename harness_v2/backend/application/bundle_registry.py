"""Default SDD bundle registry construction."""

from __future__ import annotations

from harness_v2.backend.application.bundle_orchestration import BundleRegistry
from harness_v2.backend.application.bundles import (
    DesignBundleDefinition,
    ExploreBundleDefinition,
    explorer_bundle_definitions,
    knowledge_bundle_definitions,
    ProposalBundleDefinition,
    SpecBundleDefinition,
    TasksBundleDefinition,
    TddBundleDefinition,
)


def default_bundle_registry(tdd_loop: object | None = None) -> BundleRegistry:
    registry = BundleRegistry(
        (
            ExploreBundleDefinition(),
            knowledge_bundle_definitions()[0],
            ProposalBundleDefinition(),
            SpecBundleDefinition(),
            DesignBundleDefinition(),
            TasksBundleDefinition(),
            TddBundleDefinition(tdd_loop=tdd_loop),
            knowledge_bundle_definitions()[1],
            *explorer_bundle_definitions(),
        )
    )
    registry.validate_sdd_coverage()
    return registry
