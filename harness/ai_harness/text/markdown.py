"""Markdown parsing helpers.

Pure functions — no side effects, no imports from the harness domain.
Previously scattered as staticmethods on WorkerExchange and
AnalysisQualityMixin; extracted here so they can be shared and tested
independently.
"""
from __future__ import annotations

import re


def markdown_section(candidate: str, section: str) -> str:
    """Return the body of a ## Section heading, or '' if absent."""
    lines = candidate.replace("\r\n", "\n").splitlines()
    marker = f"## {section}"
    try:
        start = lines.index(marker) + 1
    except ValueError:
        return ""
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end]).strip()


def strip_code_block(value: str) -> str:
    """Strip a fenced code block wrapper, returning the inner content."""
    raw = value.strip()
    if raw.startswith("```") and raw.endswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return raw


def compact_lines(text: str) -> tuple[str, ...]:
    """Return non-empty lines with list markers (-, *, +, 1.) stripped."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        while line.startswith(("-", "*", "+")):
            line = line[1:].strip()
        match = re.match(r"^\d+[.)]\s+(.*)$", line)
        if match:
            line = match.group(1).strip()
        if line:
            lines.append(line)
    return tuple(lines)


def section_sentences(section: str) -> list[str]:
    """Split a markdown section into individual sentences / bullet items."""
    chunks: list[str] = []
    for raw in section.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("- ", "* ")):
            chunks.append(line)
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        chunks.extend(part.strip() for part in parts if part.strip())
    return chunks
