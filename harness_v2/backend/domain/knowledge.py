"""Knowledge patch domain objects for v2 candidate learning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any

from harness_v2.backend.domain.errors import DomainValidationError, require_text
from harness_v2.backend.domain.lifecycle import BundleName


_ID_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{1,127}")
_DOMAIN_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_TYPE_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_SAFE_SEGMENT_RE = re.compile(r"[A-Za-z0-9_.-]{1,128}")

CLAIM_STATUSES = frozenset(("active", "deprecated", "superseded", "conflicted", "unverified", "stale"))
EVIDENCE_TYPES = frozenset(("code", "run_artifact", "test", "documentation", "decision", "manual"))


class KnowledgePatchStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class LearningProposalBundle:
    manifest: dict[str, object]
    claims: tuple[dict[str, object], ...]
    relations: tuple[dict[str, object], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest", validate_proposal_manifest(self.manifest))
        claims = tuple(validate_claim(claim) for claim in self.claims)
        if not claims:
            raise DomainValidationError("proposed_claims must not be empty")
        _require_unique(tuple(str(claim["id"]) for claim in claims), "proposed_claims")
        object.__setattr__(self, "claims", claims)
        relations = tuple(validate_relation(relation) for relation in self.relations)
        _require_unique(tuple(str(relation["id"]) for relation in relations), "proposed_relations")
        object.__setattr__(self, "relations", relations)


@dataclass(frozen=True, slots=True)
class KnowledgePatchRecord:
    patch_id: str
    run_id: str
    origin_bundle: BundleName
    version: int
    status: KnowledgePatchStatus
    path: str
    proposal_id: str
    summary: str
    created_at: str
    rejected_at: str | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "patch_id", _id(self.patch_id, "patch_id"))
        object.__setattr__(self, "run_id", _safe_segment(self.run_id, "run_id"))
        object.__setattr__(self, "origin_bundle", BundleName(self.origin_bundle))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise DomainValidationError("knowledge patch version must be a positive integer")
        object.__setattr__(self, "status", KnowledgePatchStatus(self.status))
        object.__setattr__(self, "path", require_text(self.path, "knowledge patch path"))
        object.__setattr__(self, "proposal_id", _id(self.proposal_id, "proposal_id"))
        object.__setattr__(self, "summary", require_text(self.summary, "knowledge patch summary"))
        object.__setattr__(self, "created_at", require_text(self.created_at, "created_at"))
        if self.rejected_at is not None:
            object.__setattr__(self, "rejected_at", require_text(self.rejected_at, "rejected_at"))
        if self.rejection_reason is not None:
            object.__setattr__(self, "rejection_reason", require_text(self.rejection_reason, "rejection_reason"))
        if self.status is KnowledgePatchStatus.REJECTED and (self.rejected_at is None or self.rejection_reason is None):
            raise DomainValidationError("rejected knowledge patch requires rejected_at and rejection_reason")
        if self.status is KnowledgePatchStatus.CANDIDATE and (self.rejected_at is not None or self.rejection_reason is not None):
            raise DomainValidationError("candidate knowledge patch must not include rejection metadata")

    def reject(self, reason: str, rejected_at: str) -> "KnowledgePatchRecord":
        return KnowledgePatchRecord(
            patch_id=self.patch_id,
            run_id=self.run_id,
            origin_bundle=self.origin_bundle,
            version=self.version,
            status=KnowledgePatchStatus.REJECTED,
            path=self.path,
            proposal_id=self.proposal_id,
            summary=self.summary,
            created_at=self.created_at,
            rejected_at=rejected_at,
            rejection_reason=reason,
        )


def parse_learning_proposal(value: object) -> LearningProposalBundle:
    document = _object(value, "learning proposal")
    required = {"schema_version", "phase", "proposal_manifest", "proposed_claims"}
    allowed = required | {"proposed_relations"}
    _require_keys(document, required, allowed, "learning proposal")
    if document["schema_version"] != 1 or document["phase"] != "learning":
        raise DomainValidationError("learning proposal version or phase is invalid")
    raw_claims = document["proposed_claims"]
    if not isinstance(raw_claims, list):
        raise DomainValidationError("proposed_claims must be a list")
    raw_relations = document.get("proposed_relations", [])
    if not isinstance(raw_relations, list):
        raise DomainValidationError("proposed_relations must be a list")
    return LearningProposalBundle(
        manifest=_object(document["proposal_manifest"], "proposal_manifest"),
        claims=tuple(_object(item, "claim") for item in raw_claims),
        relations=tuple(_object(item, "relation") for item in raw_relations),
    )


def validate_proposal_manifest(value: object) -> dict[str, object]:
    manifest = _object(value, "proposal_manifest")
    required = {"schema_version", "proposal_id", "summary", "source_artifacts"}
    allowed = required | {"claims_file", "relations_file"}
    _require_keys(manifest, required, allowed, "proposal_manifest")
    if manifest["schema_version"] != 1:
        raise DomainValidationError("proposal_manifest schema_version is unsupported")
    normalized: dict[str, object] = {
        "schema_version": 1,
        "proposal_id": _id(manifest["proposal_id"], "proposal_id"),
        "summary": _string(manifest["summary"], "proposal summary"),
        "source_artifacts": list(_string_list(manifest["source_artifacts"], "source_artifacts")),
    }
    if "claims_file" in manifest:
        if manifest["claims_file"] != "proposed_claims.jsonl":
            raise DomainValidationError("proposal_manifest.claims_file must be proposed_claims.jsonl")
        normalized["claims_file"] = "proposed_claims.jsonl"
    if "relations_file" in manifest:
        if manifest["relations_file"] != "proposed_relations.jsonl":
            raise DomainValidationError("proposal_manifest.relations_file must be proposed_relations.jsonl")
        normalized["relations_file"] = "proposed_relations.jsonl"
    return normalized


def validate_claim(value: object) -> dict[str, object]:
    claim = _object(value, "claim")
    required = {
        "id",
        "domain",
        "subjects",
        "files",
        "symbols",
        "claim_type",
        "text",
        "status",
        "evidence",
        "valid_from",
        "valid_until",
        "last_verified",
    }
    allowed = required | {"metadata"}
    _require_keys(claim, required, allowed, "claim")
    status = _string(claim["status"], "claim.status")
    if status not in CLAIM_STATUSES:
        raise DomainValidationError("claim.status is unsupported")
    evidence = _evidence_list(claim["evidence"], "claim.evidence")
    if status != "unverified" and not evidence:
        raise DomainValidationError("claims without evidence must be marked unverified")
    normalized: dict[str, object] = {
        "id": _id(claim["id"], "claim.id"),
        "domain": _pattern_text(claim["domain"], "claim.domain", _DOMAIN_RE),
        "subjects": list(_string_list(claim["subjects"], "claim.subjects")),
        "files": list(_string_list(claim["files"], "claim.files", nonempty=status != "unverified")),
        "symbols": list(_string_list(claim["symbols"], "claim.symbols", nonempty=False)),
        "claim_type": _pattern_text(claim["claim_type"], "claim.claim_type", _TYPE_RE),
        "text": _string(claim["text"], "claim.text"),
        "status": status,
        "evidence": evidence,
        "valid_from": _optional_string(claim["valid_from"], "claim.valid_from"),
        "valid_until": _optional_string(claim["valid_until"], "claim.valid_until"),
        "last_verified": _optional_string(claim["last_verified"], "claim.last_verified"),
    }
    if "metadata" in claim:
        if not isinstance(claim["metadata"], dict):
            raise DomainValidationError("claim.metadata must be an object")
        normalized["metadata"] = dict(claim["metadata"])
    return normalized


def validate_relation(value: object) -> dict[str, object]:
    relation = _object(value, "relation")
    required = {"id", "domain", "source", "target", "relation_type", "status", "evidence"}
    allowed = required | {"metadata"}
    _require_keys(relation, required, allowed, "relation")
    status = _string(relation["status"], "relation.status")
    if status not in CLAIM_STATUSES:
        raise DomainValidationError("relation.status is unsupported")
    evidence = _evidence_list(relation["evidence"], "relation.evidence")
    if status != "unverified" and not evidence:
        raise DomainValidationError("relations without evidence must be marked unverified")
    normalized: dict[str, object] = {
        "id": _id(relation["id"], "relation.id"),
        "domain": _pattern_text(relation["domain"], "relation.domain", _DOMAIN_RE),
        "source": _id(relation["source"], "relation.source"),
        "target": _id(relation["target"], "relation.target"),
        "relation_type": _pattern_text(relation["relation_type"], "relation.relation_type", _TYPE_RE),
        "status": status,
        "evidence": evidence,
    }
    if "metadata" in relation:
        if not isinstance(relation["metadata"], dict):
            raise DomainValidationError("relation.metadata must be an object")
        normalized["metadata"] = dict(relation["metadata"])
    return normalized


def _evidence_list(value: object, field: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise DomainValidationError(f"{field} must be a list")
    return [validate_evidence(item) for item in value]


def validate_evidence(value: object) -> dict[str, object]:
    evidence = _object(value, "evidence")
    allowed = {"type", "file", "artifact", "symbol", "commit", "line_start", "line_end", "excerpt", "url"}
    _require_keys(evidence, {"type"}, allowed, "evidence")
    kind = _pattern_text(evidence["type"], "evidence.type", _TYPE_RE)
    if kind not in EVIDENCE_TYPES:
        raise DomainValidationError("evidence.type is unsupported")
    if not any(isinstance(evidence.get(key), str) and str(evidence.get(key)).strip() for key in ("file", "artifact", "url")):
        raise DomainValidationError("evidence must include file, artifact, or url")
    normalized: dict[str, object] = {"type": kind}
    for key in ("file", "artifact", "symbol", "commit", "excerpt", "url"):
        if key in evidence:
            normalized[key] = _string(evidence[key], f"evidence.{key}")
    for key in ("line_start", "line_end"):
        if key in evidence:
            if isinstance(evidence[key], bool) or not isinstance(evidence[key], int) or evidence[key] < 1:
                raise DomainValidationError(f"evidence.{key} must be a positive integer")
            normalized[key] = evidence[key]
    if "line_start" in normalized and "line_end" in normalized and int(normalized["line_end"]) < int(normalized["line_start"]):
        raise DomainValidationError("evidence line_end must be greater than or equal to line_start")
    return normalized


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DomainValidationError(f"{name} must be an object")
    return dict(value)


def _require_keys(value: dict[str, object], required: set[str], allowed: set[str], name: str) -> None:
    keys = set(value)
    if not required <= keys or not keys <= allowed:
        raise DomainValidationError(f"{name} has invalid fields")


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field} must be a nonempty string")
    return value.strip()


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field)


def _pattern_text(value: object, field: str, pattern: re.Pattern[str]) -> str:
    text = _string(value, field)
    if not pattern.fullmatch(text):
        raise DomainValidationError(f"{field} has invalid format")
    return text


def _id(value: object, field: str) -> str:
    return _pattern_text(value, field, _ID_RE)


def _safe_segment(value: object, field: str) -> str:
    text = _string(value, field)
    if not _SAFE_SEGMENT_RE.fullmatch(text):
        raise DomainValidationError(f"{field} must be a safe path segment")
    return text


def _string_list(value: object, field: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        raise DomainValidationError(f"{field} must be a valid list")
    items = tuple(_string(item, field) for item in value)
    _require_unique(items, field)
    return items


def _require_unique(values: tuple[str, ...], field: str) -> None:
    if len(values) != len(set(values)):
        raise DomainValidationError(f"{field} must not contain duplicates")
