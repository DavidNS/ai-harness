"""Knowledge synthesis phase implementation shared by knowledge bundles."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.common import _source_artifacts
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName

_CONTEXT_LIMIT = 100_000
_ARTIFACT_LIMIT = 20_000
_REPOSITORY_FILE_LIMIT = 8_000
_REPOSITORY_ENTRY_LIMIT = 12


def execute(context: PhaseExecutionContext) -> PhaseResult:
    source_bundle, required = _knowledge_source(context.bundle)
    source_artifacts = _source_artifacts(context, required)
    output = context.artifacts.run_worker_text(
        context.run,
        context.bundle or BundleName.KNOWLEDGE_EXTRACT_EXPLORE,
        context.phase or PhaseName.KNOWLEDGE_EXTRACT_SYNTHESIS,
        "knowledge_synthesis",
        build_knowledge_inputs(context, source_bundle, source_artifacts),
    )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise BundleValidationError("knowledge_synthesis output must be valid JSON") from exc
    context.artifacts.write_json(context.run.run_id, f"knowledge/{context.bundle.value}/synthesis.json", payload)
    return PhaseResult()


def build_knowledge_inputs(
    context: PhaseExecutionContext,
    source_bundle: BundleName,
    source_artifacts: Mapping[str, Any],
) -> dict[str, object]:
    """Build the single v1-style knowledge extraction envelope.

    v2 still uses milestone bundles to decide when extraction runs, but the
    worker should see one broad context shape rather than bespoke per-bundle
    inputs. The top-level compatibility fields are retained for existing
    scripted providers and prompts.
    """

    run = context.run
    inventory = context.artifacts.list_artifacts(run.run_id)
    selected_artifacts = _selected_artifacts(context, inventory, source_artifacts)
    repository_snapshot = _repository_snapshot(context.runtime.working_directory, selected_artifacts)
    entry_contexts = _entry_contexts(selected_artifacts.get("explore/outcome_bundle.json"))
    run_context = {
        "run_id": run.run_id,
        "request": run.request,
        "status": run.status.value,
        "root_bundle": run.root_bundle.value,
        "current_bundle": run.current_bundle.value if run.current_bundle else None,
        "current_phase": run.current_phase.value if run.current_phase else None,
        "completed_phases": [phase.value for phase in run.completed_phases],
    }
    return {
        "source": source_bundle.value.lower(),
        "source_phase": source_bundle.value.lower(),
        "run_id": run.run_id,
        "request": run.request,
        "run": run_context,
        "source_artifacts": dict(source_artifacts),
        "artifact_inventory": list(inventory),
        "selected_artifacts": selected_artifacts,
        "tasks": [_task_to_mapping(task) for task in run.tasks],
        "decision_history": [_decision_to_mapping(decision) for decision in run.decision_history],
        "errors": [_error_to_mapping(error) for error in run.errors],
        "repository_snapshot": repository_snapshot,
        "entry_contexts": entry_contexts,
        "context": {
            "run": run_context,
            "artifact_inventory": list(inventory),
            "selected_artifacts": selected_artifacts,
            "repository_snapshot": repository_snapshot,
            "entry_contexts": entry_contexts,
        },
        "accepted_evidence": [],
        "rejected_evidence": [],
        "repair": {},
    }


def _entry_contexts(bundle: object) -> list[dict[str, object]]:
    if not isinstance(bundle, Mapping):
        return []
    evidence_by_id = {
        str(item.get("id")): item
        for item in _mapping_items(bundle.get("evidence"))
        if isinstance(item.get("id"), str) and item.get("id")
    }
    exploration_map = bundle.get("exploration_map") if isinstance(bundle.get("exploration_map"), Mapping) else {}
    contexts: list[dict[str, object]] = []
    for entry in _mapping_items(bundle.get("entries")):
        entry_id = _text(entry.get("id"))
        evidence_refs = [_text(ref) for ref in _list_items(entry.get("evidence_refs")) if _text(ref)]
        target = entry.get("target") if isinstance(entry.get("target"), Mapping) else {}
        target_path = _text(target.get("path")) if isinstance(target, Mapping) else ""
        contexts.append({
            "entry_id": entry_id,
            "classification": _text(entry.get("classification")),
            "action": _text(entry.get("action")),
            "title": _text(entry.get("title")),
            "target": dict(target) if isinstance(target, Mapping) else {},
            "evidence_refs": evidence_refs,
            "evidence": [_compact_evidence(evidence_by_id[ref]) for ref in evidence_refs if ref in evidence_by_id],
            "map_signals": _entry_map_signals(exploration_map, target_path),
            "expected_status": _expected_claim_status(_text(entry.get("action"))),
        })
    return contexts


def _entry_map_signals(exploration_map: object, target_path: str) -> dict[str, object]:
    if not isinstance(exploration_map, Mapping):
        return {}
    signals: dict[str, object] = {}
    for section in ("existing_functionality", "similar_functionality"):
        items = _matching_map_items(exploration_map.get(section), target_path)
        if items:
            signals[section] = items
    duplicate_search = exploration_map.get("duplicate_search")
    if isinstance(duplicate_search, Mapping):
        matches = _matching_map_items(duplicate_search.get("matches"), target_path)
        if matches:
            signals["duplicate_matches"] = matches
        terms = [_text(term) for term in _list_items(duplicate_search.get("searched_terms")) if _text(term)]
        if terms:
            signals["searched_terms"] = terms[:12]
    return signals


def _matching_map_items(value: object, target_path: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in _mapping_items(value):
        path = _text(item.get("path"))
        if target_path and path and path != target_path:
            continue
        compact = {key: item[key] for key in ("id", "kind", "path", "summary", "confidence", "source_id", "source_kind") if key in item and item[key] not in (None, "", [], {})}
        if compact:
            items.append(compact)
    return items[:6]


def _compact_evidence(item: Mapping[str, object]) -> dict[str, object]:
    return {key: item[key] for key in ("id", "claim", "status", "confidence", "sources") if key in item and item[key] not in (None, "", [], {})}


def _expected_claim_status(action: str) -> str:
    if action in {"create", "update_existing", "document_limitation"}:
        return "accepted"
    if action in {"duplicate_noop", "existing_functionality", "reject"}:
        return "rejected_or_existing"
    if action == "ask_user":
        return "pending_decision"
    if action == "blocked":
        return "blocked"
    return "unknown"


def _mapping_items(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _list_items(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _knowledge_source(bundle: BundleName | None) -> tuple[BundleName, tuple[str, ...]]:
    if bundle is BundleName.KNOWLEDGE_EXTRACT_TDD:
        return BundleName.TDD_BUNDLE, ("published/tdd-results.json", "published/tdd-handoff.json")
    return BundleName.EXPLORE_BUNDLE, ("explore/outcome_bundle.json", "published/explore-handoff.json")


def _selected_artifacts(
    context: PhaseExecutionContext,
    inventory: tuple[str, ...],
    source_artifacts: Mapping[str, Any],
) -> dict[str, object]:
    preferred = (
        "route.json",
        "strategy.json",
        "explorer_gate.json",
        "explore/request_profile.json",
        "explore/context_pack.json",
        "explore/evidence_digest.json",
        "explore/exploration_map.json",
        "explore/outcome_bundle.json",
        "published/explore-handoff.json",
        "purpose/bundle.json",
        "spec.json",
        "design.json",
        "tasks.json",
        "published/tdd-results.json",
        "published/tdd-handoff.json",
        "git-run.json",
        "ci-status.json",
        "ci-signals.json",
    )
    selected: dict[str, object] = {key: _clip_artifact(value) for key, value in source_artifacts.items()}
    remaining = _CONTEXT_LIMIT
    for artifact_id in (*preferred, *inventory):
        if artifact_id in selected or artifact_id not in inventory or _skip_selected_artifact(artifact_id):
            continue
        value = _read_artifact(context, artifact_id)
        if value is None:
            continue
        clipped = _clip_artifact(value, min(_ARTIFACT_LIMIT, remaining))
        selected[artifact_id] = clipped
        remaining -= len(json.dumps(clipped, ensure_ascii=False, sort_keys=True))
        if remaining <= 0:
            break
    return selected


def _skip_selected_artifact(artifact_id: str) -> bool:
    return artifact_id.startswith((
        "workers/",
        "validation/",
        "knowledge/",
    ))


def _read_artifact(context: PhaseExecutionContext, artifact_id: str) -> object | None:
    if artifact_id.endswith(".json"):
        return context.artifacts.read_json(context.run.run_id, artifact_id)
    return context.artifacts.read_text(context.run.run_id, artifact_id)


def _clip_artifact(value: object, limit: int = _ARTIFACT_LIMIT) -> object:
    if isinstance(value, str):
        return _clip_text(value, limit)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(encoded) <= limit:
        return value
    return {"truncated": True, "excerpt": _clip_text(encoded, limit)}


def _clip_text(value: object, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[clipped {len(text) - limit} chars]"


def _repository_snapshot(root: Path, selected_artifacts: Mapping[str, object]) -> dict[str, object]:
    root = Path(root)
    paths = _repository_paths(selected_artifacts)
    entries = []
    for relative in paths[:_REPOSITORY_ENTRY_LIMIT]:
        entry = _repository_entry(root, relative)
        if entry is not None:
            entries.append(entry)
    return {
        "repository_root": str(root),
        "git_head": _git_head(root, selected_artifacts),
        "entries": entries,
    }


def _repository_paths(value: object) -> list[str]:
    found: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if key in {"path", "file"} and isinstance(child, str):
                    found.append(child)
                else:
                    visit(child)
        elif isinstance(item, list | tuple):
            for child in item:
                visit(child)

    visit(value)
    unique = []
    seen = set()
    for path in found:
        normalized = path.strip().replace("\\", "/")
        if not normalized or normalized.startswith("/") or ".." in Path(normalized).parts:
            continue
        if normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique


def _repository_entry(root: Path, relative: str) -> dict[str, object] | None:
    path = root / relative
    try:
        if not path.is_file():
            return None
        content = path.read_text(encoding="utf-8", errors="ignore")[:_REPOSITORY_FILE_LIMIT]
    except OSError:
        return None
    snippets = []
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        snippets.append({"line_start": line_number, "line_end": line_number, "excerpt": line[:220]})
        if len(snippets) >= 4:
            break
    return {"path": relative, "bytes_read": len(content), "snippets": snippets}


def _git_head(root: Path, selected_artifacts: Mapping[str, object]) -> str | None:
    git_run = selected_artifacts.get("git-run.json")
    if isinstance(git_run, Mapping):
        for key in ("head", "git_head", "revision", "sha"):
            value = git_run.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _task_to_mapping(task: object) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "title": task.title,
        "status": task.status.value,
        "attempts": task.attempts,
        "last_failure": task.last_failure,
    }


def _decision_to_mapping(decision: object) -> dict[str, object]:
    return {
        "decision_id": decision.decision_id,
        "origin_bundle": decision.origin_bundle.value,
        "prompt": decision.prompt,
        "response": decision.response,
        "created_at": decision.created_at,
        "answered_at": decision.answered_at,
        "options": list(decision.options),
    }


def _error_to_mapping(error: object) -> dict[str, object]:
    return {
        "code": error.code,
        "message": error.message,
        "bundle": error.bundle,
        "phase": error.phase,
        "timestamp": error.timestamp,
    }
