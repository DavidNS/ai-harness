"""Clock port for backend-owned timestamps."""

from __future__ import annotations

from typing import Protocol


class ClockPort(Protocol):
    """Time source boundary for application services."""

    def now_iso(self) -> str: ...
