from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.config import HarnessConfig
from ai_harness.orchestrator import Orchestrator
from tests.fixtures.flow import run_with_route
from tests.fixtures.scripted_provider import ScriptedProvider


class NonCodeIntegrationTests(unittest.TestCase):
    def test_non_code_writes_only_stub_pipeline_artifacts_and_invokes_no_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ScriptedProvider()
            result = run_with_route(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Brainstorm market analysis ideas for a bakery",
                "non_code",
            )
            self.assertEqual([], provider.calls)
            self.assertEqual("non-code stub", result.outcome)
            self.assertIn("non_code.md", result.artifacts)
            self.assertNotIn("tasks.json", result.artifacts)
            self.assertTrue(result.snapshot_path.is_dir())


if __name__ == "__main__":
    unittest.main()
