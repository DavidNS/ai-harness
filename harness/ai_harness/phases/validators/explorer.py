"""Explorer phase validators."""

from __future__ import annotations

import re

from ..errors import PhaseValidationError
from ..markdown import markdown_section, markdown_section_text, markdown_validator


def _resolved_open_questions(candidate: str) -> bool:
    text = markdown_section_text(candidate, "Open Questions")
    lines = []
    for raw in text.splitlines():
        line = raw.strip().strip("-*+ ").strip()
        if line:
            lines.append(line.rstrip(".").casefold())
    if not lines:
        return True
    resolved = {
        "none",
        "n/a",
        "not applicable",
        "no open questions",
        "no unresolved questions",
        "no unresolved factual questions",
        "no repository-answerable questions remain",
    }
    return all(line in resolved for line in lines)


def _validate_resolved_open_questions(candidate: str) -> None:
    if not _resolved_open_questions(candidate):
        raise PhaseValidationError("explorer output must not contain unresolved factual open questions")


def validate_compact_improvement(candidate: str) -> str:
    if not isinstance(candidate, str) or not candidate.strip():
        raise PhaseValidationError("phase output must be nonempty Markdown")
    lines = candidate.replace("\r\n", "\n").splitlines()
    first_line = lines[0].strip() if lines else ""
    if not first_line.startswith("# Improvement:") or not first_line.removeprefix("# Improvement:").strip():
        raise PhaseValidationError("compact improvement output must begin with '# Improvement: <title>'")
    sections = ("Status", "Problem", "Evidence", "Desired Behavior", "Implementation Notes", "Acceptance Criteria")
    positions: list[int] = []
    for section in sections:
        marker = f"## {section}"
        matches = [index for index, line in enumerate(lines) if line.strip() == marker]
        if len(matches) != 1:
            raise PhaseValidationError(f"required section must appear once: {section}")
        positions.append(matches[0])
    if positions != sorted(positions):
        raise PhaseValidationError("required sections are out of order")
    if any(line.strip() == "## Open Questions" for line in lines):
        raise PhaseValidationError("compact explorer improvements must not contain Open Questions")
    for index, section in zip(positions, sections):
        end = next((position for position in positions if position > index), len(lines))
        if not any(line.strip() for line in lines[index + 1 : end]):
            raise PhaseValidationError(f"required section is empty: {section}")
    return candidate


def validate_explorer_distill(candidate: str) -> str:
    validated = validate_compact_improvement(candidate)
    text = validated.casefold()
    forbidden = (
        "selected direction",
        "decision behavioral delta",
        "discovery selected",
        "rejected alternatives",
        "counterevidence and falsifying conditions",
        "counterevidence and risks",
        "value hypothesis",
        "behavioral delta",
    )
    for phrase in forbidden:
        if phrase in text:
            raise PhaseValidationError(f"distilled improvement contains process residue: {phrase}")
    if re.search(r"\bC\d+\b", validated):
        raise PhaseValidationError("distilled improvement must not contain internal claim IDs")
    if re.search(r"^\s*-\s*\[[ xX]\]", validated, re.MULTILINE):
        raise PhaseValidationError("distilled improvement must not use checkbox syntax")
    criteria = markdown_section(validated, "Acceptance Criteria")
    if re.search(r"\b\d+[.)]\s+", criteria):
        raise PhaseValidationError("distilled acceptance criteria must not contain embedded numbered procedures")
    return validated


def validate_explorer(candidate: str) -> str:
    improvement = markdown_validator(
        "Improvement Analysis",
        ("Problem", "Context", "Findings", "Options", "Risks", "Recommendation", "Outcome", "Open Questions"),
    )
    limitation = markdown_validator(
        "Limitation",
        ("Problem", "Context", "Reasoning", "Outcome", "Next Step"),
    )
    existing = markdown_validator(
        "Existing Functionality",
        ("Problem", "Evidence", "Outcome", "Open Questions"),
    )
    first_line = candidate.replace("\r\n", "\n").splitlines()[0].strip() if candidate else ""
    if first_line.startswith("# Improvement:"):
        return validate_compact_improvement(candidate)
    if first_line == "# Improvement Analysis v1":
        validated = improvement(candidate)
        _validate_resolved_open_questions(validated)
        return validated
    if first_line == "# Limitation v1":
        return limitation(candidate)
    if first_line == "# Existing Functionality v1":
        validated = existing(candidate)
        _validate_resolved_open_questions(validated)
        return validated
    raise PhaseValidationError(
        "explorer output must be concise Improvement, legacy Improvement Analysis, Limitation, or Existing Functionality Markdown"
    )
