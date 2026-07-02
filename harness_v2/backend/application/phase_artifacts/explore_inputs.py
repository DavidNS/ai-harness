"""Explore phase input and decision mappers."""

from __future__ import annotations

from harness_v2.backend.application.phase_artifacts.explore_utils import _string_items
from harness_v2.backend.domain.lifecycle import BundleName
from harness_v2.backend.domain.runs import RunRecord

EXPLORE_BUNDLE = BundleName.EXPLORE_BUNDLE


def needs_clarification(profile: dict[str, object]) -> bool:
    return bool(_string_items(profile.get("clarification_questions")))


def clarification_questions(profile: dict[str, object]) -> tuple[str, ...]:
    return tuple(_string_items(profile.get("clarification_questions")))


def has_explore_decision(run: RunRecord) -> bool:
    return any(decision.origin_bundle is EXPLORE_BUNDLE for decision in run.decision_history)


def decision_history(run: RunRecord) -> list[dict[str, str]]:
    return [{"decision_id": decision.decision_id, "origin_bundle": decision.origin_bundle.value, "prompt": decision.prompt, "response": decision.response, "created_at": decision.created_at, "answered_at": decision.answered_at} for decision in run.decision_history]
