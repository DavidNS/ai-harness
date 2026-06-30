"""Explorer bundle planning and publication services.

BundlePlanner keeps the validation/planning pass side-effect free.
ExplorerPublisher owns canonical artifact writes, analysis manifests,
knowledge proposals, and extraction telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping

from ..canonical import CanonicalDocs, checksum
from ..contracts.enums import PhaseName
from ..control_outputs import ExplorerBundle, ExplorerBundleEntry
from ..errors import HarnessError
from ..knowledge_source import KnowledgeSourceError, pending_patch_path
from ..phases import get_phase
from .classification import explorer_kind as _explorer_kind
from .evidence_extraction import EvidenceExtractor
from .explorer_context import (
    ExplorerContext,
    ExplorerExtractionContext,
)
from .explorer_handoff import build_explorer_handoff, sanitize_manifest_title
from .learning_service import LearningService
from .phase_learning_extractor import PhaseLearningExtractor
from .quality import ImprovementQualityGate

# ------------------------------------------------------------------ #
# Data contract                                                        #
# ------------------------------------------------------------------ #

@dataclass(frozen=True, slots=True)
class _ExplorerPublishPlan:
    entry: ExplorerBundleEntry
    canonical_kind: str
    action: str
    path: str | None = None
    record: dict[str, object] | None = None


# ------------------------------------------------------------------ #
# Pure helpers (used by BundlePlanner and by the mixin writer shims)  #
# ------------------------------------------------------------------ #

def entry_canonical_kind(entry: ExplorerBundleEntry, content: str) -> str:
    if entry.action == "documentation_task":
        return "improvement"
    if entry.action == "existing_functionality":
        return "existing-functionality"
    if entry.artifact_kind == "documentation":
        return "improvement"
    if entry.artifact_kind in {"improvement", "limitation", "bullshit", "existing-functionality"}:
        return entry.artifact_kind
    return _explorer_kind(content)


def analysis_manifest_record(
    entry: ExplorerBundleEntry,
    record: Mapping[str, object],
    *,
    split_rationale: str | None = None,
    knowledge_proposal: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"entry_id": entry.entry_id, "title": sanitize_manifest_title(entry.title, content=entry.content), **dict(record)}
    if entry.reason is not None:
        payload["reason"] = entry.reason
    if split_rationale is not None:
        payload["split_rationale"] = split_rationale
    if knowledge_proposal is not None:
        payload["knowledge_proposal"] = knowledge_proposal
    return payload


# ------------------------------------------------------------------ #
# BundlePlanner                                                        #
# ------------------------------------------------------------------ #

class BundlePlanner:
    """Plans publication of an ExplorerBundle without writing anything.

    Cheap to instantiate per call — the heavy work happens inside plan_bundle().
    """

    def __init__(
        self,
        canonical: CanonicalDocs,
        quality_gate: ImprovementQualityGate,
        repository_observations: list[dict[str, object]],
        *,
        explorer_artifact_path_fn: Callable[[str], str],
        parse_learning_sections_fn: Callable,
    ) -> None:
        self._canonical = canonical
        self._quality_gate = quality_gate
        self._repository_observations = repository_observations
        self._explorer_artifact_path = explorer_artifact_path_fn
        self._parse_learning_sections = parse_learning_sections_fn

    def bundle_improvement_path(self, entry: ExplorerBundleEntry, content: str) -> str:
        return entry.path if entry.path is not None else self._explorer_artifact_path(content)

    def bundle_split_child_ids(self, bundle: ExplorerBundle) -> frozenset[str]:
        entry_ids: list[str] = []
        paths: list[str] = []
        for entry in bundle.entries:
            if entry.entry_id in {"legacy", "single"} or entry.action in {"no-op", "documentation_task"}:
                continue
            if entry.content is None or not self._quality_gate.is_compact_improvement(entry.content):
                continue
            try:
                if entry_canonical_kind(entry, entry.content) != "improvement":
                    continue
                paths.append(self.bundle_improvement_path(entry, entry.content))
            except Exception:
                continue
            entry_ids.append(entry.entry_id)
        if len(entry_ids) < 2 or len(paths) != len(set(paths)):
            return frozenset()
        return frozenset(entry_ids)

    def plan_entry(
        self,
        entry: ExplorerBundleEntry,
        *,
        split_child_ids: frozenset[str],
    ) -> _ExplorerPublishPlan:
        if entry.action == "no-op":
            record: dict[str, object] = {
                "action": "no-op",
                "kind": entry.artifact_kind or "explorer",
                "reason": entry.reason,
            }
            if entry.path is not None:
                record["path"] = entry.path
                if self._canonical.exists(entry.path):
                    record["checksum"] = checksum(self._canonical.read(entry.path))
            return _ExplorerPublishPlan(
                entry, str(record["kind"]), "record", entry.path,
                analysis_manifest_record(entry, record),
            )

        assert entry.content is not None
        if entry.action == "existing_functionality" and entry.content.startswith("# Learning v2"):
            self._parse_learning_sections(entry.content)
        else:
            get_phase("explorer").validate(entry.content)
        canonical_kind = entry_canonical_kind(entry, entry.content)
        if canonical_kind == "existing-functionality":
            return _ExplorerPublishPlan(entry, canonical_kind, "existing_functionality")
        if canonical_kind == "improvement" and not self._quality_gate.is_compact_improvement(entry.content):
            raise HarnessError("explorer bundle improvement entries must use the concise # Improvement format")

        split_child = entry.entry_id in split_child_ids
        if entry.action == "update":
            assert entry.path is not None and entry.expected_checksum is not None
            if canonical_kind != "improvement":
                raise HarnessError("explorer bundle updates are only supported for improvement artifacts")
            if not (entry.path.startswith("docs/explorer/improvements/") or entry.path.startswith("docs/analysis/improvements/")) or not entry.path.endswith("/improvement.md"):
                raise HarnessError("update intent must target docs/explorer/improvements/<slug>/.../improvement.md")
            if not self._canonical.exists(entry.path):
                raise HarnessError("cannot update missing improvement artifact")
            if checksum(self._canonical.read(entry.path)) != entry.expected_checksum:
                raise HarnessError("canonical update checksum mismatch")
            self._quality_gate.validate_compact_improvement_quality(
                entry.content, entry,
                split_child=split_child,
                observations=self._repository_observations,
            )
            return _ExplorerPublishPlan(entry, canonical_kind, "update", entry.path)

        if canonical_kind == "improvement":
            self._quality_gate.validate_compact_improvement_quality(
                entry.content, entry,
                split_child=split_child,
                observations=self._repository_observations,
            )
        if entry.path is not None and canonical_kind == "improvement":
            path = entry.path
        else:
            path = self._explorer_artifact_path(entry.content)
        return _ExplorerPublishPlan(entry, canonical_kind, "write", path)

    def plan_bundle(self, bundle: ExplorerBundle) -> list[_ExplorerPublishPlan]:
        split_child_ids = self.bundle_split_child_ids(bundle)
        plans: list[_ExplorerPublishPlan] = []
        for entry in bundle.entries:
            try:
                plans.append(self.plan_entry(entry, split_child_ids=split_child_ids))
            except Exception as exc:
                raise HarnessError(f"explorer bundle entry {entry.entry_id}: {exc}") from exc
        return plans


class ExplorerPublisher:
    """Publishes explorer bundles and related knowledge side effects."""

    def __init__(
        self,
        canonical: CanonicalDocs,
        artifacts: object,
        state: object,
        warnings: list[str],
        target: Path,
        *,
        repository_observations_fn: Callable[[], list[dict[str, object]]],
        stage_json_fn: Callable[[str], dict[str, object]],
        safe_stage_json_fn: Callable[[str], dict[str, object]],
        learning_service_fn: Callable[[], LearningService],
        knowledge_synthesis_inputs_fn: Callable[..., dict[str, object]],
        invoke_knowledge_synthesis_with_repair_fn: Callable[[Mapping[str, object]], str],
        distilled_compact_improvement_fn: Callable[..., str],
        explorer_artifact_path_fn: Callable[[str], str],
        parse_learning_sections_fn: Callable[..., object],
    ) -> None:
        self._canonical = canonical
        self._artifacts = artifacts
        self._state = state
        self._warnings = warnings
        self._target = target
        self._repository_observations = repository_observations_fn
        self._stage_json = stage_json_fn
        self._safe_stage_json = safe_stage_json_fn
        self._learning_service = learning_service_fn
        self._knowledge_synthesis_inputs = knowledge_synthesis_inputs_fn
        self._invoke_knowledge_synthesis_with_repair = invoke_knowledge_synthesis_with_repair_fn
        self._distilled_compact_improvement = distilled_compact_improvement_fn
        self._explorer_artifact_path = explorer_artifact_path_fn
        self._parse_learning_sections = parse_learning_sections_fn
        self._extraction_records: list[dict[str, object]] = []

    @staticmethod
    def claim_type_for_explorer_kind(artifact_kind: str) -> str:
        normalized = artifact_kind.replace("_", "-")
        if normalized == "limitation":
            return "constraint"
        if normalized == "bullshit":
            return "decision"
        if normalized == "improvement":
            return "decision"
        return "responsibility"

    def _make_evidence_extractor(self) -> EvidenceExtractor:
        return EvidenceExtractor(
            self._target,
            self._repository_observations(),
            stage_json_fn=self._stage_json,
        )

    def _make_bundle_planner(self) -> BundlePlanner:
        return BundlePlanner(
            self._canonical,
            ImprovementQualityGate(),
            self._repository_observations(),
            explorer_artifact_path_fn=self._explorer_artifact_path,
            parse_learning_sections_fn=self._parse_learning_sections,
        )

    def publish_analysis_manifest(
        self,
        records: list[dict[str, object]],
        *,
        primary_entry: str | None,
        target_phase: str,
        split_bundle_rationale: str | None = None,
        handoff_artifact: str | None = None,
    ) -> None:
        primary = None
        if primary_entry is not None:
            primary = next((item for item in records if item.get("entry_id") == primary_entry and (item.get("path") or item.get("suggested_path"))), None)
        if primary is None:
            primary = next((item for item in records if (item.get("path") or item.get("suggested_path")) and item.get("action") in {"created", "updated", "recorded"}), None)
        if primary is None:
            primary = next((item for item in records if item.get("path") or item.get("suggested_path")), None)
        manifest: dict[str, object] = {
            "manifest_version": 1,
            "primary_artifact": (primary.get("path") or primary.get("suggested_path")) if primary else None,
            "artifacts": records,
        }
        if split_bundle_rationale is not None:
            manifest["split_bundle_rationale"] = split_bundle_rationale
        if handoff_artifact is not None:
            manifest["handoff_artifact"] = handoff_artifact
        if primary is not None:
            for key in ("kind", "path", "suggested_path", "checksum"):
                if key in primary:
                    manifest[key] = primary[key]
        artifact = "published/explorer.json"
        self._artifacts.write_json(artifact, manifest)
        self._state.record_artifact(artifact, target_phase)

    def publish_entry_proposal(
        self,
        entry: ExplorerBundleEntry,
        artifact_kind: str,
        context: ExplorerContext,
    ) -> str | None:
        assert entry.content is not None
        learning_service = self._learning_service()
        learning = entry.content if entry.content.startswith("# Learning v2") else learning_service.explorer_learning(entry.content, kind=artifact_kind)
        accepted, rejected, sources_checked = self._make_evidence_extractor().extract(entry)
        rejected = [item for item in rejected if item.get("reason") not in {"missing_path", "path_missing"}]
        mapped_claim_type = self.claim_type_for_explorer_kind(artifact_kind)
        claim_status = "active" if accepted else "unverified"
        state = self._state.load()
        record: dict[str, object] = {
            "run_id": state.run_id,
            "phase": state.current_phase,
            "entry_id": entry.entry_id,
            "artifact_kind": artifact_kind,
            "requested_claim_type": artifact_kind,
            "mapped_claim_type": mapped_claim_type,
            "claim_status": claim_status,
            "evidence_sources_checked": sources_checked,
            "evidence_accepted": accepted,
            "evidence_rejected": rejected,
        }
        if accepted:
            record["outcome"] = "proposal_created"
        else:
            reason = "repository_evidence_rejected" if rejected else "missing_repository_evidence"
            record["outcome"] = "skipped_no_repo_evidence"
            record["failure_code"] = reason
            record["failure_message"] = (
                "Repository evidence candidates were rejected; emitted an unverified proposal."
                if rejected else
                "No repository-backed evidence was available; emitted an unverified proposal."
            )
        try:
            extraction_context = ExplorerExtractionContext(
                entry_id=entry.entry_id,
                artifact_kind=artifact_kind,
                learning=learning,
                entry_content=entry.content,
                intake=self._safe_stage_json("explorer_intake"),
                discovery=self._safe_stage_json("explorer_discovery"),
                decision=self._safe_stage_json("explorer_decision"),
                review=(
                    self._artifacts.read("explorer/review.md")
                    if "explorer/review.md" in self._artifacts.list()
                    else ""
                ),
                related_improvements=context.related_improvements,
                repository_observations=context.repository_observations,
                evidence_sources_checked=sources_checked,
            )
            result = PhaseLearningExtractor(
                knowledge_synthesis_inputs_fn=self._knowledge_synthesis_inputs,
                invoke_knowledge_synthesis_with_repair_fn=self._invoke_knowledge_synthesis_with_repair,
                learning_service_fn=self._learning_service,
            ).synthesize_and_publish(
                "explorer",
                phase=PhaseName.EXPLORE_BUNDLE,
                context=extraction_context.synthesis_context(),
                accepted_evidence=accepted,
                rejected_evidence=rejected,
                source_artifacts=["explorer_artifact", "explorer_decision"],
            )
            record["proposal_path"] = result.proposal_path
            return result.proposal_path
        except Exception as exc:
            text = " ".join(str(exc).split())[:500]
            if isinstance(exc, KnowledgeSourceError):
                record["outcome"] = "failed_evidence_validation"
            elif "knowledge_review" in text or "Knowledge Review" in text:
                record["outcome"] = "failed_review"
            else:
                record["outcome"] = "failed_extraction"
            record["failure_code"] = type(exc).__name__
            record["failure_message"] = text
            self._warnings.append(f"Knowledge proposal failed for {entry.entry_id}: {exc}")
            return None
        finally:
            self._extraction_records.append(record)

    def publish_existing_functionality_entry(
        self,
        entry: ExplorerBundleEntry,
        context: ExplorerContext,
        *,
        split_rationale: str | None = None,
    ) -> dict[str, object]:
        assert entry.content is not None
        proposal_path = self.publish_entry_proposal(
            entry,
            artifact_kind="existing-functionality",
            context=context,
        )
        if proposal_path is None:
            proposal_path = pending_patch_path(self._state.load().run_id)
        payload = {
            "action": "created",
            "kind": "existing-functionality",
            "path": proposal_path,
        }
        return analysis_manifest_record(
            entry,
            payload,
            split_rationale=split_rationale,
            knowledge_proposal=proposal_path,
        )

    def publish_handoff(
        self,
        bundle: ExplorerBundle,
        records: list[dict[str, object]],
        *,
        pre_distilled_content: Mapping[str, str] | None,
        target_phase: str,
    ) -> str:
        handoff = build_explorer_handoff(
            bundle=bundle,
            records=records,
            discovery=self._safe_stage_json("explorer_discovery"),
            decision=self._safe_stage_json("explorer_decision"),
            pre_distilled_content=pre_distilled_content,
        )
        artifact = "published/explorer-handoff.json"
        self._artifacts.write_json(artifact, handoff)
        self._state.record_artifact(artifact, target_phase)
        return artifact

    def publish_extraction_telemetry(self, target_phase: str) -> None:
        if not self._extraction_records:
            return
        artifact = "published/explorer-knowledge-extraction.json"
        self._artifacts.write_json(artifact, {
            "schema_version": 1,
            "records": self._extraction_records,
        })
        self._state.record_artifact(artifact, target_phase)
        if any(record.get("outcome") != "proposal_created" for record in self._extraction_records):
            self._warnings.append(f"Explorer knowledge extraction details recorded in {artifact}")

    def publish_bundle(
        self,
        bundle: ExplorerBundle,
        context: ExplorerContext,
        *,
        target_phase: str = PhaseName.EXPLORE_BUNDLE,
        split_bundle_rationale: str | None = None,
        pre_distilled_content: Mapping[str, str] | None = None,
    ) -> None:
        self._extraction_records = []
        planner = self._make_bundle_planner()
        plans = planner.plan_bundle(bundle)
        records: list[dict[str, object]] = []
        for plan in plans:
            entry = plan.entry
            if plan.record is not None:
                record = dict(plan.record)
                if split_bundle_rationale is not None and "split_rationale" not in record:
                    record["split_rationale"] = split_bundle_rationale
                records.append(record)
                continue
            assert entry.content is not None
            content = (
                pre_distilled_content[entry.entry_id]
                if pre_distilled_content is not None and entry.entry_id in pre_distilled_content
                else entry.content
            )
            learning_entry = replace(entry, content=content)
            proposal_path: str | None = None
            if plan.canonical_kind in {"improvement", "limitation", "bullshit", "existing-functionality"}:
                proposal_path = self.publish_entry_proposal(
                    learning_entry,
                    artifact_kind=plan.canonical_kind,
                    context=context,
                )
            record: dict[str, object] = {
                "action": "recorded",
                "bundle_action": entry.action,
                "kind": plan.canonical_kind,
            }
            if plan.path is not None:
                record["suggested_path"] = plan.path
            records.append(analysis_manifest_record(
                entry,
                record,
                split_rationale=split_bundle_rationale,
                knowledge_proposal=proposal_path,
            ))
        handoff_artifact = self.publish_handoff(
            bundle,
            records,
            pre_distilled_content=pre_distilled_content,
            target_phase=target_phase,
        )
        self.publish_analysis_manifest(
            records,
            primary_entry=bundle.primary_entry,
            target_phase=target_phase,
            split_bundle_rationale=split_bundle_rationale,
            handoff_artifact=handoff_artifact,
        )
        self.publish_extraction_telemetry(target_phase)
