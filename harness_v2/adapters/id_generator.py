"""Identifier generator adapters for v2 hosts."""

from __future__ import annotations

from uuid import uuid4


class UuidIdGenerator:
    """UUID-backed identifier generator for application services."""

    def new_id(self) -> str:
        return uuid4().hex
