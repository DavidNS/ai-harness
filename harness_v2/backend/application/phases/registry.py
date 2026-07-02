"""Phase handler registry for v2 execution."""

from __future__ import annotations

from harness_v2.backend.application.phase_executor import PhaseFunctionRegistry
from harness_v2.backend.domain.lifecycle import PhaseName


def default_phase_function_registry() -> PhaseFunctionRegistry:
    from harness_v2.backend.application.phases import (
        design_draft,
        design_handoff,
        explore_context_pack,
        explore_evidence_digest,
        explore_exploration_map,
        explore_handoff,
        explore_outcome_synthesis,
        explore_request_understanding,
        knowledge_patch,
        knowledge_synthesis,
        proposal_handoff,
        proposal_purpose,
        spec_draft,
        spec_handoff,
        tasks_draft,
        tasks_handoff,
        tdd_create_test,
        validate_json,
        tdd_handoff,
        tdd_implement,
        tdd_review,
    )

    return PhaseFunctionRegistry({
        PhaseName.EXPLORE_REQUEST_UNDERSTANDING: explore_request_understanding.execute,
        PhaseName.EXPLORE_CONTEXT_PACK: explore_context_pack.execute,
        PhaseName.EXPLORE_EVIDENCE_DIGEST: explore_evidence_digest.execute,
        PhaseName.EXPLORE_EXPLORATION_MAP: explore_exploration_map.execute,
        PhaseName.EXPLORE_OUTCOME_SYNTHESIS: explore_outcome_synthesis.execute,
        PhaseName.EXPLORE_HANDOFF: explore_handoff.execute,
        PhaseName.PROPOSAL_PURPOSE: proposal_purpose.execute,
        PhaseName.PROPOSAL_HANDOFF: proposal_handoff.execute,
        PhaseName.SPEC_DRAFT: spec_draft.execute,
        PhaseName.SPEC_HANDOFF: spec_handoff.execute,
        PhaseName.DESIGN_DRAFT: design_draft.execute,
        PhaseName.DESIGN_HANDOFF: design_handoff.execute,
        PhaseName.TASKS_DRAFT: tasks_draft.execute,
        PhaseName.VALIDATE_JSON: validate_json.execute,
        PhaseName.TASKS_HANDOFF: tasks_handoff.execute,
        PhaseName.KNOWLEDGE_EXTRACT_EXPLORE_SYNTHESIS: knowledge_synthesis.execute,
        PhaseName.KNOWLEDGE_EXTRACT_EXPLORE_PATCH: knowledge_patch.execute,
        PhaseName.KNOWLEDGE_EXTRACT_TDD_SYNTHESIS: knowledge_synthesis.execute,
        PhaseName.KNOWLEDGE_EXTRACT_TDD_PATCH: knowledge_patch.execute,
        PhaseName.TDD_CREATE_TEST: tdd_create_test.execute,
        PhaseName.TDD_IMPLEMENT: tdd_implement.execute,
        PhaseName.TDD_REVIEW: tdd_review.execute,
        PhaseName.TDD_HANDOFF: tdd_handoff.execute,
    })
