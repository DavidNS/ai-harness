from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CliIntegrationTests(unittest.TestCase):
    def test_cli_module_starts_simulated_run(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", "-m", "harness_v2.frontends.cli", "start", "Fix", "tests"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("Run: ", completed.stdout)
        self.assertIn("Status: COMPLETED", completed.stdout)
        self.assertIn("Event: RunStarted", completed.stdout)
        self.assertIn("Event: PhaseStarted phase=SIMULATED", completed.stdout)
        self.assertIn("Event: PhaseCompleted phase=SIMULATED", completed.stdout)
        self.assertIn("Event: RunCompleted", completed.stdout)


if __name__ == "__main__":
    unittest.main()

