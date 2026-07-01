from __future__ import annotations

import unittest

from harness_v2.backend.application.bundle_orchestration import BundleRegistry
from harness_v2.backend.application.bundle_registry import default_bundle_registry
from harness_v2.backend.application.bundles import ExploreBundleDefinition
from harness_v2.backend.application.contracts import InvalidRunStateError
from harness_v2.backend.domain.lifecycle import EXPLORER_PHASES, PhaseName, SDD_PHASES


class BundleRegistryTests(unittest.TestCase):
    def test_default_registry_contains_all_sdd_phases(self) -> None:
        registry = default_bundle_registry()

        phases = set(registry.phases())
        self.assertTrue(set(SDD_PHASES).issubset(phases))
        self.assertTrue(set(EXPLORER_PHASES).issubset(phases))

    def test_duplicate_phase_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            BundleRegistry((ExploreBundleDefinition(), ExploreBundleDefinition()))

    def test_missing_phase_lookup_fails_closed(self) -> None:
        registry = BundleRegistry((ExploreBundleDefinition(),))

        with self.assertRaises(InvalidRunStateError):
            registry.get(PhaseName.PROPOSAL_BUNDLE)


if __name__ == "__main__":
    unittest.main()
