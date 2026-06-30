"""Pre-orchestration analysis/implementation gate."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from .strategy import select_strategy

GATE_PATHS = ("explore_bundle", "sdd")


ANALYSIS_ARTIFACT_PATTERN = re.compile(r"(?<![\w/.-])(docs/explorer/improvements/(?:[\w.-]+/)*[\w.-]+(?:/improvement\.md)?)(?![\w/.-])")
EXPLICIT_FULL_PATTERN = re.compile(r"\b(?:full\s+sdd|full_implementation|full\s+implementation)\b")
DRAFT_IMPROVEMENT_PATTERN = re.compile(r"(?<![\w/.-])(draft-improvements/[\w./-]+\.md)(?![\w.-])")
ANALYSIS_TERMS = re.compile(
    r"\b(?:investigat(?:e|ion)|analy[sz](?:e|is)|triage|research|figure out|draft|proposal|improvement idea|not documented|open question)\b"
)
BUG_TERMS = re.compile(
    r"\b(?:bug|debug|traceback|exception|failure|failing|error|regression|broken|crash|repro(?:duction)?)\b"
)
TRIVIAL_TERMS = re.compile(r"\b(?:typo|misspelling|format|mechanical|change a string|rename)\b")
FULL_TERMS = re.compile(
    r"\b(?:feature|workflow|orchestrat(?:or|ion)|controller|routing|resume|recovery|snapshot|state|"
    r"pipeline|schema|worker|artifact contract|artifact|phase graph|phase contract|decision gate|"
    r"architecture|redesign|migration|persisted)\b"
)


@dataclass(frozen=True, slots=True)
class ExplorerGateDecision:
    path: str
    reason: str
    matched_signals: tuple[str, ...]
    required_artifact: str | None = None
    supplied_artifact: str | None = None
    source: str = "heuristic"
    classifier_version: int = 1
    scores: dict[str, int] = field(default_factory=dict)
    score_signals: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def explorer_artifact_required(self) -> bool:
        return False

    @property
    def ranked_paths(self) -> tuple[str, ...]:
        return tuple(sorted(GATE_PATHS, key=lambda path: (-self.scores.get(path, 0), path)))

    def with_path(self, path: str, reason: str, *, source: str) -> "ExplorerGateDecision":
        return replace(self, path=path, reason=reason, source=source)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "reason": self.reason,
            "matched_signals": list(self.matched_signals),
            "entry_artifact": self.supplied_artifact,
            "required_artifact": self.required_artifact,
            "supplied_artifact": self.supplied_artifact,
            "explorer_artifact_required": self.explorer_artifact_required,
            "bug_brief_required": False,
            "source": self.source,
            "classifier_version": self.classifier_version,
            "scores": dict(self.scores),
            "score_signals": {key: list(value) for key, value in self.score_signals.items()},
            "ranked_paths": list(self.ranked_paths),
        }


def _add_score(scores: dict[str, int], signals: dict[str, list[str]], path: str, points: int, signal: str) -> None:
    scores[path] += points
    signals[path].append(f"{signal}+{points}")


def _score_gate(request: str, intent_text: str, supplied: str | None) -> tuple[dict[str, int], dict[str, tuple[str, ...]]]:
    text = " ".join(request.casefold().split())
    scores = {path: 0 for path in GATE_PATHS}
    signals: dict[str, list[str]] = {path: [] for path in GATE_PATHS}
    if supplied is not None:
        _add_score(scores, signals, "sdd", 5, "explorer_scope_supplied")
        if ANALYSIS_TERMS.search(intent_text):
            _add_score(scores, signals, "explore_bundle", 5, "explore_existing_scope")
    has_draft = DRAFT_IMPROVEMENT_PATTERN.search(request) is not None
    explorer_context = supplied is not None or has_draft or "improvement" in intent_text or "artifact" in intent_text or "document" in intent_text
    if has_draft:
        _add_score(scores, signals, "explore_bundle", 5, "draft_improvement_reference")
    if ANALYSIS_TERMS.search(intent_text) and explorer_context:
        _add_score(scores, signals, "explore_bundle", 4, "explorer_language")
    if "improvement" in intent_text:
        _add_score(scores, signals, "explore_bundle", 3, "improvement_language")
    if "artifact" in intent_text or "document" in intent_text:
        _add_score(scores, signals, "explore_bundle", 1, "artifact_language")
    if BUG_TERMS.search(text):
        _add_score(scores, signals, "sdd", 3, "bug_or_failure_language")
    if TRIVIAL_TERMS.search(text):
        _add_score(scores, signals, "sdd", 4, "trivial_change_language")
    if FULL_TERMS.search(text):
        _add_score(scores, signals, "sdd", 4, "full_implementation_language")
    strategy = select_strategy(request)
    if strategy.strategy == "SDD":
        _add_score(scores, signals, "sdd", max(strategy.score, 1), "strategy_sdd")
    return scores, {key: tuple(value) for key, value in signals.items()}


def _signals(score_signals: dict[str, tuple[str, ...]], *paths: str) -> tuple[str, ...]:
    values: list[str] = []
    for path in paths:
        values.extend(signal.split("+", 1)[0] for signal in score_signals.get(path, ()))
    return tuple(dict.fromkeys(values))


def _contested(scores: dict[str, int]) -> bool:
    return scores.get("explore_bundle", 0) > 0 and scores.get("sdd", 0) > 0


def _existing_analysis_artifact(request: str, repository: Path | None) -> str | None:
    for match in ANALYSIS_ARTIFACT_PATTERN.finditer(request):
        relative = match.group(1)
        if not relative.endswith("/improvement.md"):
            relative = str(Path(relative) / "improvement.md")
        if ".." in Path(relative).parts:
            continue
        if repository is None:
            return relative
        root = repository.resolve()
        expected = (root / "docs" / "explorer" / "improvements").resolve()
        candidate = (root / relative).resolve()
        try:
            if not candidate.is_relative_to(expected) or not candidate.is_file():
                continue
        except ValueError:
            continue
        try:
            first_line = candidate.read_text(encoding="utf-8").splitlines()[0].strip()
        except (OSError, UnicodeDecodeError, IndexError):
            continue
        if first_line in {"# Improvement Analysis v1", "# Improvement Explorer v1"} or first_line.startswith("# Improvement:"):
            return relative
    return None


def classify_explorer_gate(request: str, *, repository: Path | None = None) -> ExplorerGateDecision:
    intent_text = ANALYSIS_ARTIFACT_PATTERN.sub(" ", request)
    intent_text = DRAFT_IMPROVEMENT_PATTERN.sub(" ", intent_text)
    intent_text = " ".join(intent_text.casefold().split())
    supplied = _existing_analysis_artifact(request, repository)
    scores, score_signals = _score_gate(request, intent_text, supplied)
    required = None

    if supplied is not None and EXPLICIT_FULL_PATTERN.search(request.casefold()):
        return ExplorerGateDecision(
            "sdd",
            f"Explicit high-resolution SDD requested with supplied {supplied}",
            _signals(score_signals, "sdd") or ("explicit_sdd",),
            supplied_artifact=supplied,
            scores=scores,
            score_signals=score_signals,
        )

    return ExplorerGateDecision(
        "ask_user",
        "User must choose the harness flow before execution",
        _signals(score_signals, *GATE_PATHS) or ("user_flow_selection",),
        required_artifact=required,
        supplied_artifact=supplied,
        scores=scores,
        score_signals=score_signals,
    )
