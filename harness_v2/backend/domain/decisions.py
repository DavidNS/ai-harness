"""User decision domain objects for v2 runs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from harness_v2.backend.domain.escalation import EscalationCategory
from harness_v2.backend.domain.errors import DomainValidationError, require_text
from harness_v2.backend.domain.lifecycle import BundleName


def _normalize_options(options: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = tuple(require_text(option, "decision option") for option in options)
    if len(normalized) != len(set(normalized)):
        raise DomainValidationError("decision options must be unique")
    return normalized


class DecisionAction(StrEnum):
    CONTINUE = "CONTINUE"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True, slots=True)
class DecisionEffect:
    option: str
    action: DecisionAction = DecisionAction.CONTINUE
    category: EscalationCategory | None = None

    def __post_init__(self) -> None:
        action = DecisionAction(self.action)
        category = None if self.category is None else EscalationCategory(self.category)
        object.__setattr__(self, "option", require_text(self.option, "decision effect option"))
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "category", category)
        _validate_action_category(action, category, "escalation decision effect" if action is DecisionAction.ESCALATE else "continue decision effect")


def _validate_action_category(action: DecisionAction, category: EscalationCategory | None, label: str) -> None:
    if action is DecisionAction.ESCALATE and category is None:
        raise DomainValidationError(f"{label} requires an escalation category")
    if action is DecisionAction.CONTINUE and category is not None:
        raise DomainValidationError(f"{label} must not define an escalation category")


def _normalize_effects(
    options: tuple[str, ...],
    effects: tuple[DecisionEffect, ...] | list[DecisionEffect],
) -> tuple[DecisionEffect, ...]:
    normalized = tuple(DecisionEffect(effect.option, effect.action, effect.category) for effect in effects)
    effect_options = tuple(effect.option for effect in normalized)
    if len(effect_options) != len(set(effect_options)):
        raise DomainValidationError("decision effects must be unique per option")
    if any(option not in options for option in effect_options):
        raise DomainValidationError("decision effects must reference a decision option")
    if not options and normalized:
        raise DomainValidationError("open-ended decisions cannot define option effects")
    return normalized


@dataclass(frozen=True, slots=True)
class PendingDecision:
    decision_id: str
    origin_bundle: BundleName
    prompt: str
    created_at: str
    options: tuple[str, ...] = ()
    effects: tuple[DecisionEffect, ...] = ()
    default_action: DecisionAction = DecisionAction.CONTINUE
    default_category: EscalationCategory | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", require_text(self.decision_id, "decision ID"))
        object.__setattr__(self, "origin_bundle", BundleName(self.origin_bundle))
        object.__setattr__(self, "prompt", require_text(self.prompt, "decision prompt"))
        options = _normalize_options(self.options)
        default_action = DecisionAction(self.default_action)
        default_category = None if self.default_category is None else EscalationCategory(self.default_category)
        _validate_action_category(default_action, default_category, "default decision effect")
        object.__setattr__(self, "options", options)
        object.__setattr__(self, "effects", _normalize_effects(options, self.effects))
        object.__setattr__(self, "default_action", default_action)
        object.__setattr__(self, "default_category", default_category)
        object.__setattr__(self, "created_at", require_text(self.created_at, "decision timestamp"))

    def effect_for(self, response: str) -> DecisionEffect:
        normalized = require_text(response, "decision response")
        for effect in self.effects:
            if effect.option == normalized:
                return effect
        return DecisionEffect(normalized, self.default_action, self.default_category)


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    decision_id: str
    origin_bundle: BundleName
    prompt: str
    response: str
    created_at: str
    answered_at: str
    options: tuple[str, ...] = ()
    effects: tuple[DecisionEffect, ...] = ()
    default_action: DecisionAction = DecisionAction.CONTINUE
    default_category: EscalationCategory | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", require_text(self.decision_id, "decision ID"))
        object.__setattr__(self, "origin_bundle", BundleName(self.origin_bundle))
        object.__setattr__(self, "prompt", require_text(self.prompt, "decision prompt"))
        object.__setattr__(self, "response", require_text(self.response, "decision response"))
        object.__setattr__(self, "created_at", require_text(self.created_at, "decision timestamp"))
        object.__setattr__(self, "answered_at", require_text(self.answered_at, "decision answer timestamp"))
        options = _normalize_options(self.options)
        default_action = DecisionAction(self.default_action)
        default_category = None if self.default_category is None else EscalationCategory(self.default_category)
        _validate_action_category(default_action, default_category, "default decision effect")
        object.__setattr__(self, "options", options)
        object.__setattr__(self, "effects", _normalize_effects(options, self.effects))
        object.__setattr__(self, "default_action", default_action)
        object.__setattr__(self, "default_category", default_category)
