"""Review phase validator."""

from __future__ import annotations

from ..errors import PhaseValidationError
from ..markdown import markdown_validator


def validate_review(candidate: str) -> str:
    validated = markdown_validator("Review", ("Verdict", "Findings"))(candidate)
    lines = validated.replace("\r\n", "\n").splitlines()
    verdict_index = lines.index("## Verdict")
    verdict_lines: list[str] = []
    for line in lines[verdict_index + 1 :]:
        if line.startswith("## "):
            break
        if line.strip():
            verdict_lines.append(line.strip())
    if verdict_lines not in (["APPROVE"], ["REQUEST_CHANGES"]):
        raise PhaseValidationError("review verdict must be exactly APPROVE or REQUEST_CHANGES")
    return validated
