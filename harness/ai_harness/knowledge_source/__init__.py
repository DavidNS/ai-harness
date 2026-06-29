"""Structured knowledge-source contracts and reconciliation helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .contracts import (
    CLAIM_STATUSES,
    CLAIMS_FILE,
    GENERATED_EVIDENCE_PARTS,
    KNOWLEDGE_REVIEW_DECISIONS,
    KNOWLEDGE_SOURCE_ROOT,
    MANIFEST_FILE,
    PENDING_PATCH_ROOT,
    RECONCILIATION_DECISIONS,
    RELATIONS_FILE,
    REPOSITORY_EVIDENCE_TYPES,
    SEMANTIC_OPERATIONS,
    KnowledgeReviewBundle,
    KnowledgeSourceError,
    LearningProposalBundle,
)
from .evidence import is_repository_backed_evidence, validate_repository_evidence_policy
from .parsing import parse_knowledge_review, parse_learning_proposal
from .patches import pending_patch_path, render_jsonl
from .reconciliation import (
    candidate_match_score,
    reconciliation_job,
    reduce_reconciliation_decision,
    select_candidate_cluster,
)
from .review import apply_knowledge_review, apply_lazy_learning_quality_gates
from .validation import (
    validate_claim,
    validate_evidence,
    validate_knowledge_review,
    validate_proposal_manifest,
    validate_relation,
)

__all__ = [
    "Any",
    "CLAIMS_FILE",
    "CLAIM_STATUSES",
    "GENERATED_EVIDENCE_PARTS",
    "Iterable",
    "KNOWLEDGE_REVIEW_DECISIONS",
    "KNOWLEDGE_SOURCE_ROOT",
    "KnowledgeReviewBundle",
    "KnowledgeSourceError",
    "LearningProposalBundle",
    "MANIFEST_FILE",
    "Mapping",
    "PENDING_PATCH_ROOT",
    "Path",
    "PurePosixPath",
    "RECONCILIATION_DECISIONS",
    "RELATIONS_FILE",
    "REPOSITORY_EVIDENCE_TYPES",
    "SEMANTIC_OPERATIONS",
    "Sequence",
    "apply_knowledge_review",
    "apply_lazy_learning_quality_gates",
    "candidate_match_score",
    "dataclass",
    "is_repository_backed_evidence",
    "json",
    "parse_knowledge_review",
    "parse_learning_proposal",
    "pending_patch_path",
    "re",
    "reconciliation_job",
    "reduce_reconciliation_decision",
    "render_jsonl",
    "select_candidate_cluster",
    "validate_claim",
    "validate_evidence",
    "validate_knowledge_review",
    "validate_proposal_manifest",
    "validate_relation",
    "validate_repository_evidence_policy",
]
