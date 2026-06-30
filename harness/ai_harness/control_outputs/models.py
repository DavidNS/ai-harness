"""Typed control output models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..contracts.enums import ArtifactKind, BundleAction
from ..errors import ValidationError
from ..models import utc_now
from .validators import (
    _mapping,
    _optional_positive_int,
    _optional_score_mapping,
    _optional_signal_mapping,
    _optional_text,
    _optional_text_mapping,
    _optional_text_sequence,
    _phase,
    _repository_evidence_sequence,
    _require_kind,
    _text,
    _text_sequence,
)


@dataclass(frozen=True, slots=True)
class DecisionOption:
    id: str
    label: str
    consequence: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "DecisionOption":
        try:
            option = cls(str(value["id"]), str(value["label"]), str(value["consequence"]))
        except KeyError as exc:
            raise ValidationError("decision option is missing required fields") from exc
        if not option.id.strip() or not option.label.strip() or not option.consequence.strip():
            raise ValidationError("decision option fields must be nonempty")
        return option

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label, "consequence": self.consequence}


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    origin_phase: str
    reason: str
    question: str
    context: tuple[str, ...]
    options: tuple[DecisionOption, ...] = ()
    allows_freeform: bool = True
    decision_id: str | None = None
    scores: Mapping[str, int] = field(default_factory=dict)
    score_signals: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    ranked_paths: tuple[str, ...] = ()
    schema_version: int = 1
    kind: str = "decision_request"
    option_details: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object], *, expected_origin: str) -> "DecisionRequest":
        _require_kind(value, "decision_request")
        origin = _phase(value.get("origin_phase"), "origin_phase")
        if origin != expected_origin:
            raise ValidationError("decision request origin does not match the active worker phase")
        reason = _text(value.get("reason"), "reason")
        question = _text(value.get("question"), "question")
        if "?" not in question:
            raise ValidationError("decision request question must be a direct question")
        context = _text_sequence(value.get("context"), "context")
        raw_options = value.get("options", ())
        if raw_options is None:
            raw_options = ()
        if not isinstance(raw_options, list):
            raise ValidationError("decision request options must be a list")
        options = tuple(DecisionOption.from_mapping(_mapping(item, "decision option")) for item in raw_options)
        option_ids = [option.id for option in options]
        if len(option_ids) != len(set(option_ids)):
            raise ValidationError("decision option IDs must be unique")
        allows_freeform = value.get("allows_freeform", True)
        if not isinstance(allows_freeform, bool):
            raise ValidationError("allows_freeform must be a boolean")
        decision_id = value.get("decision_id")
        if decision_id is not None and not str(decision_id).strip():
            raise ValidationError("decision_id must be nonempty when supplied")
        scores = _optional_score_mapping(value.get("scores", {}), "scores")
        score_signals = _optional_signal_mapping(value.get("score_signals", {}), "score_signals")
        ranked_paths = _optional_text_sequence(value.get("ranked_paths", []), "ranked_paths")
        option_details = _optional_text_mapping(value.get("option_details", {}), "option_details")
        return cls(
            origin,
            reason,
            question,
            context,
            options,
            allows_freeform,
            None if decision_id is None else str(decision_id),
            scores,
            score_signals,
            ranked_paths,
            option_details=option_details,
        )

    def with_id(self, decision_id: str) -> "DecisionRequest":
        if not decision_id.strip():
            raise ValidationError("decision ID is required")
        return DecisionRequest(
            self.origin_phase,
            self.reason,
            self.question,
            self.context,
            self.options,
            self.allows_freeform,
            decision_id,
            self.scores,
            self.score_signals,
            self.ranked_paths,
            option_details=self.option_details,
        )

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "origin_phase": self.origin_phase,
            "reason": self.reason,
            "question": self.question,
            "context": list(self.context),
            "options": [option.to_dict() for option in self.options],
            "allows_freeform": self.allows_freeform,
        }
        if self.decision_id is not None:
            data["decision_id"] = self.decision_id
        if self.scores:
            data["scores"] = dict(self.scores)
        if self.score_signals:
            data["score_signals"] = {key: list(value) for key, value in self.score_signals.items()}
        if self.ranked_paths:
            data["ranked_paths"] = list(self.ranked_paths)
        if self.option_details:
            data["option_details"] = dict(self.option_details)
        return data


def _bundle_phase(value: str) -> str:
    mapping = {
        "EXPLORE": "EXPLORE_BUNDLE",
        "EXPLORER": "EXPLORE_BUNDLE",
        "EXPLORER_REVIEW": "EXPLORE_BUNDLE",
        "PURPOSE": "PROPOSAL_BUNDLE",
        "PROPOSAL": "PROPOSAL_BUNDLE",
        "SPEC": "SPEC_BUNDLE",
        "DESIGN": "DESIGN_BUNDLE",
        "TASKS": "TASKS_BUNDLE",
        "SIMPLE_TASK": "TASKS_BUNDLE",
        "TDD_LOOP": "TDD_BUNDLE",
        "IMPLEMENT": "TDD_BUNDLE",
        "IMPLEMENTING": "TDD_BUNDLE",
        "TEST": "TDD_BUNDLE",
        "REVIEW": "TDD_BUNDLE",
    }
    return mapping.get(value, value)


@dataclass(frozen=True, slots=True)
class PhaseEscalation:
    origin_phase: str
    target_phase: str
    reason: str
    schema_version: int = 1
    kind: str = "phase_escalation"

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, object],
        *,
        expected_origin: str,
        active_graph_phase: str,
        graph: Sequence[str],
    ) -> "PhaseEscalation":
        _require_kind(value, "phase_escalation")
        origin = _phase(value.get("origin_phase"), "origin_phase")
        if origin != expected_origin:
            raise ValidationError("phase escalation origin does not match the active worker phase")
        target = _bundle_phase(_phase(value.get("target_phase"), "target_phase"))
        active_graph_phase = _bundle_phase(active_graph_phase)
        reason = _text(value.get("reason"), "reason")
        if target not in graph:
            raise ValidationError("phase escalation target is not in the selected graph")
        if active_graph_phase not in graph:
            raise ValidationError("active graph phase is not in the selected graph")
        if graph.index(target) >= graph.index(active_graph_phase):
            raise ValidationError("phase escalation target must be earlier than the active graph phase")
        return cls(origin, target, reason)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "origin_phase": self.origin_phase,
            "target_phase": self.target_phase,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ImpossibleOutcome:
    origin_phase: str
    reason: str
    evidence: tuple[str, ...]
    remaining_options: tuple[str, ...] = ()
    schema_version: int = 1
    kind: str = "impossible"

    @classmethod
    def from_mapping(cls, value: Mapping[str, object], *, expected_origin: str) -> "ImpossibleOutcome":
        _require_kind(value, "impossible")
        origin = _phase(value.get("origin_phase"), "origin_phase")
        if origin != expected_origin:
            raise ValidationError("impossible origin does not match the active worker phase")
        reason = _text(value.get("reason"), "reason")
        evidence = _text_sequence(value.get("evidence"), "evidence")
        remaining = value.get("remaining_options", ())
        if remaining is None:
            remaining = ()
        remaining_options = _optional_text_sequence(remaining, "remaining_options")
        return cls(origin, reason, evidence, remaining_options)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "origin_phase": self.origin_phase,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "remaining_options": list(self.remaining_options),
        }


EXPLORER_BUNDLE_ACTIONS = frozenset(BundleAction)
EXPLORER_ARTIFACT_KINDS = frozenset(ArtifactKind)


@dataclass(frozen=True, slots=True)
class ExplorerBundleEntry:
    entry_id: str
    action: str
    title: str
    artifact_kind: str | None = None
    content: str | None = None
    path: str | None = None
    expected_checksum: str | None = None
    reason: str | None = None
    repository_evidence: tuple[dict[str, object], ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ExplorerBundleEntry":
        entry_id = _text(value.get("id"), "bundle entry id")
        raw_action = _text(value.get("action"), "bundle entry action")
        action = "no-op" if raw_action in {"no-op", "no_op"} else raw_action.replace("-", "_")
        if action not in EXPLORER_BUNDLE_ACTIONS:
            raise ValidationError("bundle entry action is invalid")
        title = _text(value.get("title"), "bundle entry title")
        artifact_kind = _optional_text(value.get("artifact_kind"), "artifact_kind")
        if artifact_kind is not None:
            artifact_kind = artifact_kind.replace("_", "-")
            if artifact_kind not in EXPLORER_ARTIFACT_KINDS:
                raise ValidationError("bundle entry artifact_kind is invalid")
        content = _optional_text(value.get("content"), "content")
        path = _optional_text(value.get("path"), "path")
        expected_checksum = _optional_text(value.get("expected_checksum"), "expected_checksum")
        reason = _optional_text(value.get("reason"), "reason")
        repository_evidence = _repository_evidence_sequence(value.get("repository_evidence", []), "repository_evidence")
        if action == "update" and (path is None or expected_checksum is None or content is None):
            raise ValidationError("update bundle entries require path, expected_checksum, and content")
        if action in {"create", "documentation_task", "limitation", "existing_functionality"} and content is None:
            raise ValidationError(f"{action} bundle entries require content")
        if action == "no-op" and reason is None:
            raise ValidationError("no-op bundle entries require reason")
        return cls(entry_id, action, title, artifact_kind, content, path, expected_checksum, reason, repository_evidence)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.entry_id,
            "action": self.action,
            "title": self.title,
        }
        if self.artifact_kind is not None:
            data["artifact_kind"] = self.artifact_kind
        if self.content is not None:
            data["content"] = self.content
        if self.path is not None:
            data["path"] = self.path
        if self.expected_checksum is not None:
            data["expected_checksum"] = self.expected_checksum
        if self.reason is not None:
            data["reason"] = self.reason
        if self.repository_evidence:
            data["repository_evidence"] = [dict(item) for item in self.repository_evidence]
        return data


@dataclass(frozen=True, slots=True)
class ExplorerBundle:
    origin_phase: str
    entries: tuple[ExplorerBundleEntry, ...]
    primary_entry: str | None = None
    schema_version: int = 1
    kind: str = "explorer_bundle"

    @classmethod
    def from_mapping(cls, value: Mapping[str, object], *, expected_origin: str) -> "ExplorerBundle":
        _require_kind(value, "explorer_bundle")
        origin = _phase(value.get("origin_phase"), "origin_phase")
        if origin != expected_origin:
            raise ValidationError("explorer bundle origin does not match the active worker phase")
        if not origin.startswith("EXPLORER"):
            raise ValidationError("explorer_bundle is only valid for explorer phases")
        raw_entries = value.get("entries")
        if not isinstance(raw_entries, list) or not raw_entries:
            raise ValidationError("explorer bundle entries must be a nonempty list")
        entries = tuple(ExplorerBundleEntry.from_mapping(_mapping(item, "bundle entry")) for item in raw_entries)
        entry_ids = [entry.entry_id for entry in entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValidationError("bundle entry IDs must be unique")
        primary = _optional_text(value.get("primary_entry"), "primary_entry")
        if primary is not None and primary not in entry_ids:
            raise ValidationError("primary_entry must reference a bundle entry id")
        return cls(origin, entries, primary)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "origin_phase": self.origin_phase,
            "entries": [entry.to_dict() for entry in self.entries],
        }
        if self.primary_entry is not None:
            data["primary_entry"] = self.primary_entry
        return data


@dataclass(frozen=True, slots=True)
class DecisionAnswer:
    decision_id: str
    answer: str
    selected_option: str | None = None
    answered_at: str = field(default_factory=utc_now)
    schema_version: int = 1
    kind: str = "decision_answer"

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.answer.strip():
            raise ValidationError("decision answer requires decision_id and answer")
        if self.selected_option is not None and not self.selected_option.strip():
            raise ValidationError("selected_option must be nonempty when supplied")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "decision_id": self.decision_id,
            "answered_at": self.answered_at,
            "answer": self.answer,
            "selected_option": self.selected_option,
        }


ControlOutput = DecisionRequest | PhaseEscalation | ImpossibleOutcome | ExplorerBundle


class ControlFlowSignal(Exception):
    """Raised internally so TDD retries do not convert control outputs to failures."""

    def __init__(self, output: ControlOutput) -> None:
        super().__init__(output.kind)
        self.output = output
