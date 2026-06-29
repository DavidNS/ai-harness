"""Knowledge-source reconciliation helpers."""

from __future__ import annotations

from typing import Mapping, Sequence

from .contracts import _DOMAIN_RE, _ID_RE, RECONCILIATION_DECISIONS
from .validation import _fail, _string, validate_claim


def candidate_match_score(new_claim: Mapping[str, object], existing: Mapping[str, object]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    if new_claim.get("domain") == existing.get("domain"):
        reasons.append("domain")
    if new_claim.get("claim_type") == existing.get("claim_type"):
        reasons.append("claim_type")
    for field in ("subjects", "files", "symbols"):
        left = set(str(item) for item in new_claim.get(field, []) if isinstance(item, str))
        right = set(str(item) for item in existing.get(field, []) if isinstance(item, str))
        if left & right:
            reasons.append(field)
    score = sum(3 if reason in {"domain", "subjects", "files", "symbols"} else 1 for reason in reasons)
    return score, reasons


def select_candidate_cluster(
    new_claim: Mapping[str, object],
    accepted_claims: Sequence[Mapping[str, object]],
    *,
    limit: int = 10,
) -> list[dict[str, object]]:
    if isinstance(limit, bool) or limit < 1:
        _fail("candidate cluster limit must be positive")
    ranked: list[tuple[int, str, Mapping[str, object], list[str]]] = []
    for existing in accepted_claims:
        score, reasons = candidate_match_score(new_claim, existing)
        if score > 0:
            ranked.append((score, str(existing.get("id", "")), existing, reasons))
    selected = sorted(ranked, key=lambda item: (-item[0], item[1]))[:limit]
    return [
        {"claim": dict(claim), "score": score, "reasons": reasons}
        for score, _, claim, reasons in selected
    ]


def reconciliation_job(
    job_id: str,
    domain_summary: str,
    new_claim: Mapping[str, object],
    candidate_cluster: Sequence[Mapping[str, object]],
    evidence_snippets: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "job_id": _string(job_id, "job_id", pattern=_ID_RE),
        "domain": _string(new_claim.get("domain"), "claim.domain", pattern=_DOMAIN_RE),
        "domain_summary": _string(domain_summary, "domain_summary"),
        "new_claim": validate_claim(new_claim),
        "candidate_cluster": [dict(item) for item in candidate_cluster],
        "evidence_snippets": [dict(item) for item in evidence_snippets],
    }


def reduce_reconciliation_decision(
    decision: str,
    new_claim: Mapping[str, object],
    candidate_ids: Sequence[str],
    *,
    rationale: str = "",
) -> dict[str, object]:
    if decision not in RECONCILIATION_DECISIONS:
        _fail("reconciliation decision is unsupported")
    claim = validate_claim(new_claim)
    targets = tuple(_string(item, "candidate_id", pattern=_ID_RE) for item in candidate_ids)
    operations: list[dict[str, object]] = []
    review_tasks: list[dict[str, object]] = []
    if decision == "duplicate":
        if not targets:
            _fail("duplicate decisions require a candidate")
        operations.append({"operation": "merge", "target_claim_id": targets[0], "source_claim_id": claim["id"]})
    elif decision == "supersedes":
        if not targets:
            _fail("supersedes decisions require at least one candidate")
        operations.append({"operation": "add", "claim": claim})
        for target in targets:
            operations.append({"operation": "supersede", "claim_id": target, "replacement_claim_id": claim["id"]})
    elif decision == "contradicted_by":
        if not targets:
            _fail("contradicted_by decisions require a candidate")
        operations.append({"operation": "add", "claim": claim})
        for target in targets:
            operations.append({"operation": "contradict", "claim_id": target, "conflicting_claim_id": claim["id"]})
    elif decision in {"compatible", "unrelated"}:
        operations.append({"operation": "add", "claim": claim})
    else:
        review_tasks.append({
            "claim_id": claim["id"],
            "candidate_ids": list(targets),
            "reason": rationale or "AI reconciliation requested human review.",
        })
    return {
        "schema_version": 1,
        "decision": decision,
        "claim_id": claim["id"],
        "operations": operations,
        "review_tasks": review_tasks,
        "rationale": rationale,
    }
