"""Side-effect-free hybrid intent router."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .providers.base import Provider
from .providers.json_extract import run_json_prompt
from .route_heuristics import score_route

_CODE_INTENTS = frozenset({"build_software", "modify_code", "debug_issue", "explorer_request"})
_NON_CODE_INTENTS = frozenset({"ideation", "market_analysis", "research", "unknown"})


_BUG_EXPLORER_PATTERN = re.compile(
    r"\b(?:bug|debug|traceback|exception|failure|failing|error|regression|broken|crash)\b"
)
_IMPROVEMENT_EXPLORER_PATTERN = re.compile(
    r"draft-improvements/[\w./-]+\.md"
    r"|\b(?:investigat(?:e|ion)|analy[sz](?:e|is)|triage|research)\b.{0,80}\bimprovement(?:s)?\b"
    r"|\bimprovement(?:s)?\b.{0,80}\b(?:investigat(?:e|ion)|analy[sz](?:e|is)|triage|research)\b"
)
_TRIVIAL_CHANGE_PATTERN = re.compile(r"\b(?:typo|misspelling|format|mechanical)\b")
_EXPLICIT_HIGH_SDD_PATTERN = re.compile(r"\b(?:full\s+sdd|full_implementation|full\s+implementation)\b")
_ANALYSIS_REFERENCE_PATTERN = re.compile(r"(?<![\w/.-])docs/explorer/improvements/(?:[\w.-]+/)*[\w.-]+(?:/improvement\.md)?(?![\w/.-])")


@dataclass(frozen=True, slots=True)
class RouteDecision:
    mode: str
    intent: str
    confidence: float
    source: str
    matched_signals: tuple[str, ...] = ()
    error: str | None = None


def validate_route(value: Mapping[str, object]) -> RouteDecision:
    if set(value) != {"mode", "intent", "confidence"}:
        raise ValueError("route object must contain exactly mode, intent, and confidence")
    mode, intent, confidence = value["mode"], value["intent"], value["confidence"]
    if mode not in {"code", "non_code"}:
        raise ValueError("invalid route mode")
    allowed = _CODE_INTENTS if mode == "code" else _NON_CODE_INTENTS
    if intent not in allowed:
        raise ValueError("intent is inconsistent with route mode")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("route confidence must be numeric")
    if not 0 <= float(confidence) <= 1:
        raise ValueError("route confidence must be between zero and one")
    return RouteDecision(str(mode), str(intent), float(confidence), "provider")


def _local_explorer_intent(request: str) -> tuple[str, tuple[str, ...]] | None:
    text = " ".join(request.casefold().split())
    if _BUG_EXPLORER_PATTERN.search(text):
        return "debug_issue", ("bug_explorer_request",)
    if _TRIVIAL_CHANGE_PATTERN.search(text):
        return None
    if _IMPROVEMENT_EXPLORER_PATTERN.search(text):
        return "explorer_request", ("explorer_request",)
    return None


def route_request(
    request: str,
    *,
    provider: Provider | None = None,
    cwd: Path | None = None,
    permissions: Mapping[str, object] | None = None,
    router_prompt: str | None = None,
) -> RouteDecision:
    text = " ".join(request.casefold().split())
    if _EXPLICIT_HIGH_SDD_PATTERN.search(text):
        signals = ["explicit_sdd_high"]
        if _ANALYSIS_REFERENCE_PATTERN.search(request):
            signals.append("explorer_scope_reference")
        return RouteDecision("code", "modify_code", 0.90, "heuristic", tuple(signals))

    explorer = _local_explorer_intent(request)
    if explorer is not None:
        intent, signals = explorer
        return RouteDecision("code", intent, 0.82, "heuristic", signals)

    scored = score_route(request)
    if scored.local_mode == "code":
        intent = "debug_issue" if "stack_trace" in scored.code_signals else "modify_code"
        return RouteDecision(
            "code", intent, min(1.0, 0.65 + scored.code_score * 0.08),
            "heuristic", scored.code_signals,
        )
    if scored.local_mode == "non_code":
        intent = "ideation" if "ideation" in scored.non_code_signals else "research"
        return RouteDecision(
            "non_code", intent, min(1.0, 0.65 + scored.non_code_score * 0.08),
            "heuristic", scored.non_code_signals,
        )
    if scored.ambiguous:
        return RouteDecision(
            "code",
            "modify_code",
            0.0,
            "needs_user",
            scored.code_signals + scored.non_code_signals,
            "ambiguous code/non-code routing requires user choice",
        )

    if provider is None or cwd is None:
        return RouteDecision(
            "non_code", "unknown", 0.0, "safe_fallback",
            scored.code_signals + scored.non_code_signals,
            "ambiguous request requires a configured provider",
        )

    prompt = router_prompt or (
        "Classify the request as code or non_code. Return only JSON with mode, "
        "intent, and confidence. Allowed code intents: build_software, modify_code, "
        "debug_issue, explorer_request. Allowed non-code intents: ideation, market_analysis, research, "
        f"unknown.\n\nRequest:\n{request}"
    )
    structured = run_json_prompt(
        provider,
        prompt,
        cwd=cwd,
        permissions=permissions,
        validator=validate_route,
    )
    if structured.succeeded:
        assert isinstance(structured.value, RouteDecision)
        return structured.value
    return RouteDecision(
        "non_code", "unknown", 0.0, "safe_fallback",
        scored.code_signals + scored.non_code_signals, structured.error,
    )
