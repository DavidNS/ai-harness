"""Offline checks for ARCHITECTURE.md as an agent-readable overview."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from doc_understanding_cases import CASES, READING_GUIDE


ARCHITECTURE = ROOT / "ARCHITECTURE.md"


def _architecture_text() -> str:
    return ARCHITECTURE.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    return match.group("body").strip()


def _plain(text: str) -> str:
    return " ".join(text.lower().split())


class ArchitectureDocOfflineTests(unittest.TestCase):
    def test_intro_preserves_agent_readable_overview_concepts(self) -> None:
        text = _architecture_text()
        intro = text.split("## Purpose", 1)[0]
        lower_intro = _plain(intro)

        expected_terms = (
            "ai coding harness",
            "software engineers and agents",
            "small, explicit boundaries",
            "split by domain",
            "ownership",
            "context",
            "validation",
            "hexagonal",
            "command-driven model-view-update",
            "intent",
            "state transitions",
            "backend effects",
        )

        missing = [term for term in expected_terms if term not in lower_intro]
        self.assertEqual([], missing)

    def test_intro_stays_compact_for_system_map_use(self) -> None:
        intro_lines = [
            line for line in _architecture_text().split("## Purpose", 1)[0].splitlines()
            if line.strip() and not line.startswith("#")
        ]

        self.assertLessEqual(len(intro_lines), 12)
        self.assertLessEqual(sum(len(line) for line in intro_lines), 900)

    def test_purpose_keeps_reproducibility_and_learning_boundary(self) -> None:
        purpose = _plain(_section(_architecture_text(), "Purpose"))

        for term in (
            "portable tool",
            "software engineering release lifecycle",
            "cli and ui",
            "python code",
            "codex/claude",
            "git ci",
            "deterministic",
            "ai workers",
            "reproducible",
            "one clear task",
            "one limited context",
            "the harness learns---not the model",
        ):
            self.assertIn(term, purpose)

    def test_overview_does_not_read_like_low_level_contract(self) -> None:
        intro_and_purpose = _architecture_text().split("## Three connected lifecycles", 1)[0]
        lower_text = _plain(intro_and_purpose)

        low_level_markers = (
            "request payload",
            "response schema",
            "database table",
            "class diagram",
            "method signature",
            "endpoint",
        )

        present = [marker for marker in low_level_markers if marker in lower_text]
        self.assertEqual([], present)

    def test_live_eval_cases_are_nonempty_and_scored_outside_the_model(self) -> None:
        self.assertGreaterEqual(len(CASES), 4)
        self.assertIn("system map", READING_GUIDE)

        for case in CASES:
            self.assertTrue(case.case_id)
            self.assertTrue(case.prompt)
            self.assertGreaterEqual(len(case.required_terms), 3)
            self.assertNotIn("score yourself", case.prompt.lower())


if __name__ == "__main__":
    unittest.main()
