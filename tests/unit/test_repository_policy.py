from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_harness.errors import ConfigurationError
from ai_harness.repository_policy import load_repository_policy


class RepositoryPolicyTests(unittest.TestCase):
    def test_defaults_ignore_common_generated_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = load_repository_policy(Path(directory))

        for path in (
            ".pytest_cache/v/cache/nodeids",
            "pkg/__pycache__/mod.cpython-312.pyc",
            "target/classes/App.class",
            ".gradle/cache/state.bin",
            "node_modules/pkg/index.js",
            "coverage/index.html",
            "build/output.log",
            "dist/app.whl",
        ):
            with self.subTest(path=path):
                self.assertTrue(policy.ignores(path))

        self.assertFalse(policy.ignores("src/app.py"))

    def test_repo_config_adds_paths_and_globs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ai-harness.yml").write_text(
                "ignore:\n"
                "  paths:\n"
                "    - generated/reports/\n"
                "  globs:\n"
                "    - '*.tmp'\n",
                encoding="utf-8",
            )
            policy = load_repository_policy(root)

        self.assertTrue(policy.ignores("generated/reports/out.json"))
        self.assertTrue(policy.ignores("notes/output.tmp"))
        self.assertFalse(policy.ignores("generated/source.py"))

    def test_repo_config_accepts_empty_inline_lists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ai-harness.yml").write_text("ignore:\n  paths: []\n  globs: []\n", encoding="utf-8")
            policy = load_repository_policy(root)

        self.assertTrue(policy.ignores("__pycache__/x.pyc"))

    def test_malformed_repo_config_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ai-harness.yml").write_text("ignore:\n  paths:\n  - bad-indent\n", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_repository_policy(root)


if __name__ == "__main__":
    unittest.main()
