"""Shared Markdown validators for phase outputs."""

from __future__ import annotations

from .errors import PhaseValidationError
from .types import Validator


def markdown_validator(title: str, sections: tuple[str, ...]) -> Validator:
    heading = f"# {title} v1"

    def validate(candidate: str) -> str:
        if not isinstance(candidate, str) or not candidate.strip():
            raise PhaseValidationError("phase output must be nonempty Markdown")
        lines = candidate.replace("\r\n", "\n").splitlines()
        if not lines or lines[0].strip() != heading:
            raise PhaseValidationError(f"phase output must begin with {heading!r}")
        positions: list[int] = []
        for section in sections:
            marker = f"## {section}"
            matches = [index for index, line in enumerate(lines) if line.strip() == marker]
            if len(matches) != 1:
                raise PhaseValidationError(f"required section must appear once: {section}")
            positions.append(matches[0])
        if positions != sorted(positions):
            raise PhaseValidationError("required sections are out of order")
        for index, section in zip(positions, sections):
            end = next((position for position in positions if position > index), len(lines))
            if not any(line.strip() for line in lines[index + 1 : end]):
                raise PhaseValidationError(f"required section is empty: {section}")
        return candidate

    return validate


def markdown_section(candidate: str, section: str) -> str:
    lines = candidate.replace("\r\n", "\n").splitlines()
    marker = f"## {section}"
    try:
        start = lines.index(marker) + 1
    except ValueError:
        return ""
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip()


def markdown_section_text(candidate: str, section: str) -> str:
    lines = candidate.replace("\r\n", "\n").splitlines()
    marker = f"## {section}"
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == marker) + 1
    except StopIteration:
        return ""
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip()
