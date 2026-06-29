from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import install


class ActivationContractAcceptanceTests(unittest.TestCase):
    def test_provider_bootstraps_preserve_request_and_prevent_recursion(self) -> None:
        for provider in ("codex", "claude"):
            with self.subTest(provider=provider):
                text = install.bootstrap_content(ROOT, provider)
                normalized = " ".join(text.split())
                self.assertIn("first substantive top-level user request", normalized)
                self.assertIn("exactly once", normalized)
                self.assertIn("original request", normalized)
                self.assertIn("current working directory", normalized)
                self.assertIn(f"`{provider}` as the provider", normalized)
                self.assertIn("Do not summarize or rewrite", normalized)
                self.assertIn("do not activate it recursively", normalized)
                self.assertIn("explicitly asks to bypass", normalized)
                self.assertIn("explicitly invoke", normalized)

    def test_old_skill_entrypoint_is_removed(self) -> None:
        self.assertFalse((ROOT / "harness" / "SKILL.md").exists())
        self.assertTrue((ROOT / "harness" / "run.py").is_file())
        self.assertTrue((ROOT / "harness" / "ai_harness").is_dir())


if __name__ == "__main__":
    unittest.main()
