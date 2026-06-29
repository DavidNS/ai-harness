"""Knowledge-source contracts and shared constants."""

from __future__ import annotations

import re
from dataclasses import dataclass


class KnowledgeSourceError(ValueError):
    """Raised when a knowledge-source artifact violates its contract."""


CLAIM_STATUSES = frozenset({
    "active",
    "deprecated",
    "superseded",
    "conflicted",
    "unverified",
    "stale",
})
SEMANTIC_OPERATIONS = frozenset({
    "add",
    "supersede",
    "contradict",
    "deprecate",
    "merge",
    "mark_stale",
})
RECONCILIATION_DECISIONS = frozenset({
    "duplicate",
    "supersedes",
    "contradicted_by",
    "compatible",
    "unrelated",
    "needs_human",
})

KNOWLEDGE_SOURCE_ROOT = "knowledge-source"
PENDING_PATCH_ROOT = f"{KNOWLEDGE_SOURCE_ROOT}/patches/pending"
CLAIMS_FILE = "proposed_claims.jsonl"
RELATIONS_FILE = "proposed_relations.jsonl"
MANIFEST_FILE = "proposal_manifest.json"

_ID_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{1,127}")
_DOMAIN_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_TYPE_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}")
REPOSITORY_EVIDENCE_TYPES = frozenset({"code", "test", "documentation", "decision"})
GENERATED_EVIDENCE_PARTS = frozenset({
    ".ai-harness",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
})
KNOWLEDGE_REVIEW_DECISIONS = frozenset({
    "accept",
    "downgrade",
    "reject_for_repair",
    "fail_review",
})


@dataclass(frozen=True, slots=True)
class LearningProposalBundle:
    manifest: dict[str, object]
    claims: tuple[dict[str, object], ...]
    relations: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeReviewBundle:
    proposal_id: str
    claim_reviews: tuple[dict[str, object], ...]
    relation_reviews: tuple[dict[str, object], ...] = ()
