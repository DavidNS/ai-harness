"""Private validation helpers for control output parsing."""

from __future__ import annotations

from typing import Mapping

from ..errors import ValidationError


def _require_kind(value: Mapping[str, object], expected: str) -> None:
    if value.get("schema_version") != 1 or value.get("kind") != expected:
        raise ValidationError(f"{expected} control output has invalid schema or kind")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be a JSON object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a nonempty string")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a nonempty string when supplied")
    return value


def _optional_positive_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError(f"{field} must be a positive integer when supplied")
    return value


def _repository_evidence_sequence(value: object, field: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be a list")
    normalized: list[dict[str, object]] = []
    for item in value:
        raw = _mapping(item, field)
        path = _text(raw.get("path"), f"{field}.path")
        kind = _text(raw.get("kind"), f"{field}.kind")
        if kind not in {"code", "test", "documentation", "decision"}:
            raise ValidationError(f"{field}.kind is invalid")
        entry: dict[str, object] = {"path": path, "kind": kind}
        for key in ("symbol", "excerpt", "confidence"):
            value = raw.get(key)
            if value is not None:
                entry[key] = _text(value, f"{field}.{key}")
        for key in ("line_start", "line_end"):
            value = _optional_positive_int(raw.get(key), f"{field}.{key}")
            if value is not None:
                entry[key] = value
        if "line_start" in entry and "line_end" in entry and entry["line_end"] < entry["line_start"]:
            raise ValidationError(f"{field}.line_end must be greater than or equal to line_start")
        normalized.append(entry)
    return tuple(normalized)


def _phase(value: object, field: str) -> str:
    text = _text(value, field).upper()
    if not text.replace("_", "").isalnum():
        raise ValidationError(f"{field} must be a phase name")
    return text


def _text_sequence(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{field} must be a nonempty list of strings")
    return _optional_text_sequence(value, field)


def _optional_text_sequence(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be a list of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError(f"{field} contains an invalid value")
    return tuple(value)


def _optional_score_mapping(value: object, field: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be a JSON object")
    scores: dict[str, int] = {}
    for key, score in value.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(score, int) or score < 0:
            raise ValidationError(f"{field} contains an invalid score")
        scores[key] = score
    return scores


def _optional_text_mapping(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be a JSON object")
    details: dict[str, str] = {}
    for key, detail in value.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(detail, str) or not detail.strip():
            raise ValidationError(f"{field} contains an invalid detail")
        details[key] = detail
    return details


def _optional_signal_mapping(value: object, field: str) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be a JSON object")
    signals: dict[str, tuple[str, ...]] = {}
    for key, raw_items in value.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(raw_items, list):
            raise ValidationError(f"{field} contains an invalid signal list")
        if any(not isinstance(item, str) or not item.strip() for item in raw_items):
            raise ValidationError(f"{field} contains an invalid signal")
        signals[key] = tuple(raw_items)
    return signals
