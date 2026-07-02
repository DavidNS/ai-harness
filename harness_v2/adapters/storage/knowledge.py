"""Knowledge patch storage adapters for v2."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

from harness_v2.adapters.storage.file import (
    _ensure_safe_directory_tree,
    _fsync_directory,
    _require_safe_directory,
)
from harness_v2.backend.domain.knowledge import (
    KnowledgePatchRecord,
    KnowledgePatchStatus,
    LearningProposalBundle,
)
from harness_v2.backend.domain.lifecycle import BundleName
from harness_v2.backend.ports.knowledge_patch_store import KnowledgePatchNotFoundError, KnowledgePatchStoreError

MANIFEST_FILE = "proposal_manifest.json"
CLAIMS_FILE = "proposed_claims.jsonl"
RELATIONS_FILE = "proposed_relations.jsonl"
PATCH_STATE_FILE = "patch_state.json"


class InMemoryKnowledgePatchStore:
    """Knowledge patch store backed by process-local records."""

    def __init__(self) -> None:
        self._patches: dict[str, KnowledgePatchRecord] = {}

    def create_patch(
        self,
        run_id: str,
        origin_bundle: BundleName,
        proposal: LearningProposalBundle,
        created_at: str,
    ) -> KnowledgePatchRecord:
        bundle = BundleName(origin_bundle)
        version = self._next_version(run_id, bundle)
        patch_id = _patch_id(run_id, bundle, version)
        record = KnowledgePatchRecord(
            patch_id=patch_id,
            run_id=run_id,
            origin_bundle=bundle,
            version=version,
            status=KnowledgePatchStatus.CANDIDATE,
            path=_patch_path(run_id, bundle, version),
            proposal_id=str(proposal.manifest["proposal_id"]),
            summary=str(proposal.manifest["summary"]),
            created_at=created_at,
        )
        self._patches[patch_id] = record
        return record

    def get_patch(self, patch_id: str) -> KnowledgePatchRecord:
        try:
            return self._patches[patch_id]
        except KeyError as exc:
            raise KnowledgePatchNotFoundError(patch_id) from exc

    def list_patches(
        self,
        run_id: str | None = None,
        status: KnowledgePatchStatus | None = None,
    ) -> tuple[KnowledgePatchRecord, ...]:
        normalized_status = None if status is None else KnowledgePatchStatus(status)
        records = self._patches.values()
        if run_id is not None:
            records = [record for record in records if record.run_id == run_id]
        if normalized_status is not None:
            records = [record for record in records if record.status is normalized_status]
        return tuple(sorted(records, key=lambda record: record.patch_id))

    def reject_patch(self, patch_id: str, reason: str, rejected_at: str) -> KnowledgePatchRecord:
        record = self.get_patch(patch_id).reject(reason, rejected_at)
        self._patches[patch_id] = record
        return record

    def _next_version(self, run_id: str, bundle: BundleName) -> int:
        versions = [record.version for record in self._patches.values() if record.run_id == run_id and record.origin_bundle == bundle]
        return max(versions, default=0) + 1


class FileKnowledgePatchStore:
    """File-backed candidate patch store under knowledge-source/patches/pending."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def create_patch(
        self,
        run_id: str,
        origin_bundle: BundleName,
        proposal: LearningProposalBundle,
        created_at: str,
    ) -> KnowledgePatchRecord:
        bundle = BundleName(origin_bundle)
        version = self._next_version(run_id, bundle)
        record = KnowledgePatchRecord(
            patch_id=_patch_id(run_id, bundle, version),
            run_id=run_id,
            origin_bundle=bundle,
            version=version,
            status=KnowledgePatchStatus.CANDIDATE,
            path=_patch_path(run_id, bundle, version),
            proposal_id=str(proposal.manifest["proposal_id"]),
            summary=str(proposal.manifest["summary"]),
            created_at=created_at,
        )
        directory = _ensure_safe_directory_tree(self._root, tuple(record.path.split("/")))
        _write_json(directory / MANIFEST_FILE, proposal.manifest)
        _write_text(directory / CLAIMS_FILE, _render_jsonl(proposal.claims))
        if proposal.relations:
            _write_text(directory / RELATIONS_FILE, _render_jsonl(proposal.relations))
        _write_json(directory / PATCH_STATE_FILE, _record_payload(record))
        _fsync_directory(directory)
        return record

    def get_patch(self, patch_id: str) -> KnowledgePatchRecord:
        for record in self.list_patches():
            if record.patch_id == patch_id:
                return record
        raise KnowledgePatchNotFoundError(patch_id)

    def list_patches(
        self,
        run_id: str | None = None,
        status: KnowledgePatchStatus | None = None,
    ) -> tuple[KnowledgePatchRecord, ...]:
        normalized_status = None if status is None else KnowledgePatchStatus(status)
        pending = self._pending_root()
        if pending is None:
            return ()
        records: list[KnowledgePatchRecord] = []
        for state_path in sorted(pending.glob("*/*/v*/" + PATCH_STATE_FILE)):
            _require_safe_directory(state_path.parent)
            record = _record_from_payload(_read_json(state_path))
            if run_id is not None and record.run_id != run_id:
                continue
            if normalized_status is not None and record.status is not normalized_status:
                continue
            records.append(record)
        return tuple(sorted(records, key=lambda record: record.patch_id))

    def reject_patch(self, patch_id: str, reason: str, rejected_at: str) -> KnowledgePatchRecord:
        record = self.get_patch(patch_id).reject(reason, rejected_at)
        state_path = self._root / record.path / PATCH_STATE_FILE
        _write_json(state_path, _record_payload(record))
        _fsync_directory(state_path.parent)
        return record

    def _next_version(self, run_id: str, bundle: BundleName) -> int:
        versions = [record.version for record in self.list_patches(run_id=run_id) if record.origin_bundle == bundle]
        return max(versions, default=0) + 1

    def _pending_root(self) -> Path | None:
        current = self._root
        for part in ("knowledge-source", "patches", "pending"):
            if current.exists() or current.is_symlink():
                _require_safe_directory(current)
            else:
                return None
            current = current / part
        if current.exists() or current.is_symlink():
            _require_safe_directory(current)
            return current
        return None


def _patch_id(run_id: str, bundle: BundleName, version: int) -> str:
    return f"patch.{run_id}.{bundle.value.lower()}.v{version:04d}"


def _patch_path(run_id: str, bundle: BundleName, version: int) -> str:
    return f"knowledge-source/patches/pending/{run_id}/{bundle.value.lower()}/v{version:04d}"


def _render_jsonl(items: tuple[dict[str, object], ...]) -> str:
    return "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in items)


def _record_payload(record: KnowledgePatchRecord) -> dict[str, object]:
    payload = asdict(record)
    payload["origin_bundle"] = record.origin_bundle.value
    payload["status"] = record.status.value
    return payload


def _record_from_payload(payload: dict[str, object]) -> KnowledgePatchRecord:
    try:
        return KnowledgePatchRecord(
            patch_id=str(payload["patch_id"]),
            run_id=str(payload["run_id"]),
            origin_bundle=BundleName(str(payload["origin_bundle"])),
            version=int(payload["version"]),
            status=KnowledgePatchStatus(str(payload["status"])),
            path=str(payload["path"]),
            proposal_id=str(payload["proposal_id"]),
            summary=str(payload["summary"]),
            created_at=str(payload["created_at"]),
            rejected_at=None if payload.get("rejected_at") is None else str(payload["rejected_at"]),
            rejection_reason=None if payload.get("rejection_reason") is None else str(payload["rejection_reason"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise KnowledgePatchStoreError("knowledge patch state is malformed") from exc


def _write_json(path: Path, value: dict[str, object]) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise KnowledgePatchStoreError(f"knowledge patch state is malformed JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise KnowledgePatchStoreError("knowledge patch state must be an object")
    return payload


def _write_text(path: Path, value: str) -> None:
    if path.exists() and path.is_symlink():
        raise KnowledgePatchStoreError(f"unsafe knowledge patch path contains a symlink: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o666)
    except OSError as exc:
        if path.is_symlink():
            raise KnowledgePatchStoreError(f"unsafe knowledge patch path contains a symlink: {path}") from exc
        raise
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
