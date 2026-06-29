import sys
import unittest
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parents[2] / "harness"
sys.path.insert(0, str(SCRIPTS))
from ai_harness.providers.base import ProviderResult
from ai_harness.router import route_request
class Fake:
 def __init__(self, outputs): self.outputs,self.calls=list(outputs),0
 def run_prompt(self,prompt,*,cwd,permissions=None): self.calls+=1; return ProviderResult(self.outputs.pop(0),"",0,0.01)
class RouterTests(unittest.TestCase):
 def test_clear_requests_stay_local(self):
  p=Fake([])
  bug=route_request("Investigate bug in api.py",provider=p)
  self.assertEqual(("code","debug_issue"),(bug.mode,bug.intent))
  improvement=route_request("Investigate draft-improvements/routing.md",provider=p)
  self.assertEqual(("code","explorer_request"),(improvement.mode,improvement.intent))
  self.assertEqual("code",route_request("Fix traceback in api.py and add tests",provider=p).mode)
  self.assertEqual("non_code",route_request("Brainstorm product ideas",provider=p).mode)
  self.assertEqual(0,p.calls)

 def test_mixed_improvement_wording_stays_explorer(self):
  d=route_request("investigate this repo and create an improvement that allows safer routing")
  self.assertEqual(("code","explorer_request"),(d.mode,d.intent))

 def test_full_sdd_nested_analysis_reference_is_detected(self):
  d=route_request("full implementation for docs/explorer/improvements/quality/layered-routing/improvement.md")
  self.assertEqual(("code","modify_code"),(d.mode,d.intent))
  self.assertIn("explorer_scope_reference",d.matched_signals)
 def test_ambiguous_requires_user_without_provider_classification(self):
  p=Fake(['{"mode":"code","intent":"build_software","confidence":0.8}'])
  d=route_request("Make something useful",provider=p,cwd=Path.cwd())
  self.assertEqual(("code","needs_user",0),(d.mode,d.source,p.calls))
 def test_invalid_provider_is_not_used_for_ambiguous_route(self):
  p=Fake(["bad","bad"]); d=route_request("Make something useful",provider=p,cwd=Path.cwd())
  self.assertEqual(("code","modify_code",0.0,0),(d.mode,d.intent,d.confidence,p.calls))
 def test_missing_provider_requires_user_for_ambiguous_route(self):
  d=route_request("Make something useful")
  self.assertEqual(("code","modify_code",0.0,"needs_user"),(d.mode,d.intent,d.confidence,d.source))
