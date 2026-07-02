from __future__ import annotations

import unittest

from harness_v2.backend.application.phase_artifacts import explore
from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


class ExploreBundleIntegrationTests(unittest.TestCase):
    def test_explore_bundle_uses_shared_catalog_and_helpers(self) -> None:
        steps = bundle_catalog.linearize_bundle(BundleName.EXPLORE_BUNDLE)
        profile = {
            "schema_version": 1,
            "phase": "explore_request_profile",
            "summary": "Fix tests",
            "request_type": "feature",
            "complexity": "local_change",
            "ambiguity": "clear",
            "risk": "low",
            "evidence_depth": "standard",
            "request_parts": ["Fix tests"],
            "constraints": [],
            "evidence_questions": ["What fails?"],
            "gatherers": ["code"],
            "clarification_questions": [],
        }

        explore.validate_request_profile(profile)

        self.assertEqual(PhaseName.EXPLORE_REQUEST_UNDERSTANDING, steps[0].phase_name)
        self.assertEqual(PhaseName.EXPLORE_HANDOFF, steps[-1].phase_name)


if __name__ == "__main__":
    unittest.main()
