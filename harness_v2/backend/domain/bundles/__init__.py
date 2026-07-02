"""Declarative v2 bundle compositions."""

from __future__ import annotations

from harness_v2.backend.domain.lifecycle import BundleName, BundleSpec

from .design import DESIGN_BUNDLE
from .explore import EXPLORE_BUNDLE
from .knowledge import KNOWLEDGE_EXTRACT_EXPLORE, KNOWLEDGE_EXTRACT_TDD
from .proposal import PROPOSAL_BUNDLE
from .sdd import SDD_BUNDLE
from .spec import SPEC_BUNDLE
from .tasks import TASKS_BUNDLE
from .tdd import TDD_BUNDLE

BUNDLE_SPECS: dict[BundleName, BundleSpec] = {
    SDD_BUNDLE.name: SDD_BUNDLE,
    EXPLORE_BUNDLE.name: EXPLORE_BUNDLE,
    KNOWLEDGE_EXTRACT_EXPLORE.name: KNOWLEDGE_EXTRACT_EXPLORE,
    PROPOSAL_BUNDLE.name: PROPOSAL_BUNDLE,
    SPEC_BUNDLE.name: SPEC_BUNDLE,
    DESIGN_BUNDLE.name: DESIGN_BUNDLE,
    TASKS_BUNDLE.name: TASKS_BUNDLE,
    TDD_BUNDLE.name: TDD_BUNDLE,
    KNOWLEDGE_EXTRACT_TDD.name: KNOWLEDGE_EXTRACT_TDD,
}
