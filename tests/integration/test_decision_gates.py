from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ai_harness.config import HarnessConfig
from ai_harness.errors import StateError
from ai_harness.orchestrator import Orchestrator
from ai_harness.providers.base import ProviderResult
from ai_harness.stores.state import StateStore
from tests.fixtures.flow import run_with_flow
from tests.fixtures.scripted_provider import MARKDOWN, ScriptedProvider


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "harness" / "run.py"


def decision_request(origin: str) -> str:
    return json.dumps({
        "schema_version": 1,
        "kind": "decision_request",
        "origin_phase": origin,
        "reason": "The implementation has two viable approaches.",
        "question": "Should compatibility be preserved?",
        "context": ["Preserving compatibility is lower risk."],
        "options": [{"id": "preserve", "label": "Preserve", "consequence": "Adapter code is required."}],
        "allows_freeform": True,
    })


def write_analysis_artifact(repository: Path, name: str = "jwt-authentication.md") -> str:
    slug = Path(name).stem
    relative = Path("docs") / "explorer" / "improvements" / slug / "improvement.md"
    artifact = repository / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        "# Improvement Analysis v1\n## Problem\nImplement JWT authentication.\n## Context\nRequired by test.\n## Findings\nViable.\n## Options\nImplement.\n## Risks\nNone.\n## Recommendation\nProceed.\n## Outcome\nimprovement\n## Open Questions\nNone.\n",
        encoding="utf-8",
    )
    return str(relative)

class InterruptOnExplore:
    def __init__(self) -> None:
        self.delegate = ScriptedProvider()

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explore Request Understanding Worker v1" in prompt:
            raise KeyboardInterrupt("simulated interruption")
        return self.delegate.run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class DesignDecisionProvider(ScriptedProvider):
    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Design Worker v1" in prompt and self.counts["design"] == 0:
            self.calls.append("design")
            self.counts["design"] += 1
            return ProviderResult(decision_request("DESIGN"), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class EscalatingDesignProvider(ScriptedProvider):
    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Design Worker v1" in prompt:
            self.calls.append("design")
            index = self.counts["design"]
            self.counts["design"] += 1
            if index == 0:
                return ProviderResult(decision_request("DESIGN"), "", 0, 0.001)
            if index == 1:
                return ProviderResult(json.dumps({
                    "schema_version": 1,
                    "kind": "phase_escalation",
                    "origin_phase": "DESIGN",
                    "target_phase": "SPEC",
                    "reason": "The answer changes an acceptance criterion.",
                }), "", 0, 0.001)
            return ProviderResult(MARKDOWN["design"], "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class ImpossibleImplementProvider(ScriptedProvider):
    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Implement Worker v1" in prompt:
            self.calls.append("implement")
            self.counts["implement"] += 1
            (cwd / "feature.py").write_text("partial\n", encoding="utf-8")
            return ProviderResult(json.dumps({
                "schema_version": 1,
                "kind": "impossible",
                "origin_phase": "IMPLEMENT",
                "reason": "The requested behavior depends on an unavailable service.",
                "evidence": ["No provider abstraction exists for that service."],
                "remaining_options": ["Change the requirement."],
            }), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class RepairableImplementEscalationProvider(ScriptedProvider):
    def __init__(self) -> None:
        super().__init__()
        self.implement_prompts: list[str] = []
        self.tasks_prompts: list[str] = []

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Tasks Worker v1" in prompt:
            self.tasks_prompts.append(prompt)
        if "# Implement Worker v1" in prompt:
            self.implement_prompts.append(prompt)
            self.calls.append("implement")
            index = self.counts["implement"]
            self.counts["implement"] += 1
            if index == 0:
                return ProviderResult(json.dumps({
                    "schema_version": 1,
                    "kind": "phase_escalation",
                    "origin_phase": "IMPLEMENTING",
                    "target_phase": "TASK_SELECTION",
                    "reason": "The task scope is missing a required file.",
                }), "", 0, 0.001)
            if index == 1:
                return ProviderResult(json.dumps({
                    "schema_version": 1,
                    "kind": "phase_escalation",
                    "origin_phase": "IMPLEMENT",
                    "target_phase": "TASKS",
                    "reason": "The task scope is missing a required file.",
                }), "", 0, 0.001)
            (cwd / "feature.py").write_text("ready\n", encoding="utf-8")
            return ProviderResult(MARKDOWN["implement"], "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class DecisionGateIntegrationTests(unittest.TestCase):

    def test_answer_for_active_resume_is_rejected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            request = f"Implement {write_analysis_artifact(repository)}"
            with self.assertRaises(KeyboardInterrupt):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), InterruptOnExplore()),
                    request,
                    "sdd_high",
                )
            state_path = repository / ".ai-harness/artifacts/current/state.json"
            before = state_path.read_bytes()
            active = StateStore(repository).load()
            self.assertEqual("active", active.status.value)

            with self.assertRaises(StateError):
                Orchestrator(repository, HarnessConfig(provider="local"), ScriptedProvider()).run(
                    request,
                    resume_run_id=active.run_id,
                    decision_answer="This should not be accepted for an active run.",
                )

            self.assertEqual(before, state_path.read_bytes())
            self.assertEqual("active", StateStore(repository).load().status.value)

    def test_design_decision_waits_then_answer_resume_completes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = DesignDecisionProvider()
            request = f"Implement {write_analysis_artifact(repository)}"
            waiting = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                request,
                "sdd_high",
            )

            self.assertEqual("waiting_for_user", waiting.outcome)
            state = StateStore(repository).load()
            self.assertEqual("waiting_for_user", state.status.value)
            self.assertEqual("DESIGN_BUNDLE", state.current_phase)
            assert state.pending_decision is not None
            decision_id = state.pending_decision.id
            self.assertIn(f"decisions/{decision_id}/request.json", waiting.artifacts)

            completed = Orchestrator(repository, HarnessConfig(provider="local"), provider).run(
                request,
                resume_run_id=waiting.run_id,
                decision_answer=json.dumps({
                    "schema_version": 1,
                    "kind": "decision_answer",
                    "decision_id": decision_id,
                    "answer": "Preserve compatibility.",
                    "selected_option": "preserve",
                }),
            )

            self.assertEqual("success", completed.outcome)
            self.assertTrue(completed.snapshot_path.is_dir())
            self.assertIsNotNone(completed.snapshot_path)
            self.assertTrue((completed.snapshot_path / f"decisions/{decision_id}/answer.json").is_file())
            self.assertGreaterEqual(provider.calls.count("design"), 2)

    def test_resume_without_answer_reports_decision_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = DesignDecisionProvider()
            request = f"Implement {write_analysis_artifact(repository)}"
            waiting = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                request,
                "sdd_high",
            )
            state_path = repository / ".ai-harness/artifacts/current/state.json"
            before = state_path.read_bytes()

            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--provider", "local", "--resume", waiting.run_id],
                input="",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("## Decision Required", completed.stdout)
            state = StateStore(repository).load()
            assert state.pending_decision is not None
            self.assertIn(f"Decision ID: {state.pending_decision.id}", completed.stdout)
            self.assertEqual(before, state_path.read_bytes())

    def test_resumed_phase_can_escalate_to_spec_and_regenerate_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = EscalatingDesignProvider()
            request = f"Implement {write_analysis_artifact(repository)}"
            waiting = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                request,
                "sdd_high",
            )
            state = StateStore(repository).load()
            assert state.pending_decision is not None
            completed = Orchestrator(repository, HarnessConfig(provider="local"), provider).run(
                request,
                resume_run_id=waiting.run_id,
                decision_answer=json.dumps({
                    "schema_version": 1,
                    "kind": "decision_answer",
                    "decision_id": state.pending_decision.id,
                    "answer": "Update the spec before designing.",
                }),
            )

            self.assertEqual("success", completed.outcome)
            self.assertEqual(2, provider.calls.count("spec"))
            self.assertEqual(3, provider.calls.count("design"))
            self.assertIsNotNone(completed.snapshot_path)
            self.assertTrue((completed.snapshot_path / "escalations/E1.json").is_file())

    def test_invalid_implement_escalation_is_repaired_and_regenerates_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = RepairableImplementEscalationProvider()
            request = f"Implement {write_analysis_artifact(repository)}"

            completed = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                request,
                "sdd_high",
            )

            self.assertEqual("success", completed.outcome)
            self.assertEqual(2, provider.calls.count("tasks"))
            self.assertEqual(3, provider.calls.count("implement"))
            self.assertIsNotNone(completed.snapshot_path)
            self.assertTrue((completed.snapshot_path / "escalations/E1.json").is_file())
            self.assertGreaterEqual(len(provider.tasks_prompts), 2)
            regenerated_tasks_prompt = provider.tasks_prompts[1]
            self.assertIn('"escalation_history"', regenerated_tasks_prompt)
            self.assertIn('"origin_phase": "IMPLEMENT"', regenerated_tasks_prompt)
            self.assertIn('"target_phase": "TASKS_BUNDLE"', regenerated_tasks_prompt)
            self.assertIn('The task scope is missing a required file.', regenerated_tasks_prompt)
            repair_prompt = provider.implement_prompts[1]
            self.assertIn('\"repair\"', repair_prompt)
            self.assertIn('\"expected_origin\": \"IMPLEMENT\"', repair_prompt)
            self.assertIn('\"TASKS_BUNDLE\"', repair_prompt)
            self.assertEqual("ready\n", (repository / "feature.py").read_text(encoding="utf-8"))

    def test_implement_impossible_is_failed_and_rolls_back_partial_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ImpossibleImplementProvider()
            with self.assertRaisesRegex(Exception, "impossible is only valid"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), provider),
                    f"Implement {write_analysis_artifact(repository)}",
                    "sdd",
                )

            self.assertFalse((repository / "feature.py").exists())
            state = StateStore(repository).load()
            self.assertEqual("failed", state.status.value)
            self.assertEqual("FAILED", state.current_phase)
            self.assertNotIn("impossible.json", state.artifacts)

    def test_launcher_answer_file_records_answer_and_resumes_waiting_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider_script = repository / "claude"
            provider_script.write_text(
                """#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import sys

def explore_bundle():
    return json.dumps({
        "schema_version": 1,
        "kind": "explore_outcome_bundle",
        "status": "ready_for_purpose",
        "normalized_request": {"summary": "Implement the request."},
        "triage": {"complexity": "local_change", "ambiguity": "clear", "risk": "low", "evidence_depth": "standard"},
        "evidence": [{"id": "E1", "claim": "The fixture request is bounded.", "status": "supported", "confidence": "high", "sources": [{"type": "knowledge", "description": "Fixture evidence."}]}],
        "entries": [{"id": "entry-1", "classification": "improvement", "title": "Implement the request", "problem": "The bounded request should be implemented.", "evidence_refs": ["E1"], "constraints": ["Offline fixture."], "unknowns": []}],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\\n"

STAGES = {
    "Explore Request Understanding": json.dumps({"schema_version": 1, "phase": "explore_request_understanding", "intent": "implement_request", "summary": "Implement the request.", "mentioned_surfaces": [], "explicit_constraints": [], "unclear_parts": [], "request_type": "feature"}),
    "Explore Clarification Gate": json.dumps({"schema_version": 1, "phase": "explore_clarification_gate", "status": "continue", "clarification_questions": [], "rationale": "The request is bounded."}),
    "Explore Triage": json.dumps({"schema_version": 1, "phase": "explore_triage", "complexity": "local_change", "ambiguity": "clear", "novelty": "known_repo_pattern", "risk": "low", "evidence_depth": "standard", "rationale": "Small deterministic fixture."}),
    "Explore Evidence Plan": json.dumps({"schema_version": 1, "phase": "explore_evidence_plan", "required_gatherers": ["code", "knowledge"], "optional_gatherers": ["ci"], "ci_requirement": "optional", "questions": ["Is the request bounded?"], "skip_reason": {"web": "No external current fact is required."}}),
    "Explore Evidence Collection": json.dumps({"schema_version": 1, "phase": "explore_evidence_collection", "evidence": [{"id": "R1", "claim": "The fixture request is bounded.", "status": "supported", "confidence": "high", "sources": [{"type": "knowledge", "description": "Fixture evidence."}]}], "blockers": []}),
    "Explore Ci Barrier": json.dumps({"schema_version": 1, "phase": "explore_ci_barrier", "ci_requirement": "optional", "status": "ready", "evidence": [], "blockers": []}),
    "Explore Evidence Normalization": json.dumps({"schema_version": 1, "phase": "explore_evidence_normalization", "evidence": [{"id": "E1", "claim": "The fixture request is bounded.", "status": "supported", "confidence": "high", "sources": [{"type": "knowledge", "description": "Fixture evidence."}]}]}),
    "Explore Outcome Synthesis": explore_bundle(),
    "Explore Review": "# Review v1\\n## Verdict\\nAPPROVE\\n## Findings\\nThe bundle is valid.\\n",
}

MARKDOWN = {
    "explore": explore_bundle(),
    "purpose": "# Purpose v1\\n## Problem\\nImplement the request.\\n## Scope\\nOne bounded change.\\n## Approach\\nUse controller gates.\\n## Exclusions\\nNo unrelated work.\\n## Acceptance Outline\\nTests pass.\\n",
    "spec": "# Spec v1\\n## Behavioral Requirements\\nThe feature works.\\n## Acceptance Criteria\\nController tests pass.\\n",
    "design": "# Design v1\\n## Boundaries\\nRepository only.\\n## Invariants\\nController owns state.\\n## Implementation Approach\\nWrite feature.py.\\n## Unit Test Design\\nCheck content.\\n## Integration Test Design\\nRun a process.\\n## End-to-End Test Design\\nComplete the pipeline.\\n",
    "implement": "# Implementation v1\\n## Changes\\nUpdated feature.py.\\n## Evidence\\nController tests must verify it.\\n",
    "learning": json.dumps({
        "schema_version": 1,
        "phase": "learning",
        "proposal_manifest": {
            "schema_version": 1,
            "proposal_id": "proposal.deterministic-offline-completion.001",
            "summary": "Completed offline.",
            "source_artifacts": ["implementation/T1/1.md"],
            "claims_file": "proposed_claims.jsonl",
        },
        "proposed_claims": [{
            "id": "claim.deterministic-offline-completion.001",
            "domain": "harness",
            "subjects": ["DeterministicOfflineCompletion"],
            "files": ["feature.py"],
            "symbols": [],
            "claim_type": "responsibility",
            "text": "feature.py records the deterministic offline completion fixture behavior.",
            "status": "active",
            "evidence": [{"type": "code", "file": "feature.py"}],
            "valid_from": None,
            "valid_until": None,
            "last_verified": None,
        }],
        "proposed_relations": [],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\\n",
}

prompt = sys.stdin.read()
def source_artifacts():
    try:
        inputs = json.loads(prompt.split("Controller inputs:\\n", 1)[1])
    except (IndexError, json.JSONDecodeError):
        return ["docs/explorer/improvements/jwt-authentication/improvement.md"]
    artifacts = inputs.get("explorer_scope", {}).get("artifacts", [])
    paths = [item.get("path") for item in artifacts if isinstance(item, dict) and isinstance(item.get("path"), str)]
    return paths or ["docs/explorer/improvements/jwt-authentication/improvement.md"]

stage = next((output for name, output in STAGES.items() if f"# {name} Worker v1" in prompt), None)
if stage is not None:
    print(stage, end="")
elif "# Explore Worker v1" in prompt:
    print(MARKDOWN["explore"], end="")
elif "# Purpose Worker v1" in prompt:
    print(MARKDOWN["purpose"], end="")
elif "# Spec Worker v1" in prompt:
    print(MARKDOWN["spec"], end="")
elif "# Design Worker v1" in prompt:
    marker = Path(".design-decision-requested")
    if marker.exists():
        print(MARKDOWN["design"], end="")
    else:
        marker.write_text("1", encoding="utf-8")
        print(json.dumps({
            "schema_version": 1,
            "kind": "decision_request",
            "origin_phase": "DESIGN",
            "reason": "The implementation has two viable approaches.",
            "question": "Should compatibility be preserved?",
            "context": ["Preserving compatibility is lower risk."],
            "options": [{"id": "preserve", "label": "Preserve", "consequence": "Adapter code is required."}],
            "allows_freeform": True,
        }))
elif "# Tasks Worker v1" in prompt:
    print(json.dumps({
        "schema_version": 1,
        "phase": "tasks",
        "tasks": [{
            "id": "T1",
            "title": "Write the feature",
            "depends_on": [],
            "source_artifacts": source_artifacts(),
            "acceptance_criteria": ["feature.py contains ready"],
            "touched_paths": ["feature.py"],
            "focused_tests": [[sys.executable, "-c", "from pathlib import Path; assert Path('feature.py').read_text() == 'ready\\\\n'"]],
            "broader_tests": [],
            "status": "pending",
        }],
    }))
elif "# Implement Worker v1" in prompt:
    Path("feature.py").write_text("ready\\n", encoding="utf-8")
    print(MARKDOWN["implement"], end="")
elif "# Review Worker v1" in prompt:
    print("# Review v1\\n## Verdict\\nAPPROVE\\n## Findings\\nDeterministic fixture verdict.\\n", end="")
elif "# Knowledge Synthesis Worker v1" in prompt:
    print(MARKDOWN["learning"], end="")
elif "# Knowledge Review Worker v1" in prompt:
    inputs = json.loads(prompt.split("Controller inputs:\\n", 1)[1])
    proposal = inputs["proposal"]
    print(json.dumps({
        "schema_version": 1,
        "phase": "knowledge_review",
        "proposal_id": proposal["proposal_manifest"]["proposal_id"],
        "claim_reviews": [
            {"claim_id": claim["id"], "decision": "accept", "reason": "Evidence supports a durable repository fact."}
            for claim in proposal["proposed_claims"]
        ],
        "relation_reviews": [],
    }))
else:
    raise SystemExit("unrecognized prompt")
""",
                encoding="utf-8",
            )
            provider_script.chmod(0o755)
            env = dict(os.environ)
            env["AI_HARNESS_PROVIDER"] = "claude"
            env["AI_HARNESS_PROVIDER_COMMAND"] = str(provider_script)
            request = f"Implement {write_analysis_artifact(repository)}"
            waiting = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory],
                input=request,
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )
            self.assertEqual(0, waiting.returncode, waiting.stderr)
            self.assertIn("## Decision Required", waiting.stdout)
            run_id = StateStore(repository).load().run_id
            resume_env = dict(env)
            resume_env.pop("AI_HARNESS_PROVIDER", None)
            resume_env.pop("AI_HARNESS_PROVIDER_COMMAND", None)
            resume_line = next(
                line for line in waiting.stdout.splitlines()
                if " --resume " in line and " --answer " in line
            )
            resume_command = shlex.split(resume_line)
            resume_command[resume_command.index("<answer>")] = "Use code."
            resume_command[resume_command.index("<option-id>")] = "code"

            flow_waiting = subprocess.run(
                resume_command,
                cwd=Path(directory).parent,
                input="",
                text=True,
                capture_output=True,
                check=False,
                env=resume_env,
            )

            self.assertEqual(0, flow_waiting.returncode, flow_waiting.stderr)
            self.assertIn("## Decision Required", flow_waiting.stdout)
            state = StateStore(repository).load()
            assert state.pending_decision is not None
            self.assertEqual("SELECTING_STRATEGY", state.pending_decision.origin_phase)
            self.assertTrue((repository / ".ai-harness/artifacts/current/decisions/D1/answer.json").is_file())

            answer_file = repository / "answer.json"
            answer_file.write_text(json.dumps({
                "schema_version": 1,
                "kind": "decision_answer",
                "decision_id": state.pending_decision.id,
                "answer": "Use full implementation.",
                "selected_option": "sdd_high",
            }), encoding="utf-8")

            design_waiting = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--resume", run_id, "--answer-file", str(answer_file)],
                input="",
                text=True,
                capture_output=True,
                check=False,
                env=resume_env,
            )
            self.assertEqual(0, design_waiting.returncode, design_waiting.stderr)
            self.assertIn("## Decision Required", design_waiting.stdout)
            state = StateStore(repository).load()
            assert state.pending_decision is not None
            self.assertEqual("DESIGN", state.pending_decision.origin_phase)

            answer_file.write_text(json.dumps({
                "schema_version": 1,
                "kind": "decision_answer",
                "decision_id": state.pending_decision.id,
                "answer": "Preserve compatibility.",
                "selected_option": "preserve",
            }), encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--resume", run_id, "--answer-file", str(answer_file)],
                input="",
                text=True,
                capture_output=True,
                check=False,
                env=resume_env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("Status: success", completed.stdout)
            snapshot = repository / ".ai-harness/artifacts/runs" / run_id
            self.assertTrue((snapshot / "decisions/D2/answer.json").is_file())


if __name__ == "__main__":
    unittest.main()
