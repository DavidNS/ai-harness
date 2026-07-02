from __future__ import annotations

import unittest

from harness_v2.backend.application.phase_executor import default_phase_function_registry
from harness_v2.backend.application.contracts import InvalidRunStateError
from harness_v2.backend.application.phase_executor import PhaseFunctionRegistry
from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


class PhaseFunctionRegistryTests(unittest.TestCase):
    def test_default_registry_contains_all_executable_sdd_phases(self) -> None:
        registry = default_phase_function_registry()

        for step in bundle_catalog.linearize_bundle(BundleName.SDD_BUNDLE):
            with self.subTest(bundle=step.bundle_name, phase=step.phase_name):
                handler = registry.get(step.phase_name)
                self.assertTrue(callable(handler))

    def test_missing_phase_lookup_fails_closed(self) -> None:
        registry = PhaseFunctionRegistry({})

        with self.assertRaises(InvalidRunStateError):
            registry.get(PhaseName.PROPOSAL_PURPOSE)

    def test_invalidation_rules_are_phase_scoped(self) -> None:
        rules = default_phase_function_registry().invalidation_rules()

        self.assertIn("published/explore-handoff.json", rules[PhaseName.EXPLORE_HANDOFF].artifacts)
        self.assertIn("workers/EXPLORE_BUNDLE/EXPLORE_REQUEST_UNDERSTANDING/", rules[PhaseName.EXPLORE_REQUEST_UNDERSTANDING].prefixes)
        self.assertIn("design.json", rules[PhaseName.DESIGN_DRAFT].artifacts)
        self.assertIn("tasks.json", rules[PhaseName.TASKS_DRAFT].artifacts)
        self.assertIn("published/tdd-results.json", rules[PhaseName.TDD_HANDOFF].artifacts)



if __name__ == "__main__":
    unittest.main()
