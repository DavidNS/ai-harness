from __future__ import annotations

import unittest

from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.errors import DomainValidationError
from harness_v2.backend.domain.lifecycle import (
    BUNDLE_SPECS,
    BundleName,
    BundleRef,
    ExecutorKind,
    PhaseName,
    PhaseRef,
    PhaseSpec,
    TerminalState,
    bundle_spec,
)


class BundlePhaseSchemaTests(unittest.TestCase):
    def test_sdd_bundle_is_declarative_composition_of_bundles(self) -> None:
        spec = bundle_spec(BundleName.SDD_BUNDLE)

        self.assertTrue(spec.children)
        self.assertTrue(all(isinstance(child, BundleRef) for child in spec.children))
        self.assertEqual(
            (
                BundleName.EXPLORE_BUNDLE,
                BundleName.KNOWLEDGE_EXTRACT_EXPLORE,
                BundleName.PROPOSAL_BUNDLE,
                BundleName.SPEC_BUNDLE,
                BundleName.DESIGN_BUNDLE,
                BundleName.TASKS_BUNDLE,
                BundleName.TDD_BUNDLE,
                BundleName.KNOWLEDGE_EXTRACT_TDD,
            ),
            tuple(child.name for child in spec.children),
        )

    def test_explore_bundle_is_composed_of_phases(self) -> None:
        spec = bundle_spec(BundleName.EXPLORE_BUNDLE)

        self.assertTrue(all(isinstance(child, PhaseRef) for child in spec.children))
        self.assertEqual(
            (
                PhaseName.EXPLORE_REQUEST_UNDERSTANDING,
                PhaseName.EXPLORE_CONTEXT_PACK,
                PhaseName.EXPLORE_EVIDENCE_DIGEST,
                PhaseName.EXPLORE_EXPLORATION_MAP,
                PhaseName.EXPLORE_OUTCOME_SYNTHESIS,
                PhaseName.EXPLORE_HANDOFF,
            ),
            tuple(child.name for child in spec.children),
        )

    def test_phase_executors_are_ai_workers_or_deterministic_functions(self) -> None:
        steps = bundle_catalog.linearize_bundle(BundleName.EXPLORE_BUNDLE)

        self.assertEqual(
            (
                ExecutorKind.AI_WORKER,
                ExecutorKind.DETERMINISTIC_FUNCTION,
                ExecutorKind.AI_WORKER,
                ExecutorKind.DETERMINISTIC_FUNCTION,
                ExecutorKind.AI_WORKER,
                ExecutorKind.DETERMINISTIC_FUNCTION,
            ),
            tuple(step.phase.executor for step in steps),
        )

    def test_catalog_flattens_sdd_with_reused_validation_phases(self) -> None:
        steps = bundle_catalog.linearize_bundle(BundleName.SDD_BUNDLE)
        phase_names = tuple(step.phase_name for step in steps)

        self.assertEqual(25, len(phase_names))
        self.assertEqual(3, phase_names.count(PhaseName.VALIDATE_JSON))
        self.assertEqual(PhaseName.EXPLORE_REQUEST_UNDERSTANDING, phase_names[0])
        self.assertEqual(PhaseName.KNOWLEDGE_EXTRACT_TDD_PATCH, phase_names[-1])
        self.assertEqual(BundleName.EXPLORE_BUNDLE, steps[0].bundle_name)
        self.assertEqual(BundleName.SDD_BUNDLE, steps[0].root_bundle)

    def test_catalog_derives_next_parent_and_completed_bundles(self) -> None:
        first = bundle_catalog.start_step(BundleName.SDD_BUNDLE)
        second = bundle_catalog.next_after(BundleName.SDD_BUNDLE, first.phase_name)

        self.assertEqual(BundleName.EXPLORE_BUNDLE, first.bundle_name)
        self.assertEqual(PhaseName.EXPLORE_CONTEXT_PACK, second.phase_name)
        self.assertEqual(BundleName.EXPLORE_BUNDLE, bundle_catalog.parent_bundle(BundleName.SDD_BUNDLE, first.phase_name))
        completed = bundle_catalog.completed_bundles(BundleName.SDD_BUNDLE, tuple(bundle_catalog.phases(BundleName.EXPLORE_BUNDLE)))
        self.assertIn(BundleName.EXPLORE_BUNDLE, completed)
        self.assertNotIn(BundleName.PROPOSAL_BUNDLE, completed)

    def test_completed_prefix_must_be_ordered_and_unique(self) -> None:
        prefix = tuple(bundle_catalog.phases(BundleName.SDD_BUNDLE))[:2]
        bundle_catalog.validate_completed_prefix(BundleName.SDD_BUNDLE, prefix)

        with self.assertRaises(DomainValidationError):
            bundle_catalog.validate_completed_prefix(BundleName.SDD_BUNDLE, (PhaseName.PROPOSAL_PURPOSE,))
        with self.assertRaises(DomainValidationError):
            bundle_catalog.validate_completed_prefix(BundleName.SDD_BUNDLE, (prefix[0], prefix[0]))

    def test_specs_require_consistent_phase_metadata(self) -> None:
        with self.assertRaises(DomainValidationError):
            PhaseSpec(PhaseName.SPEC_DRAFT, ExecutorKind.AI_WORKER)
        with self.assertRaises(DomainValidationError):
            PhaseSpec(PhaseName.SPEC_HANDOFF, ExecutorKind.DETERMINISTIC_FUNCTION, "handoff")
        self.assertEqual(TerminalState.COMPLETED, TerminalState("COMPLETED"))
        self.assertEqual(set(BundleName), set(BUNDLE_SPECS))


if __name__ == "__main__":
    unittest.main()
