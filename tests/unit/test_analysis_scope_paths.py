from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from ai_harness.explorer_scope_paths import (
    explorer_scope_policy_error,
    is_improvement_artifact_path,
    is_published_explorer_manifest,
    normalize_relative_path,
    repository_relative_path,
)


class ExplorerScopePathTests(unittest.TestCase):
    def test_normalize_relative_path_rejects_empty_absolute_and_parent_paths(self) -> None:
        self.assertEqual("docs/explorer/improvements/a", normalize_relative_path("docs/explorer/improvements/a/"))
        for value in ("", "/tmp/scope", "docs/../secrets"):
            with self.assertRaises(ValueError):
                normalize_relative_path(value)

    def test_policy_accepts_improvement_scopes_and_root_manifest(self) -> None:
        self.assertIsNone(explorer_scope_policy_error("docs/explorer/improvements"))
        self.assertIsNone(explorer_scope_policy_error("docs/explorer/improvements/a/improvement.md"))
        self.assertIsNone(explorer_scope_policy_error("published/explorer.json"))
        self.assertIsNotNone(explorer_scope_policy_error("docs"))
        self.assertTrue(is_improvement_artifact_path("docs/explorer/improvements/a/improvement.md"))
        self.assertTrue(is_published_explorer_manifest("published/explorer.json"))
        self.assertTrue(is_published_explorer_manifest("archive/published/explorer.json", allow_nested=True))
        self.assertFalse(is_published_explorer_manifest("archive/published/explorer.json"))

    def test_repository_relative_path_stays_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = repository_relative_path(root, "docs/explorer/improvements/a/improvement.md")

        self.assertEqual(root / "docs" / "explorer" / "improvements" / "a" / "improvement.md", candidate)
        with self.assertRaises(ValueError):
            repository_relative_path(root, "../outside")


if __name__ == "__main__":
    unittest.main()
