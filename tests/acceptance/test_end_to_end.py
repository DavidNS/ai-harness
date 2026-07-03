from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "harness"


FAKE_CLAUDE = r"""#!/usr/bin/env python3
import json
import pathlib
import sys

prompt = sys.stdin.read()
root = pathlib.Path.cwd()

def source_artifacts():
    try:
        inputs = json.loads(prompt.split("Controller inputs:\n", 1)[1])
    except (IndexError, json.JSONDecodeError):
        return ["docs/explorer/improvements/jwt-authentication/improvement.md"]
    artifacts = inputs.get("explorer_scope", {}).get("artifacts", [])
    paths = [item.get("path") for item in artifacts if isinstance(item, dict) and isinstance(item.get("path"), str)]
    return paths or ["docs/explorer/improvements/jwt-authentication/improvement.md"]

def explore_bundle():
    return json.dumps({
        "schema_version": 1,
        "kind": "explore_outcome_bundle",
        "status": "ready_for_purpose",
        "normalized_request": {"summary": "Implement the request."},
        "triage": {"complexity": "local_change", "ambiguity": "clear", "risk": "low", "evidence_depth": "standard"},
        "evidence": [{"id": "E1", "kind": "knowledge", "claim": "The fixture request is bounded.", "status": "supported", "confidence": "high", "severity": "info", "sources": [{"type": "knowledge", "description": "Fixture evidence."}]}],
        "entries": [{"id": "entry-1", "classification": "improvement", "action": "create", "title": "Implement the request", "rationale": "Evidence supports implementing the bounded request.", "behavioral_delta": "The requested behavior is implemented.", "minimum_verification": "Run the focused tests for the requested behavior.", "problem": "The bounded request should be implemented.", "evidence_refs": ["E1"], "constraints": ["Offline fixture."], "unknowns": []}],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

def explore_synthesis():
    return json.dumps({
        "schema_version": 1,
        "kind": "explore_outcome_synthesis",
        "status": "ready_for_purpose",
        "normalized_request": {"summary": "Implement the request."},
        "triage": {"complexity": "local_change", "ambiguity": "clear", "risk": "low", "evidence_depth": "standard"},
        "entries": [{"id": "entry-1", "classification": "improvement", "action": "create", "title": "Implement the request", "rationale": "Evidence supports implementing the bounded request.", "behavioral_delta": "The requested behavior is implemented.", "minimum_verification": "Run the focused tests for the requested behavior.", "problem": "The bounded request should be implemented.", "evidence_refs": ["E1"], "constraints": ["Offline fixture."], "unknowns": []}],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

stage_outputs = {
    "explore_request_profile": json.dumps({"schema_version": 1, "phase": "explore_request_profile", "summary": "Implement the request.", "request_type": "feature", "complexity": "local_change", "ambiguity": "clear", "risk": "low", "evidence_depth": "standard", "request_parts": ["Implement the request."], "constraints": [], "evidence_questions": ["Is the request bounded?"], "gatherers": ["code", "knowledge", "ci"], "clarification_questions": []}),
    "explore_evidence_digest": json.dumps({"schema_version": 1, "phase": "explore_evidence_digest", "evidence": [{"id": "E1", "kind": "knowledge", "claim": "The fixture request is bounded.", "status": "supported", "confidence": "high", "severity": "info", "sources": [{"type": "knowledge", "description": "Fixture evidence."}]}], "blockers": []}),
    "explore_outcome_synthesis": explore_synthesis(),
}

outputs = {
    "explore": explore_bundle(),
    "purpose": json.dumps({
        "schema_version": 1,
        "kind": "purpose_bundle",
        "summary": "Implement the request.",
        "selected_entries": ["entry-1"],
        "implementation_mode": "direct_patch",
        "problem": "Implement the request.",
        "scope": "One bounded change.",
        "approach": "Use controller gates.",
        "structural_work": [],
        "exclusions": ["No unrelated work."],
        "acceptance_outline": ["Tests pass."],
        "evidence_refs": ["E1"]
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    "spec": "# Spec v1\n## Behavioral Requirements\nThe feature works.\n## Acceptance Criteria\nController tests pass.\n",
    "design": "# Design v1\n## Boundaries\nRepository only.\n## Invariants\nController owns state.\n## Implementation Approach\nWrite feature.py.\n## Unit Test Design\nCheck content.\n## Integration Test Design\nRun a process.\n## End-to-End Test Design\nComplete the pipeline.\n",
    "implement": "# Implementation v1\n## Changes\nCreated feature.py.\n## Evidence\nController tests verify it.\n",
    "knowledge_synthesis": json.dumps({
        "schema_version": 1,
        "phase": "learning",
        "proposal_manifest": {
            "schema_version": 1,
            "proposal_id": "purpose.deterministic-offline-completion.001",
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
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
}

phase_names = (*stage_outputs, *outputs, "tasks", "review", "knowledge_review")
phase = next((name for name in phase_names
              if f"# {' '.join(part.title() for part in name.split('_'))} Worker v1" in prompt), None)
if "This is a non-code request routed away from ai-code-harness" in prompt:
    print("pass-through response")
elif phase in stage_outputs:
    print(stage_outputs[phase], end="")
elif phase == "tasks":
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
            "focused_tests": [[sys.executable, "-c", "from pathlib import Path; assert Path('feature.py').read_text() == 'ready\\n'"]],
            "broader_tests": [[sys.executable, "-c", "print('broader gate passed')"]],
            "status": "pending",
        }],
    }))
elif phase == "implement":
    (root / "feature.py").write_text("ready\n", encoding="utf-8")
    print(outputs[phase], end="")
elif phase == "review":
    print("# Review v1\n## Verdict\nAPPROVE\n## Findings\nObserved diff and tests satisfy the task.\n", end="")
elif phase == "knowledge_review":
    inputs = json.loads(prompt.split("Controller inputs:\n", 1)[1])
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
elif phase in outputs:
    print(outputs[phase], end="")
else:
    print("unrecognized worker prompt", file=sys.stderr)
    raise SystemExit(2)
"""


class LauncherEndToEndAcceptanceTests(unittest.TestCase):
    def test_read_only_harness_runs_full_and_non_code_pipelines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            harness = temporary / "harness"
            shutil.copytree(
                HARNESS,
                harness,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            fake_claude = temporary / "bin" / "claude"
            fake_claude.parent.mkdir()
            fake_claude.write_text(textwrap.dedent(FAKE_CLAUDE), encoding="utf-8")
            fake_claude.chmod(0o755)

            for path in harness.rglob("*"):
                path.chmod(0o555 if path.is_dir() else 0o444)
            harness.chmod(0o555)

            try:
                scenarios = (
                    ("full", "Implement docs/explorer/improvements/jwt-authentication/improvement.md", "success"),
                    ("non-code", "Write a poem about the ocean", "non-code stub"),
                )
                for name, request, expected in scenarios:
                    with self.subTest(name=name):
                        repository = temporary / name
                        repository.mkdir()
                        subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
                        if name == "full":
                            artifact = repository / "docs" / "explorer" / "improvements" / "jwt-authentication" / "improvement.md"
                            artifact.parent.mkdir(parents=True)
                            artifact.write_text(
                                "# Improvement Analysis v1\n## Problem\nImplement JWT authentication.\n## Context\nRequired by test.\n## Findings\nViable.\n## Options\nImplement.\n## Risks\nNone.\n## Recommendation\nProceed.\n## Outcome\nimprovement\n## Open Questions\nNone.\n",
                                encoding="utf-8",
                            )
                        environment = dict(os.environ)
                        environment.update({
                            "AI_HARNESS_PROVIDER_COMMAND": str(fake_claude),
                            "PYTHONDONTWRITEBYTECODE": "1",
                        })
                        completed = subprocess.run(
                            [
                                sys.executable,
                                "-B",
                                str(harness / "run.py"),
                                "--cwd",
                                str(repository),
                                "--provider",
                                "claude",
                                "--activated",
                            ],
                            input=request,
                            text=True,
                            capture_output=True,
                            check=False,
                            env=environment,
                            timeout=30,
                        )
                        self.assertEqual(0, completed.returncode, completed.stderr)
                        if "## Decision Required" in completed.stdout:
                            state = json.loads(
                                (repository / ".ai-harness/artifacts/current/state.json").read_text(encoding="utf-8")
                            )
                            run_id = state["run_id"]
                            pending = state["pending_decision"]
                            decision = json.loads(
                                (repository / ".ai-harness/artifacts/current" / pending["request_artifact"]).read_text(encoding="utf-8")
                            )
                            if decision["origin_phase"] == "ROUTING":
                                selected = "non_code" if name == "non-code" else "code"
                            elif decision["origin_phase"] == "SELECTING_STRATEGY":
                                selected = "sdd_high" if name == "full" else "sdd_low"
                            else:
                                selected = decision["options"][0]["id"]
                            answer_file = repository / "answer.json"
                            answer_file.write_text(json.dumps({
                                "schema_version": 1,
                                "kind": "decision_answer",
                                "decision_id": pending["id"],
                                "answer": "Use the selected path.",
                                "selected_option": selected,
                            }), encoding="utf-8")
                            completed = subprocess.run(
                                [
                                    sys.executable,
                                    "-B",
                                    str(harness / "run.py"),
                                    "--cwd",
                                    str(repository),
                                    "--provider",
                                    "claude",
                                    "--activated",
                                    "--resume",
                                    run_id,
                                    "--answer-file",
                                    str(answer_file),
                                ],
                                input="",
                                text=True,
                                capture_output=True,
                                check=False,
                                env=environment,
                                timeout=30,
                            )
                            self.assertEqual(0, completed.returncode, completed.stderr)
                            if name != "non-code" and "## Decision Required" in completed.stdout:
                                state = json.loads(
                                    (repository / ".ai-harness/artifacts/current/state.json").read_text(encoding="utf-8")
                                )
                                pending = state["pending_decision"]
                                decision = json.loads(
                                    (repository / ".ai-harness/artifacts/current" / pending["request_artifact"]).read_text(encoding="utf-8")
                                )
                                selected = (
                                    "sdd_high" if name == "full" else "sdd_low"
                                ) if decision["origin_phase"] == "SELECTING_STRATEGY" else decision["options"][0]["id"]
                                answer_file.write_text(json.dumps({
                                    "schema_version": 1,
                                    "kind": "decision_answer",
                                    "decision_id": pending["id"],
                                    "answer": "Use the selected flow.",
                                    "selected_option": selected,
                                }), encoding="utf-8")
                                completed = subprocess.run(
                                    [
                                        sys.executable,
                                        "-B",
                                        str(harness / "run.py"),
                                        "--cwd",
                                        str(repository),
                                        "--provider",
                                        "claude",
                                        "--activated",
                                        "--resume",
                                        run_id,
                                        "--answer-file",
                                        str(answer_file),
                                    ],
                                    input="",
                                    text=True,
                                    capture_output=True,
                                    check=False,
                                    env=environment,
                                    timeout=30,
                                )
                                self.assertEqual(0, completed.returncode, completed.stderr)

                        for heading in ("Router", "Flow", "Bundles", "Artifacts", "Result"):
                            self.assertIn(heading + "\n", completed.stdout)
                        self.assertIn(f"Status: {expected}", completed.stdout)

                        run_id = next(
                            line.removeprefix("Run ID: ").strip()
                            for line in completed.stdout.splitlines()
                            if line.startswith("Run ID: ")
                        )
                        snapshot = repository / ".ai-harness/artifacts/runs" / run_id
                        self.assertTrue((snapshot / "state.json").is_file())
                        state = json.loads((snapshot / "state.json").read_text())
                        self.assertEqual("completed", state["status"])
                        self.assertEqual("COMPLETED", state["current_phase"])
                        if name == "full":
                            self.assertEqual(
                                "ready\n",
                                (repository / "feature.py").read_text(),
                            )
                            self.assertTrue(
                                (repository / ".ai-harness/knowledge.db").is_file()
                            )
                        elif name == "non-code":
                            self.assertFalse((repository / "feature.py").exists())

                self.assertFalse(any(harness.rglob("__pycache__")))
            finally:
                for path in sorted(harness.rglob("*"), reverse=True):
                    path.chmod(0o755 if path.is_dir() else 0o644)
                harness.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
