"""Pure local request scoring for the code/non-code router."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CODE_SIGNALS: dict[str, str] = {
    "source_file": r"\b[\w.-]+\.(?:py|js|ts|tsx|jsx|go|rs|java|rb|php|cs|cpp|c|h)\b",
    "repository": r"\b(?:repo(?:sitory)?|codebase|source code|module|package)\b",
    "implementation": r"\b(?:implement|build|code|refactor|debug|fix|patch)\b",
    "tests": r"\b(?:test|tests|pytest|unittest|jest|spec)\b",
    "api_database": r"\b(?:api|endpoint|database|schema|sql|migration)\b",
    "stack_trace": r"\b(?:stack trace|traceback|exception|segfault|compile error)\b",
    "language_framework": r"\b(?:python|javascript|typescript|react|django|flask|node|rust|golang|java)\b",
}

_NON_CODE_SIGNALS: dict[str, str] = {
    "ideation": r"\b(?:brainstorm|ideate|ideas?|concepts?)\b",
    "market_analysis": r"\b(?:market analysis|competitor|positioning|customer segment)\b",
    "general_research": r"\b(?:research|summarize|explain|compare|investigate)\b",
    "writing": r"\b(?:write|rewrite|edit)\s+(?:an?\s+)?(?:article|essay|email|story|poem|post|copy)\b",
}


@dataclass(frozen=True, slots=True)
class RouteHeuristics:
    code_score: int
    non_code_score: int
    code_signals: tuple[str, ...]
    non_code_signals: tuple[str, ...]

    @property
    def ambiguous(self) -> bool:
        total = self.code_score + self.non_code_score
        return total == 0 or (
            self.code_score > 0
            and self.non_code_score > 0
            and abs(self.code_score - self.non_code_score) <= 1
        )

    @property
    def local_mode(self) -> str | None:
        if self.ambiguous:
            return None
        return "code" if self.code_score > self.non_code_score else "non_code"


def normalize_request(request: str) -> str:
    return " ".join(request.casefold().split())


def score_route(request: str) -> RouteHeuristics:
    text = normalize_request(request)
    code = tuple(name for name, pattern in _CODE_SIGNALS.items() if re.search(pattern, text))
    non_code = tuple(
        name for name, pattern in _NON_CODE_SIGNALS.items() if re.search(pattern, text)
    )
    return RouteHeuristics(len(code), len(non_code), code, non_code)
