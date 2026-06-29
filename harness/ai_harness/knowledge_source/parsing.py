"""Knowledge-source JSON parsing entry points."""

from __future__ import annotations

import json

from .contracts import KnowledgeReviewBundle, KnowledgeSourceError, LearningProposalBundle
from .validation import (
    _fail,
    _object,
    _required_keys,
    validate_claim,
    validate_knowledge_review,
    validate_proposal_manifest,
    validate_relation,
)


def parse_learning_proposal(candidate: str) -> LearningProposalBundle:
    try:
        data = json.loads(candidate)
    except (TypeError, json.JSONDecodeError) as exc:
        raise KnowledgeSourceError("learning output must be valid JSON") from exc
    document = _object(data, "learning output")
    required = {"schema_version", "phase", "proposal_manifest", "proposed_claims"}
    allowed = required | {"proposed_relations"}
    _required_keys(document, required, allowed, "learning output")
    if document["schema_version"] != 1 or document["phase"] != "learning":
        _fail("learning output version or phase is invalid")
    manifest = validate_proposal_manifest(document["proposal_manifest"])
    raw_claims = document["proposed_claims"]
    if not isinstance(raw_claims, list) or not raw_claims:
        _fail("proposed_claims must be a nonempty list")
    claims = tuple(validate_claim(item) for item in raw_claims)
    claim_ids = [str(item["id"]) for item in claims]
    if len(claim_ids) != len(set(claim_ids)):
        _fail("proposed_claims contains duplicate claim IDs")
    raw_relations = document.get("proposed_relations", [])
    if not isinstance(raw_relations, list):
        _fail("proposed_relations must be a list")
    relations = tuple(validate_relation(item) for item in raw_relations)
    relation_ids = [str(item["id"]) for item in relations]
    if len(relation_ids) != len(set(relation_ids)):
        _fail("proposed_relations contains duplicate relation IDs")
    return LearningProposalBundle(manifest, claims, relations)

def parse_knowledge_review(candidate: str) -> KnowledgeReviewBundle:
    try:
        data = json.loads(candidate)
    except (TypeError, json.JSONDecodeError) as exc:
        raise KnowledgeSourceError("knowledge review output must be valid JSON") from exc
    return validate_knowledge_review(data)
