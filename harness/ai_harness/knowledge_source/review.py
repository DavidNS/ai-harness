"""Knowledge-source review gates."""

from __future__ import annotations

from .contracts import KnowledgeReviewBundle, LearningProposalBundle
from .validation import _fail


def apply_lazy_learning_quality_gates(
    bundle: LearningProposalBundle,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    return tuple(dict(claim) for claim in bundle.claims), ()


def apply_knowledge_review(
    bundle: LearningProposalBundle,
    review: KnowledgeReviewBundle,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    if review.proposal_id != bundle.manifest["proposal_id"]:
        _fail("knowledge review proposal_id does not match proposal")
    decisions = {str(item["claim_id"]): item for item in review.claim_reviews}
    claims: list[dict[str, object]] = []
    changed: list[dict[str, object]] = []
    for claim in bundle.claims:
        candidate = dict(claim)
        review_item = decisions.get(str(candidate["id"]))
        if review_item is None:
            metadata = dict(candidate.get("metadata", {}))
            metadata["knowledge_review"] = {
                "decision": "accept",
                "reason": "No reviewer objection was returned for this claim.",
            }
            candidate["metadata"] = metadata
            claims.append(candidate)
            continue
        decision = str(review_item["decision"])
        metadata = dict(candidate.get("metadata", {}))
        review_metadata: dict[str, object] = {
            "decision": decision,
            "reason": review_item["reason"],
        }
        if "suggested_text" in review_item:
            review_metadata["suggested_text"] = review_item["suggested_text"]
        if "metadata" in review_item:
            review_metadata["metadata"] = review_item["metadata"]
        metadata["knowledge_review"] = review_metadata
        if decision == "accept":
            if "status_override" in review_item:
                candidate["status"] = review_item["status_override"]
            candidate["metadata"] = metadata
            claims.append(candidate)
            continue
        if decision == "reject_for_repair" and "suggested_text" in review_item:
            candidate["text"] = review_item["suggested_text"]
        candidate["status"] = str(review_item.get("status_override") or "unverified")
        candidate["evidence"] = list(candidate.get("evidence", []))
        candidate["files"] = list(candidate.get("files", []))
        metadata["unverified_reason"] = str(review_item["reason"])
        metadata["quality_gate"] = "ai_knowledge_review"
        candidate["metadata"] = metadata
        claims.append(candidate)
        changed.append({
            "claim_id": candidate.get("id", ""),
            "decision": decision,
            "reason": review_item["reason"],
        })
    return tuple(claims), tuple(changed)
