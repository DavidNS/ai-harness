"""EXPLORE_EVIDENCE_DIGEST phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_artifacts import explore, explore_ci, explore_mappers, explore_utils
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.common import _required_json
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


def execute(context: PhaseExecutionContext) -> PhaseResult:
    run = context.run
    profile = _required_json(context, explore.REQUEST_PROFILE_ARTIFACT)
    context_pack = _required_json(context, explore.CONTEXT_PACK_ARTIFACT)
    compact_pack = explore_mappers.compact_context_pack(context_pack)
    repository_observations = explore_utils.object_list(context_pack.get("repository_observations", []), "repository_observations")
    related_improvements = explore_utils.object_list(context_pack.get("related_improvements", []), "related_improvements")
    controller_evidence = explore_ci.ci_evidence_from_artifacts(context.artifacts, run.run_id, relevant_paths=explore_utils.candidate_paths(repository_observations, related_improvements))
    digest = context.artifacts.ensure_worker_json(run, BundleName.EXPLORE_BUNDLE, PhaseName.EXPLORE_EVIDENCE_DIGEST, explore.EVIDENCE_DIGEST_TASK, explore.EVIDENCE_DIGEST_ARTIFACT, {"request_profile": profile, "context_pack": compact_pack, "controller_evidence": controller_evidence}, explore.validate_evidence_digest)
    digest = explore_mappers.merge_evidence_digest(digest, controller_evidence)
    explore.validate_evidence_digest(digest)
    context.artifacts.write_json(run.run_id, explore.EVIDENCE_DIGEST_ARTIFACT, digest)
    return PhaseResult()
