from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "harness"
sys.path.insert(0, str(SCRIPTS))

from ai_harness.canonical import CanonicalDocs, checksum


COMPACT = """# Improvement: {title}
## Status
Proposed
## Problem
{problem}
## Evidence
{evidence}
## Desired Behavior
{desired}
## Implementation Notes
Keep the change focused.
## Acceptance Criteria
- The expected artifact path is discovered.
"""


class CanonicalDocsTests(unittest.TestCase):
    def test_list_improvements_includes_flat_and_nested_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            flat = root / "docs/explorer/improvements/flat-routing/improvement.md"
            nested = root / "docs/explorer/improvements/quality/layered-routing/improvement.md"
            for path, title in ((flat, "Flat Routing"), (nested, "Layered Routing")):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(COMPACT.format(
                    title=title,
                    problem=f"{title} is not discoverable.",
                    evidence=f"{path.name} records the fixture.",
                    desired=f"Discover {title}.",
                ), encoding="utf-8")

            docs = CanonicalDocs(root)

            self.assertEqual([
                "docs/explorer/improvements/flat-routing/improvement.md",
                "docs/explorer/improvements/quality/layered-routing/improvement.md",
            ], docs.list_improvements())

    def test_related_improvements_can_return_nested_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "docs/explorer/improvements/quality/layered-routing/improvement.md"
            nested.parent.mkdir(parents=True)
            content = COMPACT.format(
                title="Layered Routing",
                problem="Nested routing improvements are not matched.",
                evidence="docs/explorer/improvements/quality/layered-routing/improvement.md is the fixture.",
                desired="Match nested routing improvements.",
            )
            nested.write_text(content, encoding="utf-8")

            related = CanonicalDocs(root).related_improvements("layered routing", limit=5)

            self.assertEqual("docs/explorer/improvements/quality/layered-routing/improvement.md", related[0]["path"])
            self.assertEqual(checksum(content), related[0]["checksum"])


if __name__ == "__main__":
    unittest.main()
