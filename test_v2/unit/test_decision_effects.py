from __future__ import annotations

import unittest

from harness_v2.backend.domain.decisions import DecisionAction, DecisionEffect, PendingDecision
from harness_v2.backend.domain.errors import DomainValidationError
from harness_v2.backend.domain.escalation import EscalationCategory
from harness_v2.backend.domain.lifecycle import PhaseName

TIMESTAMP = "2026-07-01T00:00:00+00:00"


class DecisionEffectTests(unittest.TestCase):
    def test_option_effect_maps_answer_to_escalation_category(self) -> None:
        decision = PendingDecision(
            "decision-1",
            PhaseName.TDD_BUNDLE,
            "Continue or redesign?",
            TIMESTAMP,
            options=("continue", "redesign"),
            effects=(DecisionEffect("redesign", DecisionAction.ESCALATE, EscalationCategory.DESIGN_GAP),),
        )

        self.assertEqual(DecisionAction.CONTINUE, decision.effect_for("continue").action)
        effect = decision.effect_for("redesign")
        self.assertEqual(DecisionAction.ESCALATE, effect.action)
        self.assertEqual(EscalationCategory.DESIGN_GAP, effect.category)

    def test_open_ended_decision_can_default_to_escalation(self) -> None:
        decision = PendingDecision(
            "decision-1",
            PhaseName.EXPLORER_DECISION,
            "Clarify direction",
            TIMESTAMP,
            default_action=DecisionAction.ESCALATE,
            default_category=EscalationCategory.EXPLORATION_GAP,
        )

        effect = decision.effect_for("Look at auth flow")

        self.assertEqual("Look at auth flow", effect.option)
        self.assertEqual(DecisionAction.ESCALATE, effect.action)
        self.assertEqual(EscalationCategory.EXPLORATION_GAP, effect.category)

    def test_effects_must_match_options_and_action_targets(self) -> None:
        invalid_cases = (
            lambda: DecisionEffect("redesign", DecisionAction.ESCALATE),
            lambda: DecisionEffect("continue", DecisionAction.CONTINUE, EscalationCategory.DESIGN_GAP),
            lambda: PendingDecision(
                "decision-1",
                PhaseName.TDD_BUNDLE,
                "Continue?",
                TIMESTAMP,
                options=("continue",),
                effects=(DecisionEffect("redesign", DecisionAction.ESCALATE, EscalationCategory.DESIGN_GAP),),
            ),
            lambda: PendingDecision(
                "decision-1",
                PhaseName.TDD_BUNDLE,
                "Continue?",
                TIMESTAMP,
                default_action=DecisionAction.ESCALATE,
            ),
        )

        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises(DomainValidationError):
                    create()


if __name__ == "__main__":
    unittest.main()
