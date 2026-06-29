"""Standalone parser for the Learning v2 markdown format.

Previously the parse_learning_sections classmethod on AnalysisQualityMixin.
Extracted so that KnowledgeLoader and other collaborators can import directly
without going through the mixin/callback chain.
"""
from __future__ import annotations

from ..phases import PhaseValidationError
from ..text.markdown import compact_lines as _compact_lines

_LEARNING_SECTIONS = ("Title", "Summary", "Decisions", "Patterns", "Errors", "Solutions", "Keywords")


def parse_learning_sections(candidate: str, *, validate: bool = True) -> dict[str, str | tuple[str, ...]]:
    lines = candidate.replace("\r\n", "\n").splitlines()
    if validate:
        if not lines or lines[0].strip() != "# Learning v2":
            raise PhaseValidationError("legacy learning output must begin with '# Learning v2'")
        positions: list[int] = []
        for section in _LEARNING_SECTIONS:
            marker = f"## {section}"
            matches = [index for index, line in enumerate(lines) if line.strip() == marker]
            if len(matches) != 1:
                raise PhaseValidationError(f"required legacy learning section must appear once: {section}")
            positions.append(matches[0])
        if positions != sorted(positions):
            raise PhaseValidationError("required legacy learning sections are out of order")
        for index, section in zip(positions, _LEARNING_SECTIONS):
            end = next((position for position in positions if position > index), len(lines))
            if not any(line.strip() for line in lines[index + 1 : end]):
                raise PhaseValidationError(f"required legacy learning section is empty: {section}")
    parsed: dict[str, str | tuple[str, ...]] = {}
    for section in _LEARNING_SECTIONS:
        marker = f"## {section}"
        try:
            start = next(index for index, line in enumerate(lines) if line.strip() == marker) + 1
        except StopIteration:
            if validate:
                raise
            continue
        end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
        text = "\n".join(line.rstrip() for line in lines[start:end]).strip()
        parsed[section.lower()] = text if section in {"Title", "Summary"} else _compact_lines(text)
    return parsed
