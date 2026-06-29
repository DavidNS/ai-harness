"""LearningService — write knowledge proposals and learning artifacts.

Single responsibility: commit the AI-reviewed learning bundle to canonical
docs + artifact store. The AI invocations (knowledge_synthesis, knowledge_review)
remain as callbacks so this class has no provider dependency.

Previously _publish_learning_proposals + _explorer_learning on
ExplorerFlowMixin.
"""
from __future__ import annotations

import json
from typing import Callable, Mapping

from ..canonical import CanonicalDocs, slugify
from ..knowledge_source import (
    CLAIMS_FILE,
    MANIFEST_FILE,
    RELATIONS_FILE,
    pending_patch_path,
    render_jsonl,
)
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from ..text.markdown import markdown_section as _markdown_section


class LearningService:
    """Commits reviewed knowledge proposals to canonical + artifact store.

    Cheap to instantiate — all heavy work happens inside the publish methods.
    ``warnings`` is mutated in-place to keep RunContext in sync.
    """

    def __init__(
        self,
        canonical: CanonicalDocs,
        artifacts: ArtifactStore,
        state: StateStore,
        warnings: list[str],
        *,
        reviewed_learning_bundle_fn: Callable,
    ) -> None:
        self._canonical = canonical
        self._artifacts = artifacts
        self._state = state
        self._warnings = warnings
        self._reviewed_learning_bundle = reviewed_learning_bundle_fn

    def explorer_learning(self, output: str, *, kind: str) -> str:
        """Convert explorer artifact text to Learning v2 format."""
        title = _markdown_section(output, "Problem") or self._state.load().user_input
        evidence = _markdown_section(output, "Evidence") or _markdown_section(output, "Context")
        open_questions = (
            _markdown_section(output, "Open Questions")
            or _markdown_section(output, "Next Step")
            or "None."
        )
        keywords = slugify(title, fallback="knowledge").replace("-", ", ")
        normalized = kind.replace("_", "-")
        summaries = {
            "existing-functionality": f"Existing functionality confirmed for: {title}",
            "limitation": f"Repository limitation identified for: {title}",
            "bullshit": f"Proposal rejected after explorer for: {title}",
            "improvement": f"Explorer outcome for improvement scope: {title}",
        }
        decisions = {
            "existing-functionality": "Record the existing functionality as repository knowledge.",
            "limitation": "Record the repository constraint and keep it from being rediscovered as a proposed improvement.",
            "bullshit": "Record that this direction is rejected and avoid repeating the same outcome.",
            "improvement": "Record this explorer outcome for future explorer planning.",
        }
        solutions = {
            "existing-functionality": "Use the existing implementation rather than creating duplicate functionality.",
            "limitation": "Respect the constraint and seek alternatives in analysis planning.",
            "bullshit": "Avoid implementing this direction and reroute toward viable outcomes.",
            "improvement": "Prioritize a bounded and evidence-backed implementation path.",
        }
        summary = summaries.get(normalized, f"Repository explorer finding: {title}")
        decision = decisions.get(normalized, "Use this explorer finding to improve future analysis decisions.")
        solution = solutions.get(normalized, "Preserve a bounded, evidence-based outcome and review it before implementation.")
        evidence_value = evidence or "Repository evidence confirms the explorer result."
        return (
            "# Learning v2\n"
            "## Title\n"
            f"{title}\n"
            "## Summary\n"
            f"{summary}\n"
            "## Decisions\n"
            f"{decision}\n"
            "## Patterns\n"
            f"{evidence_value}\n"
            "## Errors\n"
            f"{open_questions}\n"
            "## Solutions\n"
            f"{solution}\n"
            "## Keywords\n"
            f"{keywords}\n"
        )

    def publish_learning_proposals(
        self,
        output: str,
        phase: str,
        *,
        synthesis_inputs: Mapping[str, object],
    ) -> str:
        bundle, reviewed_claims, review = self._reviewed_learning_bundle(output, synthesis_inputs)
        if reviewed_claims:
            self._warnings.append(
                "Knowledge proposal AI review downgraded or rejected some active claims: "
                + ", ".join(f"{item['claim_id']}:{item['decision']}:{item['reason']}" for item in reviewed_claims)
            )
        state = self._state.load()
        base = pending_patch_path(state.run_id)
        manifest = dict(bundle.manifest)
        manifest.update({
            "run_id": state.run_id,
            "claims_file": CLAIMS_FILE,
            "claims_count": len(bundle.claims),
            "relations_count": len(bundle.relations),
            "review": {
                "phase": "knowledge_review",
                "changed_claims": [dict(item) for item in reviewed_claims],
            },
        })
        if bundle.relations:
            manifest["relations_file"] = RELATIONS_FILE

        manifest_record = self._canonical.write(
            pending_patch_path(state.run_id, MANIFEST_FILE),
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        claims_record = self._canonical.write(
            pending_patch_path(state.run_id, CLAIMS_FILE),
            render_jsonl(bundle.claims),
        )
        relations_record: dict[str, str] | None = None
        if bundle.relations:
            relations_record = self._canonical.write(
                pending_patch_path(state.run_id, RELATIONS_FILE),
                render_jsonl(bundle.relations),
            )

        payload: dict[str, object] = {
            "kind": "knowledge_proposals",
            "proposal_id": manifest["proposal_id"],
            "path": base,
            "manifest": manifest_record,
            "claims": claims_record,
            "claims_count": len(bundle.claims),
            "relations_count": len(bundle.relations),
            "review": {
                "proposal_id": review.proposal_id,
                "claim_reviews": [dict(item) for item in review.claim_reviews],
                "relation_reviews": [dict(item) for item in review.relation_reviews],
                "changed_claims": [dict(item) for item in reviewed_claims],
            },
        }
        if relations_record is not None:
            payload["relations"] = relations_record
        artifact = f"published/{phase.lower()}-proposals.json"
        self._artifacts.write_json(artifact, payload)
        self._state.record_artifact(artifact, phase)
        telemetry_artifact = f"published/{phase.lower()}-knowledge-extraction.json"
        self._artifacts.write_json(telemetry_artifact, {
            "schema_version": 1,
            "phase": phase,
            "proposal_id": manifest["proposal_id"],
            "outcome": "proposal_created",
            "changed_claims": [dict(item) for item in reviewed_claims],
        })
        self._state.record_artifact(telemetry_artifact, phase)
        return base
