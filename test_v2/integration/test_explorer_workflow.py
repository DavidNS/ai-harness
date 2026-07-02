from __future__ import annotations

import unittest

from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.lifecycle import BundleName, ExecutorKind, PhaseName


class ExplorerWorkflowIntegrationTests(unittest.TestCase):
    def test_explore_bundle_flattening_keeps_ai_and_deterministic_phases_ordered(self) -> None:
        steps = bundle_catalog.linearize_bundle(BundleName.EXPLORE_BUNDLE)

        self.assertEqual(PhaseName.EXPLORE_REQUEST_UNDERSTANDING, steps[0].phase_name)
        self.assertEqual(PhaseName.EXPLORE_HANDOFF, steps[-1].phase_name)
        self.assertEqual(ExecutorKind.AI_WORKER, steps[0].phase.executor)
        self.assertEqual(ExecutorKind.DETERMINISTIC_FUNCTION, steps[1].phase.executor)


if __name__ == "__main__":
    unittest.main()
