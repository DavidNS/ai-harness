"""Shared bundle handoff artifact builders and validators."""

from __future__ import annotations

from typing import Any

from harness_v2.backend.application.json_schema import validate_json_schema


def validate_handoff(value: dict[str, Any]) -> None:
    validate_json_schema(value, "handoff")


def build_bundle_handoff(bundle: str, artifacts: list[str], next_bundle: str | None, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"schema_version": 1, "bundle": bundle, "artifacts": artifacts, "next_bundle": next_bundle, **(extra or {})}
