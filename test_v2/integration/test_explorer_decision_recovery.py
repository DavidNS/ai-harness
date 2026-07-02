from __future__ import annotations

import unittest

from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.lifecycle import BundleName, BundleRef, PhaseRef, bundle_spec


class ExplorerDecisionRecoveryTests(unittest.TestCase):
    def test_there_is_one_explore_bundle_composed_of_phases(self) -> None:
        sdd = bundle_spec(BundleName.SDD_BUNDLE)
        explore = bundle_spec(BundleName.EXPLORE_BUNDLE)

        self.assertEqual(1, [child.name for child in sdd.children].count(BundleName.EXPLORE_BUNDLE))
        self.assertTrue(all(isinstance(child, BundleRef) for child in sdd.children))
        self.assertTrue(all(isinstance(child, PhaseRef) for child in explore.children))
        self.assertEqual(BundleName.EXPLORE_BUNDLE, bundle_catalog.start_step(BundleName.SDD_BUNDLE).bundle_name)


if __name__ == "__main__":
    unittest.main()
