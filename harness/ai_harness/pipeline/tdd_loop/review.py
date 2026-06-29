"""Review output interpretation for the TDD loop."""

from __future__ import annotations

from ...models import ReviewVerdict
from ...phases import get_phase


def _review_result(candidate: str) -> tuple[ReviewVerdict, str]:
    validated = get_phase("review").validate(candidate)
    lines = validated.replace("\r\n", "\n").splitlines()

    def section_text(section: str) -> str:
        marker = f"## {section}"
        start = next(index for index, line in enumerate(lines) if line.strip() == marker) + 1
        end = next((index for index in range(start, len(lines))
                    if lines[index].strip().startswith("## ")), len(lines))
        return " ".join(line.strip() for line in lines[start:end] if line.strip())

    return ReviewVerdict(section_text("Verdict")), section_text("Findings")
