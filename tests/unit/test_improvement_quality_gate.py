"""Unit tests for ImprovementQualityGate."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.orchestrator.quality import ImprovementQualityGate


def _entry(entry_id="E001", title="Test entry", action="create", artifact_kind="improvement"):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.title = title
    entry.action = action
    entry.artifact_kind = artifact_kind
    return entry


class IsCompactImprovementTests(unittest.TestCase):
    gate = ImprovementQualityGate()

    def test_valid_header(self):
        self.assertTrue(self.gate.is_compact_improvement("# Improvement: Fix the thing\nsome body"))

    def test_empty_string(self):
        self.assertFalse(self.gate.is_compact_improvement(""))

    def test_wrong_header(self):
        self.assertFalse(self.gate.is_compact_improvement("# Fix the thing\nbody"))


class IsGenericEvidenceTests(unittest.TestCase):
    gate = ImprovementQualityGate()

    def test_short_text_is_generic(self):
        self.assertTrue(self.gate.is_generic_evidence("none"))

    def test_concrete_reference_not_generic(self):
        self.assertFalse(self.gate.is_generic_evidence("see `src/foo.py` for the implementation"))

    def test_none_literal(self):
        self.assertTrue(self.gate.is_generic_evidence("none"))

    def test_n_a_literal(self):
        self.assertTrue(self.gate.is_generic_evidence("n/a"))


class CriterionIsObservableTests(unittest.TestCase):
    gate = ImprovementQualityGate()

    def test_short_line_not_observable(self):
        self.assertFalse(self.gate.criterion_is_observable("ok"))

    def test_desired_behavior_phrase_not_observable(self):
        self.assertFalse(self.gate.criterion_is_observable("desired behavior is described in the docs"))

    def test_observable_criterion(self):
        self.assertTrue(self.gate.criterion_is_observable("the CLI prints a success message on stdout"))


class ValidateAcceptanceCriteriaTests(unittest.TestCase):
    gate = ImprovementQualityGate()

    def test_empty_section_fails(self):
        self.assertFalse(self.gate.validate_acceptance_criteria(""))

    def test_bullet_with_observable_criterion_passes(self):
        self.assertTrue(self.gate.validate_acceptance_criteria(
            "- the system logs an error message to stderr"
        ))

    def test_bullet_with_desired_behavior_phrase_fails(self):
        self.assertFalse(self.gate.validate_acceptance_criteria(
            "- desired behavior is met"
        ))


class EvidenceReferencesObservationTests(unittest.TestCase):
    gate = ImprovementQualityGate()

    def test_matches_file_path(self):
        obs = [{"path": "src/service.py"}]
        self.assertTrue(self.gate.evidence_references_repository_observation(
            "see src/service.py for details", obs
        ))

    def test_no_match_returns_false(self):
        obs = [{"path": "src/other.py"}]
        self.assertFalse(self.gate.evidence_references_repository_observation(
            "unrelated evidence text", obs
        ))

    def test_empty_observations_returns_false(self):
        self.assertFalse(self.gate.evidence_references_repository_observation("any text", []))


class ValidateCompactImprovementQualityTests(unittest.TestCase):
    gate = ImprovementQualityGate()

    GOOD_CONTENT = (
        "# Improvement: Add retry logic\n"
        "## Evidence\nsee `src/client.py` for the failed call\n"
        "## Problem\nRequests fail without retry.\n"
        "## Desired Behavior\nRequests are retried up to three times.\n"
        "## Acceptance Criteria\n- the system retries the request three times on failure\n"
    )

    def test_good_content_passes(self):
        self.gate.validate_compact_improvement_quality(self.GOOD_CONTENT, _entry())

    def test_legacy_entry_skipped(self):
        self.gate.validate_compact_improvement_quality("anything", _entry(entry_id="legacy"))

    def test_documentation_task_skipped(self):
        self.gate.validate_compact_improvement_quality("anything", _entry(action="documentation_task"))

    def test_generic_evidence_raises(self):
        from ai_harness.errors import HarnessError
        content = (
            "# Improvement: X\n## Evidence\nn/a\n## Problem\nA.\n"
            "## Desired Behavior\nB.\n## Acceptance Criteria\n- something observable here\n"
        )
        with self.assertRaises(HarnessError):
            self.gate.validate_compact_improvement_quality(content, _entry())
