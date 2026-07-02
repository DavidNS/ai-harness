"""Cross-artifact reference validation for Explore artifacts."""

from __future__ import annotations

from typing import Any

from harness_v2.backend.application.phase_artifacts.explore_utils import (
    _artifact_strings,
    _evidence_ids,
    _validate_refs,
    _validate_unique_evidence_ids,
)


def evidence_ids(value: dict[str, Any]) -> set[str]:
    return _evidence_ids(value)


def validate_unique_evidence_ids(value: dict[str, Any]) -> None:
    _validate_unique_evidence_ids(value["evidence"], "evidence")


def validate_exploration_map_refs(value: dict[str, Any], ids: set[str]) -> None:
    for surface in value["surfaces"]:
        _validate_refs(_artifact_strings(surface["evidence_refs"]), ids)
    for behavior in value["behaviors"]:
        _validate_refs(_artifact_strings(behavior["evidence_refs"]), ids)
    for item in value["constraints"]:
        _validate_refs(_artifact_strings(item["evidence_refs"]), ids)
    for item in value["risks"]:
        _validate_refs(_artifact_strings(item["evidence_refs"]), ids)
    for item in value["unknowns"]:
        _validate_refs(_artifact_strings(item["evidence_refs"]), ids)
    for item in value["candidate_work_shapes"]:
        _validate_refs(_artifact_strings(item["supporting_evidence_refs"]), ids)
        _validate_refs(_artifact_strings(item["counterevidence_refs"]), ids)
    for item in value["verification_surfaces"]:
        _validate_refs(_artifact_strings(item["evidence_refs"]), ids)


def validate_entry_refs(value: dict[str, Any], ids: set[str]) -> None:
    for entry in value["entries"]:
        _validate_refs(_artifact_strings(entry["evidence_refs"]), ids)
