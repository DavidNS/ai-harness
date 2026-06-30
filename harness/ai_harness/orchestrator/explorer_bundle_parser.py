"""ExplorerBundleParser — convert explorer worker output to an ExplorerBundle.

Handles two formats: the modern JSON bundle and the legacy v1 markdown format
legacy # Improvement Analysis v1. Previously _bundle_from_explorer_output and
_compact_improvement_from_legacy on ExplorerFlowMixin.
"""
from __future__ import annotations

import json

from ..canonical import slugify
from ..contracts.enums import PhaseName
from ..control_outputs import ExplorerBundle, ExplorerBundleEntry
from ..stores.state import StateStore
from ..text.markdown import markdown_section as _markdown_section
from .classification import explorer_kind as _explorer_kind


class ExplorerBundleParser:
    """Parse explorer worker output into a typed ExplorerBundle."""

    def __init__(self, state: StateStore) -> None:
        self._state = state

    def parse(self, output: str) -> ExplorerBundle:
        try:
            value = json.loads(output)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict) and value.get("kind") == "explorer_bundle":
            return ExplorerBundle.from_mapping(value, expected_origin=str(value.get("origin_phase", "")))
        first_line = output.replace("\r\n", "\n").splitlines()[0].strip() if output else ""
        kind = _explorer_kind(output)
        content = self._compact_from_legacy(output) if first_line == "# Improvement Analysis v1" else output
        if kind == "existing-functionality":
            action = "existing_functionality"
            artifact_kind = "existing-functionality"
        elif kind in {"limitation", "bullshit"}:
            action = "limitation"
            artifact_kind = kind
        else:
            action = "create"
            artifact_kind = "improvement"
        entry_id = "legacy" if first_line == "# Improvement Analysis v1" else "single"
        entry = ExplorerBundleEntry(
            entry_id,
            action,
            _markdown_section(output, "Problem") or self._state.load().user_input,
            artifact_kind,
            content,
        )
        return ExplorerBundle(PhaseName.EXPLORE_BUNDLE, (entry,), entry_id)

    def _compact_from_legacy(self, output: str) -> str:
        problem = _markdown_section(output, "Problem") or self._state.load().user_input
        context = _markdown_section(output, "Context")
        findings = _markdown_section(output, "Findings")
        options = _markdown_section(output, "Options")
        recommendation = _markdown_section(output, "Recommendation")
        evidence = "\n\n".join(part for part in (context, findings) if part).strip() or "Explorer found this improvement is viable."
        notes = options or "Use the future implementation flow to design and test the behavior."
        desired = recommendation or "Implement the behavior described by this improvement."
        title = slugify(problem, fallback="improvement").replace("-", " ").title()
        return (
            f"# Improvement: {title}\n"
            "## Status\n"
            "Proposed\n"
            "## Problem\n"
            f"{problem.strip()}\n"
            "## Evidence\n"
            f"{evidence.strip()}\n"
            "## Desired Behavior\n"
            f"{desired.strip()}\n"
            "## Implementation Notes\n"
            f"{notes.strip()}\n"
            "## Acceptance Criteria\n"
            "- The described behavior is implemented in the repository.\n"
            "- Focused tests cover the implemented behavior.\n"
        )
