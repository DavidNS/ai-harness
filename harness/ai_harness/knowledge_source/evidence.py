"""Repository-backed evidence validation policy."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Mapping

from ..repository_policy import default_repository_policy, load_repository_policy
from .contracts import REPOSITORY_EVIDENCE_TYPES, LearningProposalBundle
from .validation import _fail, _string


def _repository_relative_path(value: object, name: str) -> PurePosixPath:
    text = _string(value, name).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail(f"{name} must be a repository-relative path")
    if any(part.startswith(".") for part in path.parts):
        _fail(f"{name} must not point to generated or hidden runtime paths")
    if path.parts[:3] == ("knowledge-source", "patches", "pending"):
        _fail(f"{name} must not point to pending knowledge patches")
    return path


def is_repository_backed_evidence(evidence: Mapping[str, object], repository_root: Path | None = None) -> bool:
    if evidence.get("type") not in REPOSITORY_EVIDENCE_TYPES or "file" not in evidence:
        return False
    relative = _repository_relative_path(evidence.get("file"), "evidence.file")
    policy = default_repository_policy() if repository_root is None else load_repository_policy(Path(repository_root))
    if policy.ignores(relative):
        _fail("evidence.file must not point to generated or ignored repository paths")
    if repository_root is None:
        return True
    root = Path(repository_root).resolve()
    candidate = (root / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        _fail("evidence.file escapes the repository root")
    if not candidate.is_file():
        _fail("evidence.file must exist in the repository")
    return True

def validate_repository_evidence_policy(bundle: LearningProposalBundle, repository_root: Path | None = None) -> None:
    for claim in bundle.claims:
        if claim.get("status") == "unverified":
            continue
        if not any(is_repository_backed_evidence(item, repository_root) for item in claim.get("evidence", [])):
            _fail("active claims require at least one repository-backed evidence item")
    for relation in bundle.relations:
        if relation.get("status") == "unverified":
            continue
        if not any(is_repository_backed_evidence(item, repository_root) for item in relation.get("evidence", [])):
            _fail("active relations require at least one repository-backed evidence item")
