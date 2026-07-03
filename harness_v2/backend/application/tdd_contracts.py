"""Shared contracts for v2 TDD execution."""

from __future__ import annotations

import json
from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.json_schema import validate_json_schema
from harness_v2.backend.domain.escalation import EscalationCategory


def parse_tdd_review(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BundleValidationError("TDD review must be JSON") from exc
    validate_json_schema(payload, "tdd_review")
    escalation_category = None
    if payload.get("escalation_category") is not None:
        escalation_category = _review_escalation_category(str(payload["escalation_category"])).value
    if payload["verdict"] == "APPROVE" and escalation_category is not None:
        raise BundleValidationError("approved TDD review must not include escalation category")
    return {
        "verdict": payload["verdict"],
        "findings": _text_tuple(payload["findings"], "findings"),
        "acceptance_criteria": _text_tuple(payload["acceptance_criteria"], "acceptance_criteria"),
        "test_evidence": dict(payload["test_evidence"]),
        "escalation_category": escalation_category,
    }


def _review_escalation_category(value: str) -> EscalationCategory:
    try:
        category = EscalationCategory(value)
    except ValueError as exc:
        raise BundleValidationError("TDD review escalation category is unknown") from exc
    allowed = {
        EscalationCategory.DESIGN_GAP,
        EscalationCategory.TASK_PLAN_GAP,
        EscalationCategory.IMPLEMENTATION_BLOCKED,
        EscalationCategory.VALIDATION_BLOCKED,
    }
    if category not in allowed:
        raise BundleValidationError("TDD review escalation category is not valid for TDD")
    return category


def _text_tuple(value: list[str], _field: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value)
