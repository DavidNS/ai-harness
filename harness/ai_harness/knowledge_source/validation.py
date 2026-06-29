"""Knowledge-source validation helpers."""

from __future__ import annotations

import re
from typing import Mapping

from .contracts import (
    _DOMAIN_RE,
    _ID_RE,
    _TYPE_RE,
    CLAIM_STATUSES,
    CLAIMS_FILE,
    KNOWLEDGE_REVIEW_DECISIONS,
    RELATIONS_FILE,
    KnowledgeReviewBundle,
    KnowledgeSourceError,
)


def _fail(message: str) -> None:
    raise KnowledgeSourceError(message)


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail(f"{name} must be an object")
    return dict(value)


def _required_keys(value: Mapping[str, object], required: set[str], allowed: set[str], name: str) -> None:
    keys = set(value)
    if not required <= keys or not keys <= allowed:
        _fail(f"{name} has invalid fields")


def _string(value: object, name: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{name} must be a nonempty string")
    text = value.strip()
    if pattern is not None and not pattern.fullmatch(text):
        _fail(f"{name} has invalid format")
    return text


def _nullable_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name)


def _string_list(value: object, name: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        _fail(f"{name} must be a valid list")
    items: list[str] = []
    for item in value:
        items.append(_string(item, name))
    if len(items) != len(set(items)):
        _fail(f"{name} must not contain duplicates")
    return tuple(items)


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(f"{name} must be a positive integer")
    return value


def validate_evidence(value: object) -> dict[str, object]:
    evidence = _object(value, "evidence")
    allowed = {"type", "file", "artifact", "symbol", "commit", "line_start", "line_end", "excerpt", "url"}
    required = {"type"}
    _required_keys(evidence, required, allowed, "evidence")
    kind = _string(evidence["type"], "evidence.type", pattern=_TYPE_RE)
    if kind not in {"code", "run_artifact", "test", "documentation", "decision", "manual"}:
        _fail("evidence.type is unsupported")
    if not any(isinstance(evidence.get(key), str) and str(evidence.get(key)).strip() for key in ("file", "artifact", "url")):
        _fail("evidence must include file, artifact, or url")
    normalized: dict[str, object] = {"type": kind}
    for key in ("file", "artifact", "symbol", "commit", "excerpt", "url"):
        if key in evidence:
            normalized[key] = _string(evidence[key], f"evidence.{key}")
    if "line_start" in evidence:
        normalized["line_start"] = _positive_int(evidence["line_start"], "evidence.line_start")
    if "line_end" in evidence:
        normalized["line_end"] = _positive_int(evidence["line_end"], "evidence.line_end")
    if "line_start" in normalized and "line_end" in normalized and normalized["line_end"] < normalized["line_start"]:
        _fail("evidence line_end must be greater than or equal to line_start")
    return normalized


def validate_claim(value: object) -> dict[str, object]:
    claim = _object(value, "claim")
    required = {
        "id", "domain", "subjects", "files", "symbols", "claim_type", "text",
        "status", "evidence", "valid_from", "valid_until", "last_verified",
    }
    allowed = required | {"metadata"}
    _required_keys(claim, required, allowed, "claim")
    status = _string(claim["status"], "claim.status")
    if status not in CLAIM_STATUSES:
        _fail("claim.status is unsupported")
    normalized: dict[str, object] = {
        "id": _string(claim["id"], "claim.id", pattern=_ID_RE),
        "domain": _string(claim["domain"], "claim.domain", pattern=_DOMAIN_RE),
        "subjects": list(_string_list(claim["subjects"], "claim.subjects")),
        "files": list(_string_list(claim["files"], "claim.files", nonempty=status != "unverified")),
        "symbols": list(_string_list(claim["symbols"], "claim.symbols", nonempty=False)),
        "claim_type": _string(claim["claim_type"], "claim.claim_type", pattern=_TYPE_RE),
        "text": _string(claim["text"], "claim.text"),
    }
    normalized["status"] = status
    if not isinstance(claim["evidence"], list):
        _fail("claim.evidence must be a list")
    evidence = [validate_evidence(item) for item in claim["evidence"]]
    if status != "unverified" and not evidence:
        _fail("claims without evidence must be marked unverified")
    normalized["evidence"] = evidence
    normalized["valid_from"] = _nullable_string(claim["valid_from"], "claim.valid_from")
    normalized["valid_until"] = _nullable_string(claim["valid_until"], "claim.valid_until")
    normalized["last_verified"] = _nullable_string(claim["last_verified"], "claim.last_verified")
    if "metadata" in claim:
        if not isinstance(claim["metadata"], dict):
            _fail("claim.metadata must be an object")
        normalized["metadata"] = dict(claim["metadata"])
    return normalized


def validate_relation(value: object) -> dict[str, object]:
    relation = _object(value, "relation")
    required = {"id", "domain", "source", "target", "relation_type", "status", "evidence"}
    allowed = required | {"metadata"}
    _required_keys(relation, required, allowed, "relation")
    status = _string(relation["status"], "relation.status")
    if status not in CLAIM_STATUSES:
        _fail("relation.status is unsupported")
    normalized: dict[str, object] = {
        "id": _string(relation["id"], "relation.id", pattern=_ID_RE),
        "domain": _string(relation["domain"], "relation.domain", pattern=_DOMAIN_RE),
        "source": _string(relation["source"], "relation.source", pattern=_ID_RE),
        "target": _string(relation["target"], "relation.target", pattern=_ID_RE),
        "relation_type": _string(relation["relation_type"], "relation.relation_type", pattern=_TYPE_RE),
        "status": status,
    }
    if not isinstance(relation["evidence"], list):
        _fail("relation.evidence must be a list")
    evidence = [validate_evidence(item) for item in relation["evidence"]]
    if status != "unverified" and not evidence:
        _fail("relations without evidence must be marked unverified")
    normalized["evidence"] = evidence
    if "metadata" in relation:
        if not isinstance(relation["metadata"], dict):
            _fail("relation.metadata must be an object")
        normalized["metadata"] = dict(relation["metadata"])
    return normalized


def validate_proposal_manifest(value: object) -> dict[str, object]:
    manifest = _object(value, "proposal_manifest")
    required = {"schema_version", "proposal_id", "summary", "source_artifacts"}
    allowed = required | {"claims_file", "relations_file"}
    _required_keys(manifest, required, allowed, "proposal_manifest")
    if manifest["schema_version"] != 1:
        _fail("proposal_manifest schema_version is unsupported")
    normalized: dict[str, object] = {
        "schema_version": 1,
        "proposal_id": _string(manifest["proposal_id"], "proposal_manifest.proposal_id", pattern=_ID_RE),
        "summary": _string(manifest["summary"], "proposal_manifest.summary"),
        "source_artifacts": list(_string_list(manifest["source_artifacts"], "proposal_manifest.source_artifacts")),
    }
    if "claims_file" in manifest:
        if manifest["claims_file"] != CLAIMS_FILE:
            _fail(f"proposal_manifest.claims_file must be {CLAIMS_FILE}")
        normalized["claims_file"] = CLAIMS_FILE
    if "relations_file" in manifest:
        if manifest["relations_file"] != RELATIONS_FILE:
            _fail(f"proposal_manifest.relations_file must be {RELATIONS_FILE}")
        normalized["relations_file"] = RELATIONS_FILE
    return normalized

def validate_knowledge_review(value: object) -> KnowledgeReviewBundle:
    document = _object(value, "knowledge review")
    required = {"schema_version", "phase", "proposal_id", "claim_reviews"}
    allowed = required | {"relation_reviews"}
    _required_keys(document, required, allowed, "knowledge review")
    if document["schema_version"] != 1 or document["phase"] != "knowledge_review":
        _fail("knowledge review version or phase is invalid")
    proposal_id = _string(document["proposal_id"], "knowledge_review.proposal_id", pattern=_ID_RE)
    raw_claims = document["claim_reviews"]
    if not isinstance(raw_claims, list):
        _fail("knowledge_review.claim_reviews must be a list")
    claim_reviews: list[dict[str, object]] = []
    for item in raw_claims:
        review = _object(item, "claim review")
        review_required = {"claim_id", "decision", "reason"}
        review_allowed = review_required | {"suggested_text", "status_override", "metadata"}
        _required_keys(review, review_required, review_allowed, "claim review")
        decision = _string(review["decision"], "claim_review.decision")
        if decision not in KNOWLEDGE_REVIEW_DECISIONS:
            _fail("claim_review.decision is unsupported")
        if decision == "reject_for_repair" and "suggested_text" not in review:
            _fail("claim_review.suggested_text is required when decision is reject_for_repair")
        normalized: dict[str, object] = {
            "claim_id": _string(review["claim_id"], "claim_review.claim_id", pattern=_ID_RE),
            "decision": decision,
            "reason": _string(review["reason"], "claim_review.reason"),
        }
        if "suggested_text" in review:
            normalized["suggested_text"] = _string(review["suggested_text"], "claim_review.suggested_text")
        if "status_override" in review:
            override = _string(review["status_override"], "claim_review.status_override")
            if override not in CLAIM_STATUSES:
                _fail("claim_review.status_override is unsupported")
            normalized["status_override"] = override
        if "metadata" in review:
            if not isinstance(review["metadata"], dict):
                _fail("claim_review.metadata must be an object")
            normalized["metadata"] = dict(review["metadata"])
        claim_reviews.append(normalized)
    claim_ids = [str(item["claim_id"]) for item in claim_reviews]
    if len(claim_ids) != len(set(claim_ids)):
        _fail("knowledge_review.claim_reviews contains duplicate claim IDs")

    raw_relations = document.get("relation_reviews", [])
    if not isinstance(raw_relations, list):
        _fail("knowledge_review.relation_reviews must be a list")
    relation_reviews: list[dict[str, object]] = []
    for item in raw_relations:
        review = _object(item, "relation review")
        review_required = {"relation_id", "decision", "reason"}
        review_allowed = review_required | {"status_override", "metadata"}
        _required_keys(review, review_required, review_allowed, "relation review")
        decision = _string(review["decision"], "relation_review.decision")
        if decision not in KNOWLEDGE_REVIEW_DECISIONS:
            _fail("relation_review.decision is unsupported")
        normalized = {
            "relation_id": _string(review["relation_id"], "relation_review.relation_id", pattern=_ID_RE),
            "decision": decision,
            "reason": _string(review["reason"], "relation_review.reason"),
        }
        if "status_override" in review:
            override = _string(review["status_override"], "relation_review.status_override")
            if override not in CLAIM_STATUSES:
                _fail("relation_review.status_override is unsupported")
            normalized["status_override"] = override
        if "metadata" in review:
            if not isinstance(review["metadata"], dict):
                _fail("relation_review.metadata must be an object")
            normalized["metadata"] = dict(review["metadata"])
        relation_reviews.append(normalized)
    return KnowledgeReviewBundle(proposal_id, tuple(claim_reviews), tuple(relation_reviews))
