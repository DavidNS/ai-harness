from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.providers.base import ProviderResult
from tests.fixtures.scripted_provider import ScriptedProvider


ANALYSIS = "# Improvement Analysis v1\n## Problem\nInvestigate routing.\n## Context\nA draft improvement exists.\n## Findings\nThe idea is viable.\n## Options\nCreate a future implementation flow.\n## Risks\nScope may expand.\n## Recommendation\nProceed.\n## Outcome\nimprovement\n## Open Questions\nNone.\n"
LIMITATION = "# Limitation v1\n## Problem\nInvestigate routing.\n## Context\nA product constraint exists.\n## Reasoning\nThe idea conflicts with a non-goal.\n## Outcome\nlimitation\n## Next Step\nStop.\n"
NOT_WORTH_IT = "# Limitation v1\n## Problem\nInvestigate routing.\n## Context\nThe idea is possible.\n## Reasoning\nThe implementation cost is not justified.\n## Outcome\nnot-worth-it\n## Next Step\nDo not implement.\n"
EXISTING = "# Existing Functionality v1\n## Problem\nInvestigate routing.\n## Evidence\nRouter tests already cover this behavior.\n## Outcome\nexisting-functionality\n## Open Questions\nNone.\n"
UNRESOLVED_EXISTING = "# Existing Functionality v1\n## Problem\nInvestigate routing.\n## Evidence\nRouter tests already cover this behavior.\n## Outcome\nexisting-functionality\n## Open Questions\nDocumentation may be missing.\n"
COMPACT_ROUTING = "# Improvement: Routing Bundle Output\n## Status\nProposed\n## Problem\nRouting bundle output is missing.\n## Evidence\ndocs/analysis/improvements/routing-bundle-output/improvement.md records the focused routing behavior.\n## Desired Behavior\nPublish a routing improvement.\n## Implementation Notes\nKeep the change focused.\n## Acceptance Criteria\n- Routing bundle output is published.\n"
COMPACT_MANIFEST = "# Improvement: Manifest Bundle Output\n## Status\nProposed\n## Problem\nManifest bundle output is missing.\n## Evidence\ndocs/analysis/improvements/manifest-bundle-output/improvement.md records the focused manifest behavior.\n## Desired Behavior\nPublish a manifest improvement.\n## Implementation Notes\nRecord each artifact in the manifest.\n## Acceptance Criteria\n- Manifest bundle output is published.\n"
BROAD_BUNDLE_CHILD = "# Improvement: Knowledge Source Contracts\n## Status\nProposed\n## Problem\nController prompts, worker state, storage, canonical manifest publication, and tests lose knowledge source context.\n## Evidence\nharness/ai_harness/orchestrator.py records controller prompt, worker state, storage, canonical manifest publication, and test evidence.\n## Desired Behavior\nValidate knowledge source contracts without losing focused child scope.\n## Implementation Notes\nKeep the child scoped to knowledge source contracts while preserving controller, prompt, worker, state, storage, canonical, manifest, publication, and test behavior.\n## Acceptance Criteria\n- Tests assert the knowledge source contract validates controller, worker, state, storage, canonical manifest publication, and prompt behavior.\n"
BROAD_BUNDLE_PEER = "# Improvement: Navigation Context Contracts\n## Status\nProposed\n## Problem\nController prompt, worker state, storage, canonical manifest publication, and tests lose navigation context boundaries.\n## Evidence\nharness/ai_harness/orchestrator.py records controller prompt, worker state, storage, canonical manifest publication, and test evidence for navigation context.\n## Desired Behavior\nValidate navigation context contracts without losing focused child scope.\n## Implementation Notes\nKeep the child scoped to navigation context while preserving controller, prompt, worker, state, storage, canonical, manifest, publication, and test behavior.\n## Acceptance Criteria\n- Tests assert the navigation context contract validates controller, worker, state, storage, canonical manifest publication, and prompt behavior.\n"
BROAD_CATCH_ALL_CHILD = "# Improvement: Catch-All Harness Cleanup\n## Status\nProposed\n## Problem\nCatch-all controller prompt, worker state, storage, canonical manifest publication, routing, documentation, and tests need broad cleanup.\n## Evidence\nharness/ai_harness/orchestrator.py records controller prompt, worker state, storage, canonical manifest publication, routing, documentation, and test evidence.\n## Desired Behavior\nClean up everything else across the whole harness.\n## Implementation Notes\nThis catch-all child spans multiple unrelated surfaces across the entire harness.\n## Acceptance Criteria\n- Tests assert broad cleanup validates controller, worker, state, storage, canonical manifest publication, routing, documentation, and prompt behavior.\n"
ANALYSIS_IMPOSSIBLE = json.dumps({
    "schema_version": 1,
    "kind": "impossible",
    "origin_phase": "EXPLORER",
    "reason": "The completed analysis found the requested outcome contradicts a repository invariant.",
    "evidence": ["The repository invariant forbids this behavior."],
    "remaining_options": ["Change the requested outcome."],
})
INFRA_IMPOSSIBLE = json.dumps({
    "schema_version": 1,
    "kind": "impossible",
    "origin_phase": "EXPLORER",
    "reason": "The worker environment could not inspect the repository.",
    "evidence": ["bwrap failed before execution."],
    "remaining_options": ["Rerun with repository access."],
})


def decision_request(origin_phase: str = "EXPLORER") -> str:
    return json.dumps({
        "schema_version": 1,
        "kind": "decision_request",
        "origin_phase": origin_phase,
        "reason": "The explorer has two product directions.",
        "question": "Should compatibility be preserved?",
        "context": ["Preserving compatibility narrows implementation choices."],
        "options": [{"id": "preserve", "label": "Preserve", "consequence": "Prefer adapters."}],
        "allows_freeform": True,
    })

def bundle_output(entries: list[dict[str, object]], primary_entry: str | None = None) -> str:
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "explorer_bundle",
        "origin_phase": "EXPLORER",
        "entries": entries,
    }
    if primary_entry is not None:
        payload["primary_entry"] = primary_entry
    return json.dumps(payload)

class ExplorerProvider(ScriptedProvider):
    def __init__(self, explorer_output: str) -> None:
        super().__init__()
        self.explorer_output = explorer_output
        self.explorer_prompts: list[str] = []

    def _control_output_for_decision(self) -> str | None:
        try:
            payload = json.loads(self.explorer_output)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or payload.get("kind") != "impossible":
            return None
        payload["origin_phase"] = "EXPLORER_DECISION"
        return json.dumps(payload)

    @staticmethod
    def _default_decision() -> str:
        return json.dumps({
            "schema_version": 1,
            "phase": "explorer_decision",
            "outcome": "new_improvement",
            "rationale": "The supplied explorer artifact should be rendered.",
            "evidence": ["The staged test provider supplies the artifact candidate."],
            "selected_direction": "D1",
            "value_hypothesis": "Rendering the supplied artifact creates implementation-ready analysis.",
            "behavioral_delta": "Artifact synthesis publishes the selected explorer artifact.",
            "rejected_alternatives": [{"id": "D2", "reason": "A no-op would not publish the requested artifact."}],
            "counterevidence": [],
            "falsifying_conditions": ["The rendered artifact duplicates existing behavior without a new target."],
            "minimum_verification": "Explorer review approves the artifact before publication.",
        })

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Decision Worker v1" in prompt:
            control = self._control_output_for_decision()
            if control is not None:
                self.calls.append("explorer_decision")
                self.counts["explorer_decision"] += 1
                return ProviderResult(control, "", 0, 0.001)
        if "# Explorer Artifact Worker v1" in prompt:
            self.explorer_prompts.append(prompt)
            self.calls.append("explorer_artifact")
            self.counts["explorer_artifact"] += 1
            return ProviderResult(self.explorer_output, "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class RepairExplorerProvider(ExplorerProvider):
    def __init__(self, explorer_outputs: list[str]) -> None:
        super().__init__(explorer_outputs[0])
        self.explorer_outputs = list(explorer_outputs)

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Artifact Worker v1" in prompt:
            self.explorer_prompts.append(prompt)
            self.calls.append("explorer_artifact")
            self.counts["explorer_artifact"] += 1
            return ProviderResult(self.explorer_outputs.pop(0), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)

class DistillExplorerProvider(ExplorerProvider):
    def __init__(self, explorer_output: str, distilled_output: str) -> None:
        super().__init__(explorer_output)
        self.distilled_output = distilled_output
        self.distill_prompts: list[str] = []

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Distill Worker v1" in prompt:
            self.distill_prompts.append(prompt)
            self.calls.append("explorer_distill")
            self.counts["explorer_distill"] += 1
            return ProviderResult(self.distilled_output, "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class FindingStyleObservationProvider(ExplorerProvider):
    def __init__(self, explorer_output: str, repository_observations: list[dict[str, object]]) -> None:
        super().__init__(explorer_output)
        self.repository_observations = repository_observations
        self.discovery_prompts: list[str] = []

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Discovery Worker v1" in prompt:
            self.discovery_prompts.append(prompt)
            self.calls.append("explorer_discovery")
            self.counts["explorer_discovery"] += 1
            return ProviderResult(json.dumps({
                "schema_version": 1,
                "phase": "explorer_discovery",
                "claims": [{"id": "C1", "status": "resolved", "evidence": ["The request is a straightforward implementation-only change."]}],
                "candidate_directions": [{
                    "id": "D1",
                    "title": "Publish compact improvement",
                    "mechanism": "Use the supplied compact improvement as a ready artifact.",
                    "impact": "High",
                    "confidence": "High",
                    "cost": "Low",
                    "reversibility": "High",
                    "evidence_strength": "Strong",
                    "behavioral_delta": "A concrete artifact is published for implementation planning.",
                    "evidence": ["The explorer artifact contains a compact improvement block."],
                }],
                "critic_findings": [],
                "related_improvements": [],
                "repository_observations": self.repository_observations,
            }), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class IntakeDrivenObservationProvider(ExplorerProvider):
    def __init__(self, explorer_output: str) -> None:
        super().__init__(explorer_output)
        self.discovery_prompts: list[str] = []

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Intake Worker v1" in prompt:
            self.calls.append("explorer_intake")
            self.counts["explorer_intake"] += 1
            return ProviderResult(json.dumps({
                "schema_version": 1,
                "phase": "explorer_intake",
                "strategic_framing": {
                    "mode": "specific",
                    "value_targets": ["better implementation readiness"],
                    "needs_user_direction": False,
                    "rationale": "The deterministic fixture request is already bounded.",
                },
                "claims": [
                    {
                        "id": "C1",
                        "class": "repository-factual",
                        "text": "The console input component should detect slash-command mode and render filtered command suggestions.",
                        "evidence_targets": ["source", "tests"],
                    }
                ],
                "synthesis_notes": [],
            }), "", 0, 0.001)
        if "# Explorer Discovery Worker v1" in prompt:
            self.discovery_prompts.append(prompt)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class ReviewGapObservationProvider(ExplorerProvider):
    def __init__(self, explorer_output: str) -> None:
        super().__init__(explorer_output)

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Discovery Worker v1" in prompt:
            self.calls.append("explorer_discovery")
            self.counts["explorer_discovery"] += 1
            return ProviderResult(json.dumps({
                "schema_version": 1,
                "phase": "explorer_discovery",
                "claims": [{"id": "C1", "status": "unresolved", "unresolved_reason": "Repository observations did not identify the implementation surface."}],
                "candidate_directions": [{
                    "id": "D1",
                    "title": "Publish compact improvement",
                    "mechanism": "Use the supplied compact improvement as a ready artifact.",
                    "impact": "High",
                    "confidence": "Medium",
                    "cost": "Low",
                    "reversibility": "High",
                    "evidence_strength": "Weak repository evidence; strong request evidence.",
                    "behavioral_delta": "A concrete artifact is published for implementation planning.",
                    "evidence": ["The explorer artifact contains a compact improvement block."],
                }],
                "critic_findings": [],
                "related_improvements": [],
                "repository_observations": [{
                    "kind": "observation_gap",
                    "finding": "Repository observations did not identify the implementation surface.",
                }],
            }), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class StructuredEvidenceProvider(ExplorerProvider):
    def __init__(self, explorer_output: str, discovery_evidence: str) -> None:
        super().__init__(explorer_output)
        self.discovery_evidence = discovery_evidence

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Discovery Worker v1" in prompt:
            self.calls.append("explorer_discovery")
            self.counts["explorer_discovery"] += 1
            return ProviderResult(json.dumps({
                "schema_version": 1,
                "phase": "explorer_discovery",
                "claims": [{"id": "C1", "status": "resolved", "evidence": [self.discovery_evidence]}],
                "candidate_directions": [{
                    "id": "D1",
                    "title": "Publish compact improvement",
                    "mechanism": "Use structured discovery evidence from src/routing.py.",
                    "impact": "High",
                    "confidence": "High",
                    "cost": "Low",
                    "reversibility": "High",
                    "evidence_strength": "Strong",
                    "behavioral_delta": "A concrete artifact is published for implementation planning.",
                    "evidence": [self.discovery_evidence],
                }],
                "critic_findings": [],
                "related_improvements": [],
                "repository_observations": [],
            }), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class ReviewRepairProvider(ExplorerProvider):
    def __init__(self) -> None:
        super().__init__(COMPACT_ROUTING)
        self.review_outputs = [
            "# Review v1\n## Verdict\nLGTM\n## Findings\nMalformed verdict.\n",
            "# Review v1\n## Verdict\nAPPROVE\n## Findings\nRepaired review envelope.\n",
        ]
        self.review_prompts: list[str] = []

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Review Worker v1" in prompt:
            self.review_prompts.append(prompt)
            self.calls.append("explorer_review")
            self.counts["explorer_review"] += 1
            return ProviderResult(self.review_outputs.pop(0), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class DecisionExplorerProvider(ExplorerProvider):
    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Decision Worker v1" in prompt:
            self.calls.append("explorer_decision")
            index = self.counts["explorer_decision"]
            self.counts["explorer_decision"] += 1
            if index == 0:
                return ProviderResult(decision_request("EXPLORER_DECISION"), "", 0, 0.001)
            return ProviderResult(self._default_decision(), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class LowValueDecisionProvider(ExplorerProvider):
    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Decision Worker v1" in prompt:
            self.calls.append("explorer_decision")
            self.counts["explorer_decision"] += 1
            return ProviderResult(json.dumps({
                "schema_version": 1,
                "phase": "explorer_decision",
                "outcome": "new_improvement",
                "rationale": "Structurally valid but missing value-gate fields.",
                "evidence": ["Discovery resolved the repository-factual claim."],
            }), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


def split_bundle_decision() -> str:
    return json.dumps({
        "schema_version": 1,
        "phase": "explorer_decision",
        "outcome": "split_bundle",
        "rationale": "The requested artifact spans two separate implementation surfaces.",
        "evidence": ["Discovery identifies routing and manifest behavior as distinct scopes."],
        "selected_direction": "D1",
        "value_hypothesis": "Split artifacts make each result bounded and reviewable.",
        "behavioral_delta": "Each returned artifact has an independent acceptance outcome.",
        "rejected_alternatives": [{"id": "S2", "reason": "Single artifact hides surface boundaries."}],
        "counterevidence": [],
        "falsifying_conditions": ["Either request no longer maps to distinct surfaces."],
        "minimum_verification": "Each split child artifact is reviewed for bounded acceptance criteria.",
    })

class SplitBundleProvider(ExplorerProvider):
    def __init__(self, explorer_output: str, decision: str = "split_bundle") -> None:
        super().__init__(explorer_output)
        self.decision = decision

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Decision Worker v1" in prompt:
            self.calls.append("explorer_decision")
            self.counts["explorer_decision"] += 1
            payload = split_bundle_decision() if self.decision == "split_bundle" else self._default_decision()
            return ProviderResult(payload, "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)
class DiscoveryRepairProvider(ExplorerProvider):
    def __init__(self) -> None:
        super().__init__(ANALYSIS)
        self.discovery_outputs = [
            json.dumps({
                "schema_version": 1,
                "phase": "explorer_discovery",
                "claims": [{"id": "C1", "status": "resolved", "evidence": ["tests cover it."]}],
                "critic_findings": [{"direction_id": "D1", "severity": "fatal", "finding": "Bad severity.", "recommendation": "Use a supported severity."}],
                "related_improvements": [],
                "repository_observations": [],
            }),
            json.dumps({
                "schema_version": 1,
                "phase": "explorer_discovery",
                "claims": [{"id": "C1", "status": "resolved", "evidence": ["tests cover it."]}],
                "candidate_directions": [{
                    "id": "D1",
                    "title": "Repair contract mismatch",
                    "mechanism": "Retry the worker with validation feedback.",
                    "impact": "High",
                    "confidence": "Medium",
                    "cost": "Low",
                    "reversibility": "High",
                    "evidence_strength": "Strong",
                    "behavioral_delta": "Contract-only worker mistakes are corrected before the run fails.",
                    "evidence": ["harness/ai_harness/orchestrator.py"],
                }],
                "critic_findings": [{"direction_id": "D1", "severity": "warning", "finding": "Bounded repair must remain one-shot.", "recommendation": "Fail if the repair output is still invalid."}],
                "related_improvements": [],
                "repository_observations": [],
            }),
        ]
        self.discovery_prompts: list[str] = []

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Discovery Worker v1" in prompt:
            self.discovery_prompts.append(prompt)
            self.calls.append("explorer_discovery")
            self.counts["explorer_discovery"] += 1
            return ProviderResult(self.discovery_outputs.pop(0), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class NoneOfAboveExplorerProvider(ExplorerProvider):
    def __init__(self) -> None:
        super().__init__(NOT_WORTH_IT)
        self.discovery_prompts: list[str] = []

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explorer Discovery Worker v1" in prompt:
            self.discovery_prompts.append(prompt)
        if "# Explorer Decision Worker v1" in prompt:
            self.calls.append("explorer_decision")
            index = self.counts["explorer_decision"]
            self.counts["explorer_decision"] += 1
            if index == 0:
                return ProviderResult(json.dumps({
                    "schema_version": 1,
                    "phase": "explorer_decision",
                    "outcome": "needs_user_decision",
                    "rationale": "The strategic request has multiple possible directions.",
                    "evidence": ["Discovery produced candidate directions."],
                    "decision_request": {
                        "question": "Which strategic direction should explorer pursue?",
                        "context": ["Candidate directions are not yet clearly valuable."],
                        "options": [
                            {"id": "D1", "label": "Create artifact", "consequence": "Publish a new improvement."},
                            {"id": "none_of_above", "label": "None", "consequence": "Refine and rerun discovery."}
                        ],
                        "allows_freeform": True,
                    },
                }), "", 0, 0.001)
            return ProviderResult(json.dumps({
                "schema_version": 1,
                "phase": "explorer_decision",
                "outcome": "not_worth_it",
                "rationale": "After refinement, no option is valuable enough to publish as an improvement.",
                "evidence": ["The user rejected all proposed directions."],
            }), "", 0, 0.001)
        return super().run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)
