import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"harness"))
from ai_harness.strategy import (
    StrategyOverrideError,
    finalize_strategy_decision,
    parse_strategy_override,
    select_strategy,
)


class StrategyTests(unittest.TestCase):
 def test_low(self):
  d=select_strategy("Fix a typo in README.md"); self.assertEqual(("LOW","SDD"),(d.complexity,d.strategy))
 def test_medium(self):
  d=select_strategy("Add a bounded search endpoint"); self.assertEqual(("MEDIUM","SDD"),(d.complexity,d.strategy))
 def test_high(self):
  d=select_strategy("Redesign authentication across services"); self.assertEqual(("HIGH","SDD"),(d.complexity,d.strategy))
 def test_design_and_testing_high(self):
  d=select_strategy("Design caching and add testing"); self.assertEqual("HIGH",d.complexity); self.assertIn("design_and_testing",d.matched_signals)
 def test_controller_workflow_changes_bias_to_full_sdd(self):
  d=select_strategy("Update orchestrator routing resume state handling")
  self.assertEqual(("MEDIUM","SDD"),(d.complexity,d.strategy))
  self.assertIn("controller_orchestration",d.matched_signals)
  self.assertTrue(d.confirmation_required)
 def test_artifact_contract_and_decision_gate_are_high(self):
  d=select_strategy("Change the artifact contract for decision gates")
  self.assertEqual(("HIGH","SDD"),(d.complexity,d.strategy))
  self.assertFalse(d.confirmation_required)
 def test_draft_improvement_path_uses_explorer_by_default(self):
  d=select_strategy("Implement draft-improvements/strategy-selection-robustness.md")
  self.assertEqual(("MEDIUM","EXPLORER"),(d.complexity,d.strategy))
  self.assertIn("explorer_request",d.matched_signals)
 def test_trivial_draft_edit_can_remain_simple(self):
  d=select_strategy("Fix a typo in draft-improvements/strategy-selection-robustness.md")
  self.assertEqual(("LOW","SDD"),(d.complexity,d.strategy))
 def test_override_aliases(self):
  self.assertEqual("SDD_LOW",parse_strategy_override("simple"))
  self.assertEqual("SDD_MEDIUM",parse_strategy_override("sdd"))
  self.assertEqual("SDD_MEDIUM",parse_strategy_override("sdd"))
  self.assertEqual("EXPLORER",parse_strategy_override("explorer"))
  self.assertIsNone(parse_strategy_override("\n"))
  with self.assertRaises(StrategyOverrideError):
   parse_strategy_override("maybe")
 def test_finalize_records_simple_override_audit(self):
  recommendation=select_strategy("Update orchestrator routing")
  final=finalize_strategy_decision(recommendation,answer="simple",prompted=True)
  self.assertEqual(("LOW","SDD"),(final.complexity,final.strategy))
  self.assertEqual("SDD",final.recommended_strategy)
  self.assertEqual("MEDIUM",final.recommended_complexity)
  self.assertTrue(final.overridden)
  self.assertEqual("prompt_override",final.selection_source)
  self.assertEqual("simple",final.override_text)

if __name__ == "__main__":
 unittest.main()
