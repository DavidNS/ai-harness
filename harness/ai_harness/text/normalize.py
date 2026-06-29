"""Text normalisation helpers.

Pure functions — no side effects, no imports from the harness domain.
Previously staticmethods on AnalysisQualityMixin.
"""
from __future__ import annotations

import re


def normalize_key(value: str) -> str:
    """Lowercase and strip all non-alphanumeric characters for fuzzy key matching."""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def normalized_statement(text: str) -> str:
    """Return a lowercase token sequence for equality comparison of statements."""
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))
