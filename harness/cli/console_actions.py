"""Console action registry, parsing, and suggestions."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Literal


ConsoleContext = Literal["console", "request"]
ParsedKind = Literal["action", "menu", "request", "empty", "error", "unknown_slash"]


@dataclass(frozen=True, slots=True)
class ConsoleAction:
    name: str
    label: str
    key: str
    aliases: tuple[str, ...] = ()
    contexts: tuple[ConsoleContext, ...] = ("console",)
    menu_visible: bool = True
    top_level: bool = False


@dataclass(frozen=True, slots=True)
class ParsedConsoleInput:
    kind: ParsedKind
    raw_line: str
    is_slash: bool = False
    action: ConsoleAction | None = None
    args: tuple[str, ...] = ()
    request: str = ""
    error: str = ""


CONSOLE_ACTIONS: tuple[ConsoleAction, ...] = (
    ConsoleAction("status", "Show status", "s", top_level=True),
    ConsoleAction("runs", "Show live runs", "r", top_level=True),
    ConsoleAction("resume", "Resume run", "u", top_level=True),
    ConsoleAction("archive", "Archive run", "a", top_level=True),
    ConsoleAction("start", "Start request", "n", ("new",)),
    ConsoleAction("sdd", "Start full SDD", "f", top_level=True),
    ConsoleAction("explore", "Run explore bundle", "e", top_level=True),
    ConsoleAction("proposal", "Run proposal bundle", "o", top_level=True),
    ConsoleAction("spec", "Run spec bundle", "w", top_level=True),
    ConsoleAction("design", "Run design bundle", "d", top_level=True),
    ConsoleAction("tasks", "Run tasks bundle", "t", top_level=True),
    ConsoleAction("tdd", "Run TDD bundle", "l", top_level=True),
    ConsoleAction("artifacts", "List run artifacts", "v", menu_visible=False, top_level=True),
    ConsoleAction("model", "Select model", "m", contexts=("console", "request")),
    ConsoleAction("ci-mode", "Select GitHub CI mode", "g", ("ci", "github-ci"), contexts=("console", "request")),
    ConsoleAction("jobs", "Show background jobs", "j"),
    ConsoleAction("attach", "Attach job output", "b"),
    ConsoleAction("detach", "Detach job output", "z"),
    ConsoleAction("cancel", "Cancel job", "k"),
    ConsoleAction("install-ci", "Install CI", "c", top_level=True),
    ConsoleAction("install-packages", "Install packages", "p", ("packages",), top_level=True),
    ConsoleAction("help", "Show help", "h"),
    ConsoleAction("exit", "Exit launcher", "x", ("quit",)),
)


def action_names(action: ConsoleAction) -> tuple[str, ...]:
    return (action.name, *action.aliases)


def actions_by_name(actions: tuple[ConsoleAction, ...] = CONSOLE_ACTIONS) -> dict[str, ConsoleAction]:
    return {value.casefold(): action for action in actions for value in action_names(action)}


def visible_actions(
    actions: tuple[ConsoleAction, ...] = CONSOLE_ACTIONS,
    *,
    context: ConsoleContext = "console",
) -> list[ConsoleAction]:
    return [action for action in actions if action.menu_visible and context in action.contexts]


def top_level_action_names(actions: tuple[ConsoleAction, ...] = CONSOLE_ACTIONS) -> set[str]:
    return {action.name for action in actions if action.top_level}


def parse_console_line(
    line: str,
    actions: tuple[ConsoleAction, ...] = CONSOLE_ACTIONS,
    *,
    context: ConsoleContext = "console",
) -> ParsedConsoleInput:
    raw = line.strip()
    is_slash = raw.startswith("/")
    normalized = raw[1:].strip() if is_slash else raw
    if not normalized:
        return ParsedConsoleInput("menu" if is_slash else "empty", raw, is_slash=is_slash)
    if normalized == "menu":
        return ParsedConsoleInput("menu", raw, is_slash=is_slash)
    try:
        parts = tuple(shlex.split(normalized))
    except ValueError as exc:
        return ParsedConsoleInput("error", raw, is_slash=is_slash, error=str(exc))
    if not parts:
        return ParsedConsoleInput("empty", raw, is_slash=is_slash)
    action = actions_by_name(actions).get(parts[0].casefold())
    if action is not None and context in action.contexts and (is_slash or context != "request"):
        return ParsedConsoleInput("action", raw, is_slash=is_slash, action=action, args=parts[1:])
    if is_slash:
        return ParsedConsoleInput("unknown_slash", raw, is_slash=True, error=f"Unknown slash command: /{parts[0]}")
    return ParsedConsoleInput("request", raw, request=raw)


def _subsequence_score(query: str, value: str) -> int | None:
    position = -1
    gap = 0
    for char in query:
        found = value.find(char, position + 1)
        if found < 0:
            return None
        gap += max(0, found - position - 1)
        position = found
    return gap


def _match_score(query: str, action: ConsoleAction) -> tuple[int, int, str]:
    haystacks = (*action_names(action), action.label)
    folded = [value.casefold() for value in haystacks]
    if not query:
        return (0, 0, "")
    if any(value == query for value in folded):
        return (0, 0, "")
    if any(value.startswith(query) for value in folded):
        return (1, 0, "")
    if any(query in value for value in folded):
        return (2, min(value.index(query) for value in folded if query in value), action.name)
    fuzzy = [_subsequence_score(query, value) for value in folded]
    candidates = [score for score in fuzzy if score is not None]
    if candidates:
        return (3, min(candidates), action.name)
    return (9, 0, action.name)


def suggest_console_actions(
    query: str,
    actions: tuple[ConsoleAction, ...] = CONSOLE_ACTIONS,
    *,
    context: ConsoleContext = "console",
    limit: int = 8,
) -> list[ConsoleAction]:
    normalized = query.strip().lstrip("/").casefold()
    candidates = visible_actions(actions, context=context)
    scored = [(_match_score(normalized, action), index, action) for index, action in enumerate(candidates)]
    if normalized:
        scored = [item for item in scored if item[0][0] < 9]
    scored.sort(key=lambda item: (item[0], item[1]))
    return [action for _, _, action in scored[:limit]]
