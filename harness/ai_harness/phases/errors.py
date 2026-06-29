"""Phase contract exceptions."""

from __future__ import annotations


class PhaseValidationError(ValueError):
    """Raised when phase input or candidate output violates its contract."""


class PhaseRepairExhaustedError(PhaseValidationError):
    """Raised when the bounded repair attempt also violates the phase contract."""
