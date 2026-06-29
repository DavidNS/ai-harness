"""Unit tests for the text helper modules.

These cover harness/ai_harness/text/markdown.py and text/normalize.py.
Pure functions — no mocking or fixtures needed.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.text.markdown import compact_lines, markdown_section, section_sentences, strip_code_block
from ai_harness.text.normalize import normalize_key, normalized_statement


class MarkdownSectionTests(unittest.TestCase):
    def test_extracts_section_body(self) -> None:
        doc = "## Problem\nSome problem.\n## Context\nSome context.\n"
        self.assertEqual("Some problem.", markdown_section(doc, "Problem"))

    def test_returns_empty_when_section_absent(self) -> None:
        self.assertEqual("", markdown_section("## Other\ntext", "Missing"))

    def test_stops_at_next_heading(self) -> None:
        doc = "## A\nline1\nline2\n## B\nother"
        self.assertEqual("line1\nline2", markdown_section(doc, "A"))

    def test_crlf_normalised(self) -> None:
        doc = "## Section\r\nvalue\r\n"
        self.assertEqual("value", markdown_section(doc, "Section"))

    def test_empty_section_body(self) -> None:
        doc = "## Empty\n## Next\ntext"
        self.assertEqual("", markdown_section(doc, "Empty"))


class StripCodeBlockTests(unittest.TestCase):
    def test_strips_fenced_block(self) -> None:
        self.assertEqual("code here", strip_code_block("```python\ncode here\n```"))

    def test_passthrough_plain_text(self) -> None:
        self.assertEqual("plain", strip_code_block("plain"))

    def test_incomplete_fence_unchanged(self) -> None:
        self.assertEqual("```nope", strip_code_block("```nope"))


class CompactLinesTests(unittest.TestCase):
    def test_strips_bullet_markers(self) -> None:
        self.assertEqual(("item a", "item b"), compact_lines("- item a\n* item b"))

    def test_strips_numbered_list(self) -> None:
        self.assertEqual(("first", "second"), compact_lines("1. first\n2) second"))

    def test_skips_blank_lines(self) -> None:
        self.assertEqual(("a", "b"), compact_lines("a\n\nb"))

    def test_returns_tuple(self) -> None:
        self.assertIsInstance(compact_lines("x"), tuple)


class SectionSentencesTests(unittest.TestCase):
    def test_splits_sentences(self) -> None:
        result = section_sentences("Hello world. How are you?")
        self.assertEqual(["Hello world.", "How are you?"], result)

    def test_keeps_bullet_items(self) -> None:
        result = section_sentences("- item one\n- item two")
        self.assertEqual(["- item one", "- item two"], result)

    def test_skips_blank_lines(self) -> None:
        result = section_sentences("line.\n\nother.")
        self.assertIn("line.", result)
        self.assertIn("other.", result)


class NormalizeKeyTests(unittest.TestCase):
    def test_lowercases_and_strips_punctuation(self) -> None:
        self.assertEqual("givencontext", normalize_key("Given / Context"))

    def test_alphanumeric_only(self) -> None:
        self.assertEqual("abc123", normalize_key("ABC-123!"))

    def test_empty_string(self) -> None:
        self.assertEqual("", normalize_key(""))


class NormalizedStatementTests(unittest.TestCase):
    def test_lowercases_tokens(self) -> None:
        self.assertEqual("the feature works", normalized_statement("The feature works."))

    def test_strips_punctuation(self) -> None:
        self.assertEqual("a b c", normalized_statement("A, B, C!"))

    def test_equal_statements_compare_equal(self) -> None:
        a = normalized_statement("The feature works correctly.")
        b = normalized_statement("the feature works correctly")
        self.assertEqual(a, b)
