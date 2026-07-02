"""Explore phase artifact contracts and validators."""

from __future__ import annotations

from typing import Any

from harness_v2.backend.application.json_schema import validate_json_schema
from harness_v2.backend.application.phase_artifacts import explore_reference_validation
from harness_v2.backend.domain.lifecycle import BundleName

EXPLORE_BUNDLE = BundleName.EXPLORE_BUNDLE
REQUEST_PROFILE_TASK = "explore_request_profile"
EVIDENCE_DIGEST_TASK = "explore_evidence_digest"
OUTCOME_SYNTHESIS_TASK = "explore_outcome_synthesis"
REQUEST_PROFILE_ARTIFACT = "explore/request_profile.json"
CONTEXT_PACK_ARTIFACT = "explore/context_pack.json"
EVIDENCE_DIGEST_ARTIFACT = "explore/evidence_digest.json"
EXPLORATION_MAP_ARTIFACT = "explore/exploration_map.json"
OUTCOME_SYNTHESIS_ARTIFACT = "explore/outcome_synthesis.json"
OUTCOME_BUNDLE_ARTIFACT = "explore/outcome_bundle.json"
HANDOFF_ARTIFACT = "published/explore-handoff.json"
CLARIFICATION_DECISION_ID = "EXPLORE_BUNDLE-clarification"


def validate_request_profile(value: dict[str, Any]) -> None:
    validate_json_schema(value, "request_profile")


def validate_context_pack(value: dict[str, Any]) -> None:
    validate_json_schema(value, "context_pack")


def validate_evidence_digest(value: dict[str, Any]) -> None:
    validate_json_schema(value, "evidence_digest")
    explore_reference_validation.validate_unique_evidence_ids(value)


def validate_exploration_map(value: dict[str, Any], evidence_ids: set[str]) -> None:
    validate_json_schema(value, "exploration_map")
    explore_reference_validation.validate_exploration_map_refs(value, evidence_ids)


def validate_outcome_synthesis(value: dict[str, Any]) -> None:
    validate_json_schema(value, "outcome_synthesis")


def validate_outcome_bundle(value: dict[str, Any]) -> None:
    validate_json_schema(value, "outcome_bundle")
    explore_reference_validation.validate_unique_evidence_ids(value)
    ids = evidence_ids(value)
    validate_exploration_map(value["exploration_map"], ids)
    explore_reference_validation.validate_entry_refs(value, ids)


def validate_handoff(value: dict[str, Any]) -> None:
    validate_json_schema(value, "explore_handoff")


def evidence_ids(value: dict[str, Any]) -> set[str]:
    return explore_reference_validation.evidence_ids(value)
