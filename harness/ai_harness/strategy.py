"""Deterministic and explainable code-pipeline strategy selection."""

from __future__ import annotations

import re
from dataclasses import dataclass


class StrategyOverrideError(ValueError):
    """Raised when a plain-text strategy override is not recognized."""


_HIGH_SIGNALS: dict[str, tuple[str, int]] = {
    "authentication": (r"\b(?:auth(?:entication|orization)?|oauth|permissions?|security)\b", 4),
    "architecture": (r"\b(?:architecture|redesign|distributed|service boundary)\b", 4),
    "migration": (r"\b(?:migration|backfill|schema change)\b", 4),
    "multiple_modules": (r"\b(?:multiple|several|across)\s+(?:modules|packages|services)\b", 3),
    "significant_uncertainty": (r"\b(?:uncertain|investigate and implement|unknown cause)\b", 3),
    "design_and_testing": (
        r"(?=.*\b(?:design|architecture)\b)(?=.*\b(?:test|tests|testing)\b)",
        4,
    ),
    "state_transition": (r"\b(?:state transitions?|state machine|phase ordering|phase graph)\b", 4),
    "persisted_artifacts": (r"\b(?:persisted artifacts?|artifact contracts?)\b", 4),
    "decision_gate": (r"\b(?:decision gates?)\b", 4),
}
_MEDIUM_SIGNALS: dict[str, tuple[str, int]] = {
    "bounded_feature": (r"\b(?:feature|endpoint|integration|workflow)\b", 2),
    "several_files": (r"\b(?:several|multiple|three|four)\s+files?\b", 2),
    "required_tests": (r"\b(?:add|write|update|run)\s+(?:the\s+)?tests?\b", 2),
    "exploration": (r"\b(?:explore|investigate|analyze)\b", 2),
    "controller_orchestration": (r"\b(?:orchestrator|controller|routing|resume|recovery|snapshot|state)\b", 2),
    "workflow_contract": (r"\b(?:schema|worker|pipeline|artifact contract|phase graph|decision gate)\b", 2),
    "cross_cutting": (r"\b(?:initiative|multi-step|cross-phase|validation)\b", 2),
    "implementation_plan": (r"\b(?:draft-improvements|initiatives)/[\w./-]+\.md\b", 2),
}
_LOW_SIGNALS: dict[str, str] = {
    "typo": r"\b(?:typo|misspelling)\b",
    "single_file": r"\b(?:single|one)\s+(?:named\s+)?file\b|\b[\w.-]+\.(?:py|js|ts|md)\b",
    "mechanical": r"\b(?:rename|format|mechanical|change a string)\b",
    "trivial_bug": r"\b(?:trivial|small|simple)\s+(?:bug|fix|change)\b",
}

_EXPLORER_PATTERN = re.compile(
    r"draft-improvements/[\w./-]+\.md"
    r"|\b(?:investigat(?:e|ion)|analy[sz](?:e|is)|triage|research)\b.{0,80}\bimprovement(?:s)?\b"
    r"|\bimprovement(?:s)?\b.{0,80}\b(?:investigat(?:e|ion)|analy[sz](?:e|is)|triage|research)\b"
)
_EXPLORER_EXCLUSIONS = re.compile(
    r"\b(?:bug|debug|traceback|exception|failure|failing|error|regression|broken|crash|typo|misspelling|format|mechanical)\b"
)


_OVERRIDE_ALIASES = {
    "simple": "SDD_LOW",
    "low": "SDD_LOW",
    "sdd low": "SDD_LOW",
    "sdd_low": "SDD_LOW",
    "s": "SDD_LOW",
    "medium": "SDD_MEDIUM",
    "sdd": "SDD_MEDIUM",
    "sdd medium": "SDD_MEDIUM",
    "sdd_medium": "SDD_MEDIUM",
    "full": "SDD_HIGH",
    "hard": "SDD_HIGH",
    "high": "SDD_HIGH",
    "full sdd": "SDD_HIGH",
    "sdd high": "SDD_HIGH",
    "sdd_high": "SDD_HIGH",
    "f": "SDD_HIGH",
    "explorer": "EXPLORER",
    "explore": "EXPLORER",
    "i": "EXPLORER",
}


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    strategy: str
    complexity: str
    score: int
    reason: str
    matched_signals: tuple[str, ...]
    recommended_strategy: str | None = None
    recommended_complexity: str | None = None
    confirmation_required: bool = False
    prompted: bool = False
    overridden: bool = False
    selection_source: str = "automatic"
    override_text: str | None = None


def _with_recommendation_defaults(decision: StrategyDecision) -> StrategyDecision:
    recommended_strategy = decision.recommended_strategy or decision.strategy
    recommended_complexity = decision.recommended_complexity or decision.complexity
    return StrategyDecision(
        decision.strategy,
        decision.complexity,
        decision.score,
        decision.reason,
        decision.matched_signals,
        recommended_strategy,
        recommended_complexity,
        decision.confirmation_required,
        decision.prompted,
        decision.overridden,
        decision.selection_source,
        decision.override_text,
    )


def parse_strategy_override(answer: str) -> str | None:
    value = " ".join(answer.casefold().replace("-", "_").split())
    if not value:
        return None
    normalized = value.replace("_", " ")
    if value in _OVERRIDE_ALIASES:
        return _OVERRIDE_ALIASES[value]
    if normalized in _OVERRIDE_ALIASES:
        return _OVERRIDE_ALIASES[normalized]
    raise StrategyOverrideError(
        "strategy override must be empty, sdd_low, sdd_medium, sdd_high, or explorer"
    )


def finalize_strategy_decision(
    recommendation: StrategyDecision,
    *,
    answer: str | None = None,
    prompted: bool = False,
) -> StrategyDecision:
    recommendation = _with_recommendation_defaults(recommendation)
    selected = recommendation.strategy
    source = "prompt_accept" if prompted else "automatic"
    raw_answer = answer if answer is not None else None
    override = parse_strategy_override(answer) if answer is not None else None
    if override is not None:
        selected = override
        source = "prompt_override" if prompted else "override"
    elif answer is not None and prompted:
        source = "prompt_accept"

    if selected == "SDD_LOW":
        selected = "SDD"
        complexity = "LOW"
    elif selected == "SDD_MEDIUM":
        selected = "SDD"
        complexity = "MEDIUM"
    elif selected == "SDD_HIGH":
        selected = "SDD"
        complexity = "HIGH"
    elif selected == "EXPLORER":
        complexity = recommendation.complexity if recommendation.complexity != "LOW" else "MEDIUM"
    else:
        selected = "SDD" if selected != "EXPLORER" else selected
        complexity = recommendation.complexity

    overridden = selected != recommendation.recommended_strategy or complexity != recommendation.recommended_complexity
    reason = recommendation.reason
    if overridden:
        reason = f"User override selected {selected}; recommended {recommendation.recommended_strategy}: {reason}"
    return StrategyDecision(
        selected,
        complexity,
        recommendation.score,
        reason,
        recommendation.matched_signals,
        recommendation.recommended_strategy,
        recommendation.recommended_complexity,
        recommendation.confirmation_required,
        prompted,
        overridden,
        source,
        raw_answer,
    )


def strategy_audit(decision: StrategyDecision) -> dict[str, object]:
    decision = _with_recommendation_defaults(decision)
    return {
        "recommended_strategy": decision.recommended_strategy,
        "recommended_complexity": decision.recommended_complexity,
        "confirmation_required": decision.confirmation_required,
        "prompted": decision.prompted,
        "overridden": decision.overridden,
        "selection_source": decision.selection_source,
        "override_text": decision.override_text,
    }


def explorer_strategy_decision(request: str, signals: tuple[str, ...] = ()) -> StrategyDecision:
    del request
    selected_signals = signals or ("explorer_request",)
    return StrategyDecision(
        "EXPLORER",
        "MEDIUM",
        3,
        "Improvement explorer selected for discovery and triage before implementation",
        selected_signals,
        "EXPLORER",
        "MEDIUM",
        False,
    )


def is_explorer_request(request: str) -> bool:
    text = " ".join(request.casefold().split())
    return bool(_EXPLORER_PATTERN.search(text)) and not _EXPLORER_EXCLUSIONS.search(text)


def select_strategy(request: str) -> StrategyDecision:
    if is_explorer_request(request):
        return explorer_strategy_decision(request)
    text = " ".join(request.casefold().split())
    weighted = {**_MEDIUM_SIGNALS, **_HIGH_SIGNALS}
    matches = [name for name, (pattern, _) in weighted.items() if re.search(pattern, text)]
    score = sum(weighted[name][1] for name in matches)
    low = [name for name, pattern in _LOW_SIGNALS.items() if re.search(pattern, text)]
    if "implementation_plan" in matches and {"typo", "mechanical", "trivial_bug"} & set(low):
        matches.remove("implementation_plan")
        score -= _MEDIUM_SIGNALS["implementation_plan"][1]

    if any(name in _HIGH_SIGNALS for name in matches) or score >= 4:
        complexity = "HIGH"
    elif score >= 2:
        complexity = "MEDIUM"
    else:
        complexity = "LOW"
        matches.extend(low)
    strategy = "SDD"
    signals = tuple(dict.fromkeys(matches))
    reason = (
        f"{complexity} complexity selected from score {score}"
        + (f" using signals: {', '.join(signals)}" if signals else " with no complexity signals")
    )
    confirmation_required = complexity == "MEDIUM"
    return StrategyDecision(
        strategy,
        complexity,
        score,
        reason,
        signals,
        strategy,
        complexity,
        confirmation_required,
    )
