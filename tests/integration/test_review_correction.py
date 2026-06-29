from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.config import HarnessConfig
from ai_harness.orchestrator import Orchestrator
from tests.fixtures.flow import run_with_flow
from tests.fixtures.scripted_provider import ScriptedProvider


def write_analysis_artifact(repository: Path, name: str = "jwt-authentication.md") -> str:
    slug = Path(name).stem
    relative = Path("docs") / "explorer" / "improvements" / slug / "improvement.md"
    artifact = repository / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        "# Improvement Analysis v1\n## Problem\nImplement JWT authentication.\n## Context\nRequired by test.\n## Findings\nViable.\n## Options\nImplement.\n## Risks\nNone.\n## Recommendation\nProceed.\n## Outcome\nimprovement\n## Open Questions\nNone.\n",
        encoding="utf-8",
    )
    return str(relative)

class ReviewCorrectionIntegrationTests(unittest.TestCase):
    def test_requested_changes_require_correction_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            entry = write_analysis_artifact(repository)
            finding = f"{entry}: add the reviewer-requested correction."
            provider = ScriptedProvider(
                review_verdicts=("REQUEST_CHANGES", "APPROVE"),
                review_findings=(finding, "Correction accepted."),
            )
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                f"Implement {entry}",
                "sdd_high",
            )
            self.assertEqual("success", result.outcome)
            self.assertEqual(2, provider.calls.count("implement"))
            self.assertEqual(2, provider.calls.count("review"))
            self.assertEqual([], provider.phase_inputs["implement"][0]["prior_failures"])
            retry_failures = provider.phase_inputs["implement"][1]["prior_failures"]
            self.assertEqual(1, len(retry_failures))
            self.assertIn("review requested changes", retry_failures[0])
            self.assertIn(finding, retry_failures[0])

if __name__ == "__main__":
    unittest.main()
