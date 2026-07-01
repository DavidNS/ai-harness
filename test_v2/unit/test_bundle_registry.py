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

    def test_invalidation_rules_are_derived_from_registered_bundles(self) -> None:
        rules = default_bundle_registry().invalidation_rules()

        self.assertIn("published/explore-handoff.json", rules[PhaseName.EXPLORE_BUNDLE].artifacts)
        self.assertIn("explore/", rules[PhaseName.EXPLORE_BUNDLE].prefixes)
        self.assertIn("design.md", rules[PhaseName.DESIGN_BUNDLE].artifacts)
        self.assertIn("tasks.json", rules[PhaseName.TASKS_BUNDLE].artifacts)



if __name__ == "__main__":
    unittest.main()
