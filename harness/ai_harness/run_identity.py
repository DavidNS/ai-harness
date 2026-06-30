"""Run identity and presentation helpers."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone


_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[a-f0-9]{12}$")


def new_run_id(now: datetime | None = None) -> str:
    """Return a sortable, filesystem-safe run id."""
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return f"{value:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"


def is_timestamped_run_id(value: str) -> bool:
    return bool(_RUN_ID_RE.fullmatch(value))


def run_id_datetime(value: str) -> datetime | None:
    if not is_timestamped_run_id(value):
        return None
    try:
        return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def display_timestamp(value: datetime | None) -> str:
    if value is None:
        return "unknown date"
    return value.astimezone().strftime("%d-%m-%Y %H:%M:%S")


def short_run_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    if is_timestamped_run_id(text):
        return text
    return text[:12]


def run_id_date(value: str) -> str:
    if is_timestamped_run_id(value):
        return value[:8]
    return "legacy"


def run_id_token(value: str) -> str:
    if is_timestamped_run_id(value):
        return value.rsplit("-", 1)[-1][:12]
    return value[:12]
