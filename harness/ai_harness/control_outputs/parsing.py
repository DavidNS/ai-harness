"""Parsing helpers for control outputs."""

from __future__ import annotations

import json
from typing import Sequence

from ..errors import ValidationError
from .models import (
    ControlOutput,
    DecisionAnswer,
    DecisionRequest,
    ImpossibleOutcome,
    ExplorerBundle,
    PhaseEscalation,
)
from .validators import _text


def parse_control_output(
    candidate: str,
    *,
    expected_origin: str,
    active_graph_phase: str,
    graph: Sequence[str],
) -> ControlOutput | None:
    """Return a typed control output, or None when candidate is a normal artifact."""

    try:
        value = json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or "kind" not in value:
        return None
    kind = value["kind"]
    if kind == "decision_request":
        return DecisionRequest.from_mapping(value, expected_origin=expected_origin)
    if kind == "phase_escalation":
        return PhaseEscalation.from_mapping(
            value,
            expected_origin=expected_origin,
            active_graph_phase=active_graph_phase,
            graph=graph,
        )
    if kind == "impossible":
        return ImpossibleOutcome.from_mapping(value, expected_origin=expected_origin)
    if kind == "explorer_bundle":
        return ExplorerBundle.from_mapping(value, expected_origin=expected_origin)
    raise ValidationError(f"unknown control output kind: {kind}")


def parse_decision_answer(raw: str, *, pending_decision_id: str) -> DecisionAnswer:
    text = raw.strip()
    if not text:
        raise ValidationError("decision answer must not be empty")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return DecisionAnswer(pending_decision_id, text)
    if not isinstance(value, dict):
        return DecisionAnswer(pending_decision_id, text)
    if value.get("kind", "decision_answer") != "decision_answer":
        raise ValidationError("answer JSON kind must be decision_answer")
    if value.get("schema_version", 1) != 1:
        raise ValidationError("answer schema_version is unsupported")
    decision_id = str(value.get("decision_id", ""))
    if decision_id != pending_decision_id:
        raise ValidationError("answer decision_id does not match the pending decision")
    selected = value.get("selected_option")
    if selected is not None and not isinstance(selected, str):
        raise ValidationError("selected_option must be a string")
    return DecisionAnswer(decision_id, _text(value.get("answer"), "answer"), selected)
