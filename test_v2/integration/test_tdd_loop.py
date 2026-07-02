from __future__ import annotations

import json
import unittest

from harness_v2.backend.application.tdd_loop import parse_tdd_review


class TddPhaseIntegrationTests(unittest.TestCase):
    def test_tdd_review_parser_requires_structured_evidence(self) -> None:
        review = parse_tdd_review(json.dumps({
            "schema_version": 1,
            "kind": "tdd_review",
            "verdict": "APPROVE",
            "findings": ["ok"],
            "acceptance_criteria": ["criterion"],
            "test_evidence": {"focused": "passed"},
        }))

        self.assertEqual("APPROVE", review["verdict"])
        self.assertEqual({"focused": "passed"}, review["test_evidence"])


if __name__ == "__main__":
    unittest.main()
