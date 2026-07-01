"""Identifier generation port for backend-created records."""

from __future__ import annotations

from typing import Protocol


class IdGeneratorPort(Protocol):
    """Identifier source boundary for application services."""

    def new_id(self) -> str: ...
