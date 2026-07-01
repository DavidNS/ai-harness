"""Clock adapters for v2 hosts."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """UTC wall-clock implementation for application services."""

    def now_iso(self) -> str:
        return datetime.now(UTC).isoformat()
