from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.config import HarnessConfig
from ai_harness.errors import HarnessError
from ai_harness.orchestrator import Orchestrator
from ai_harness.providers.base import ProviderResult
from ai_harness.stores.state import StateStore
from tests.fixtures.flow import run_with_flow
from tests.fixtures.scripted_provider import MARKDOWN, ScriptedProvider


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

def write_compact_improvement(repository: Path, relative: str, title: str) -> str:
    artifact = repository / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        f"# Improvement: {title}\n"
        "## Status\nProposed\n"
        "## Problem\nThe current behavior is incomplete.\n"
        "## Evidence\nA full-SDD integration test uses this artifact.\n"
        "## Desired Behavior\nThe requested scope is represented during implementation.\n"
        "## Implementation Notes\nUse the controller-owned explorer scope.\n"
        "## Acceptance Criteria\n- The source artifact is covered by a task.\n",
        encoding="utf-8",
    )
    return relative


def controller_inputs(prompt: str) -> dict[str, object]:
    return json.loads(prompt.split("Controller inputs:\n", 1)[1])


class ScopedTaskProvider(ScriptedProvider):
    def __init__(self, *, task_sources: list[str] | None = None, deferrals: list[dict[str, str]] | None = None) -> None:
        super().__init__()
        self.task_sources = task_sources
        self.deferrals = deferrals
        self.task_inputs: dict[str, object] | None = None
        self.implement_task: dict[str, object] | None = None
        self.review_task: dict[str, object] | None = None

    def _scope_paths(self, prompt: str) -> list[str]:
        inputs = controller_inputs(prompt)
        self.task_inputs = inputs
        artifacts = inputs.get("explorer_scope", {}).get("artifacts", [])
        return [item["path"] for item in artifacts if isinstance(item, dict) and isinstance(item.get("path"), str)]

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Tasks Worker v1" in prompt:
            self.calls.append("tasks")
            self.counts["tasks"] += 1
            sources = self.task_sources or self._scope_paths(prompt)
            document: dict[str, object] = {
                "schema_version": 1,
                "phase": "tasks",
                "tasks": [{
                    "id": "T1",
                    "title": "Write the feature",
                    "depends_on": [],
                    "source_artifacts": sources,
                    "acceptance_criteria": ["feature.py contains ready"],
                    "touched_paths": ["feature.py"],
                    "focused_tests": [[sys.executable, "-c", "from pathlib import Path; assert Path('feature.py').read_text() == 'ready\\n'"]],
                    "broader_tests": [[sys.executable, "-c", "print('broader gate passed')"]],
                    "status": "pending",
                }],
            }
            if self.deferrals is not None:
                document["deferrals"] = self.deferrals
            return ProviderResult(json.dumps(document), "", 0, 0.001)
        if "# Implement Worker v1" in prompt:
            self.implement_task = controller_inputs(prompt)["task"]  # type: ignore[assignment]
        if "# Review Worker v1" in prompt:
            self.review_task = controller_inputs(prompt)["task"]  # type: ignore[assignment]
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)

class RepairProposalProvider(ScriptedProvider):
    def __init__(self, proposal_outputs: list[str]) -> None:
        super().__init__()
        self.proposal_outputs = list(proposal_outputs)
        self.proposal_prompts: list[str] = []

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Purpose Worker v1" in prompt:
            self.proposal_prompts.append(prompt)
            self.calls.append("purpose")
            index = self.counts["purpose"]
            self.counts["purpose"] += 1
            output = self.proposal_outputs[min(index, len(self.proposal_outputs) - 1)]
            return ProviderResult(output, "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class FullSddIntegrationTests(unittest.TestCase):
    def test_full_sdd_runs_exact_order_real_gates_snapshot_and_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            entry = write_analysis_artifact(repository)
            provider = ScriptedProvider()
            progress: list[str] = []
            result = run_with_flow(
                Orchestrator(
                    repository, HarnessConfig(provider="local"), provider,
                    progress=progress.append,
                ),
                f"Implement {entry}",
                "sdd_high",
            )

            expected_workers = ["explore_request_understanding", "explore_clarification_gate", "explore_triage", "explore_evidence_plan", "explore_evidence_collection", "explore_ci_barrier", "explore_evidence_normalization", "explore_outcome_synthesis", "explore_review", "knowledge_synthesis", "purpose", "spec", "design", "tasks", "implement", "review", "knowledge_synthesis", "knowledge_review"]
            self.assertEqual(expected_workers, provider.calls)
            running_progress = [item for item in progress if item.startswith("Running ")]
            for phase in result.phases:
                self.assertIn(f"Running {phase}", running_progress)
            self.assertTrue(any(item.startswith("Invoking explore_outcome_synthesis worker:") for item in progress))
            self.assertEqual("success", result.outcome)
            self.assertEqual("ready\n", (repository / "feature.py").read_text(encoding="utf-8"))
            self.assertIn("explore/exploration_map.json", result.artifacts)
            self.assertIn("explore/outcome_bundle.json", result.artifacts)
            self.assertTrue(result.snapshot_path.is_dir())
            exploration_map = json.loads((result.snapshot_path / "explore" / "exploration_map.json").read_text(encoding="utf-8"))
            outcome_bundle = json.loads((result.snapshot_path / "explore" / "outcome_bundle.json").read_text(encoding="utf-8"))
            self.assertEqual("exploration_map", exploration_map["kind"])
            self.assertEqual(exploration_map, outcome_bundle["exploration_map"])
            self.assertEqual(exploration_map, provider.phase_inputs["explore_outcome_synthesis"][0]["exploration_map"])
            self.assertEqual(exploration_map, provider.phase_inputs["purpose"][0]["explore/outcome_bundle.json"]["exploration_map"])
            self.assertEqual(exploration_map, provider.phase_inputs["design"][0]["explore/outcome_bundle.json"]["exploration_map"])
            self.assertTrue((result.snapshot_path / "state.json").is_file())
            strategy = json.loads((result.snapshot_path / "strategy.json").read_text(encoding="utf-8"))
            self.assertEqual("SDD", strategy["strategy"])
            self.assertEqual(strategy["strategy"], strategy["recommended_strategy"])
            self.assertEqual("user_decision", strategy["selection_source"])
            self.assertTrue(strategy["prompted"])
            self.assertFalse(strategy["overridden"])
            attempt = result.snapshot_path / "attempts/T1/1.json"
            self.assertIn('"status": "completed"', attempt.read_text(encoding="utf-8"))
            purpose = repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposal_manifest.json"
            claims = repository / "knowledge-source" / "patches" / "pending" / result.run_id / "proposed_claims.jsonl"
            self.assertTrue(purpose.is_file())
            self.assertTrue(claims.is_file())
            self.assertEqual("proposal.deterministic-offline-completion.001", json.loads(purpose.read_text(encoding="utf-8"))["proposal_id"])
            self.assertEqual("claim.deterministic-offline-completion.001", json.loads(claims.read_text(encoding="utf-8").splitlines()[0])["id"])

    def test_malformed_proposal_is_repaired_once_and_persisted_after_validation(self) -> None:
        malformed = "# Purpose v1\n## Summary\nMissing the controller-required sections.\n"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            entry = write_analysis_artifact(repository)
            provider = RepairProposalProvider([malformed, MARKDOWN["purpose"]])

            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                f"Implement {entry}",
                "sdd_high",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(2, provider.calls.count("purpose"))
            self.assertIn("purpose.md", result.artifacts)
            repair_prompt = provider.proposal_prompts[1]
            self.assertIn('"repair"', repair_prompt)
            self.assertIn("required section must appear once: Problem", repair_prompt)
            self.assertIn('"required_heading": "# Purpose v1"', repair_prompt)
            self.assertIn('"required_sections"', repair_prompt)
            self.assertIn("Missing the controller-required sections.", repair_prompt)

    def test_exhausted_proposal_repair_records_validation_failure_without_artifact(self) -> None:
        malformed = "# Purpose v1\n## Summary\nStill missing the controller-required sections.\n"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            entry = write_analysis_artifact(repository)
            provider = RepairProposalProvider([malformed, malformed])

            with self.assertRaisesRegex(Exception, "required section must appear once: Problem"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), provider),
                    f"Implement {entry}",
                    "sdd_high",
                )

            self.assertEqual(2, provider.calls.count("purpose"))
            store = StateStore(repository)
            state = store.load()
            self.assertEqual("failed", state.status.value)
            self.assertNotIn("purpose.md", state.artifacts)
            self.assertIn("validation/purpose-failure.json", state.artifacts)
            failure = store.artifacts.read_json("validation/purpose-failure.json")
            self.assertEqual("purpose", failure["phase"])
            self.assertEqual("purpose.md", failure["artifact"])
            self.assertEqual(["original", "repair"], [item["attempt"] for item in failure["attempts"]])
            self.assertTrue(all(str(item["job_result"]).startswith("jobs/J") for item in failure["attempts"]))

    def test_exhausted_review_repair_fails_without_retrying_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            entry = write_analysis_artifact(repository)
            provider = ScriptedProvider(review_verdicts=("BAD",))

            with self.assertRaisesRegex(Exception, "review repair exhausted"):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), provider),
                    f"Implement {entry}",
                    "sdd_high",
                )

            self.assertEqual(1, provider.calls.count("implement"))
            self.assertEqual(2, provider.calls.count("review"))
            state = StateStore(repository).load()
            self.assertEqual("failed", state.status.value)
            self.assertIn("validation/review-failure.json", state.artifacts)
            self.assertFalse((repository / "feature.py").exists())

    def test_full_sdd_passes_source_mapping_to_implement_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            entry = write_analysis_artifact(repository)
            provider = ScopedTaskProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                f"Implement {entry}",
                "sdd_high",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual([entry], provider.implement_task["source_artifacts"])
            self.assertEqual([entry], provider.review_task["source_artifacts"])
            scope = json.loads((result.snapshot_path / "explorer_scope.json").read_text(encoding="utf-8"))
            self.assertEqual([entry], [item["path"] for item in scope["artifacts"]])
            coverage = json.loads((result.snapshot_path / "task_coverage.json").read_text(encoding="utf-8"))
            self.assertEqual([entry], coverage["covered_artifacts"])

    def test_full_sdd_resolves_multiple_explicit_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            first = write_compact_improvement(repository, "docs/explorer/improvements/bundle/a/improvement.md", "A")
            second = write_compact_improvement(repository, "docs/explorer/improvements/bundle/b/improvement.md", "B")
            provider = ScopedTaskProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                f"Implement {second} and {first}",
                "sdd_high",
            )

            scope = json.loads((result.snapshot_path / "explorer_scope.json").read_text(encoding="utf-8"))
            self.assertEqual([second, first], [item["path"] for item in scope["artifacts"]])

    def test_full_sdd_review_retry_preserves_source_artifact_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            first = write_compact_improvement(repository, "docs/explorer/improvements/retry/a/improvement.md", "A")
            second = write_compact_improvement(repository, "docs/explorer/improvements/retry/b/improvement.md", "B")
            finding = f"{second}: adjust the implementation for this source artifact."
            provider = ScriptedProvider(
                review_verdicts=("REQUEST_CHANGES", "APPROVE"),
                review_findings=(finding, "Correction accepted."),
            )
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                f"Implement {first} and {second}",
                "sdd_high",
            )

            self.assertEqual("success", result.outcome)
            self.assertEqual(2, provider.calls.count("implement"))
            retry_failures = provider.phase_inputs["implement"][1]["prior_failures"]
            self.assertEqual(1, len(retry_failures))
            self.assertIn("review requested changes", retry_failures[0])
            self.assertIn(finding, retry_failures[0])

    def test_full_sdd_expands_initiative_folder_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            first = write_compact_improvement(repository, "docs/explorer/improvements/initiative/a/improvement.md", "A")
            second = write_compact_improvement(repository, "docs/explorer/improvements/initiative/b/improvement.md", "B")
            provider = ScopedTaskProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Implement docs/explorer/improvements/initiative",
                "sdd_high",
            )

            scope = json.loads((result.snapshot_path / "explorer_scope.json").read_text(encoding="utf-8"))
            self.assertEqual([first, second], [item["path"] for item in scope["artifacts"]])

    def test_full_sdd_resolves_manifest_and_preserves_primary_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            first = write_compact_improvement(repository, "docs/explorer/improvements/manifest/a/improvement.md", "A")
            second = write_compact_improvement(repository, "docs/explorer/improvements/manifest/b/improvement.md", "B")
            manifest = repository / "published" / "explorer.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({
                "manifest_version": 1,
                "primary_artifact": second,
                "artifacts": [
                    {"kind": "improvement", "path": first},
                    {"kind": "improvement", "path": second},
                ],
            }), encoding="utf-8")
            provider = ScopedTaskProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Implement published/explorer.json",
                "sdd_high",
            )

            scope = json.loads((result.snapshot_path / "explorer_scope.json").read_text(encoding="utf-8"))
            self.assertEqual(second, scope["primary_artifact"])
            self.assertEqual([second, first], [item["path"] for item in scope["artifacts"]])

    def test_full_sdd_uses_manifest_handoff_virtual_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            virtual_path = "docs/explorer/improvements/virtual/slash/improvement.md"
            content = "# Improvement: Virtual Slash Command\n## Status\nProposed\n## Problem\nVirtual scope is not materialized.\n## Evidence\nharness/cli/commands.py records the CLI surface.\n## Desired Behavior\nImplement virtual scope.\n## Implementation Notes\nUse the handoff content.\n## Acceptance Criteria\n- Virtual scope is consumed.\n"
            published = repository / "published"
            published.mkdir()
            (published / "explorer-handoff.json").write_text(json.dumps({
                "schema_version": 1,
                "kind": "explorer_handoff",
                "primary_entry": "single",
                "entries": [{
                    "entry_id": "single",
                    "kind": "improvement",
                    "suggested_path": virtual_path,
                    "title": "Virtual Slash Command",
                    "content": content,
                }],
                "evidence_trace": [{"id": "T1", "claim_id": "C1", "source": "test", "path": "harness/cli/commands.py", "excerpt": "CLI surface", "confidence": "high"}],
                "duplicate_search": {"searched_terms": ["slash"], "searched_surfaces": ["source"], "matches": [], "no_match_claims": []},
                "unknowns": [],
                "risks": [],
                "candidate_work_shapes": [],
                "verification_surfaces": [],
            }), encoding="utf-8")
            (published / "explorer.json").write_text(json.dumps({
                "manifest_version": 1,
                "primary_artifact": virtual_path,
                "handoff_artifact": "published/explorer-handoff.json",
                "artifacts": [{"kind": "improvement", "suggested_path": virtual_path}],
            }), encoding="utf-8")
            provider = ScopedTaskProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Implement published/explorer.json",
                "sdd_high",
            )

            scope = json.loads((result.snapshot_path / "explorer_scope.json").read_text(encoding="utf-8"))
            self.assertEqual([virtual_path], [item["path"] for item in scope["artifacts"]])
            self.assertEqual(content, scope["artifacts"][0]["content"])
            self.assertEqual("explorer_handoff", scope["explorer_handoff"]["kind"])

    def test_full_sdd_rejects_uncovered_scope_before_tdd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            first = write_compact_improvement(repository, "docs/explorer/improvements/coverage/a/improvement.md", "A")
            write_compact_improvement(repository, "docs/explorer/improvements/coverage/b/improvement.md", "B")
            provider = ScopedTaskProvider(task_sources=[first])

            with self.assertRaises(HarnessError):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), provider),
                    "Implement docs/explorer/improvements/coverage",
                    "sdd_high",
                )
            self.assertEqual(["explore_request_understanding", "explore_clarification_gate", "explore_triage", "explore_evidence_plan", "explore_evidence_collection", "explore_ci_barrier", "explore_evidence_normalization", "explore_outcome_synthesis", "explore_review", "knowledge_synthesis", "purpose", "spec", "design", "tasks"], provider.calls)

    def test_full_sdd_accepts_deferred_scope_with_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            first = write_compact_improvement(repository, "docs/explorer/improvements/deferred/a/improvement.md", "A")
            second = write_compact_improvement(repository, "docs/explorer/improvements/deferred/b/improvement.md", "B")
            provider = ScopedTaskProvider(task_sources=[first], deferrals=[{"source_artifact": second, "reason": "Implement in a later run."}])
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Implement docs/explorer/improvements/deferred",
                "sdd_high",
            )

            self.assertEqual("success", result.outcome)
            coverage = json.loads((result.snapshot_path / "task_coverage.json").read_text(encoding="utf-8"))
            self.assertEqual([{"source_artifact": second, "reason": "Implement in a later run."}], coverage["deferred_artifacts"])

    def test_full_sdd_rejects_unknown_deferred_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            first = write_compact_improvement(repository, "docs/explorer/improvements/unknown/a/improvement.md", "A")
            provider = ScopedTaskProvider(task_sources=[first], deferrals=[{"source_artifact": "docs/explorer/improvements/unknown/missing/improvement.md", "reason": "Later."}])

            with self.assertRaises(HarnessError):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), provider),
                    "Implement docs/explorer/improvements/unknown",
                    "sdd_high",
                )

    def test_analysis_choice_runs_explore_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ScriptedProvider()
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                "Implement JWT authentication API endpoint architecture and add tests",
                "explorer",
            )

            self.assertEqual("EXPLORE_BUNDLE", result.strategy.strategy)
            self.assertEqual(["explore_request_understanding", "explore_clarification_gate", "explore_triage", "explore_evidence_plan", "explore_evidence_collection", "explore_ci_barrier", "explore_evidence_normalization", "explore_outcome_synthesis", "explore_review", "knowledge_synthesis"], provider.calls)
            self.assertFalse((repository / "feature.py").exists())
            self.assertIn("explore/outcome_bundle.json", result.artifacts)
            self.assertIn("published/explore-handoff.json", result.artifacts)
            self.assertIn("explorer_gate.json", result.artifacts)

    def test_failed_test_is_corrected_before_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            entry = write_analysis_artifact(repository)
            provider = ScriptedProvider(implementation_contents=("wrong\n", "ready\n"))
            result = run_with_flow(
                Orchestrator(repository, HarnessConfig(provider="local"), provider),
                f"Implement {entry}",
                "sdd_high",
            )
            self.assertEqual("success", result.outcome)
            self.assertEqual(2, provider.calls.count("implement"))
            self.assertEqual(1, provider.calls.count("review"))


if __name__ == "__main__":
    unittest.main()
