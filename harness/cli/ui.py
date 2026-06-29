"""Interactive terminal UI helpers for the AI Harness launcher."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from . import ui_primitives as _ui_primitives
from .ui_primitives import (
    _handle_slash_command,
    _interactive_stdin,
    _LauncherExit,
    _line_prompt,
    _MenuItem,
    _print_prompt_help,
    _RawTerminal,
    _read_key,
    _read_key_byte,
    _read_menu_command,
    _redraw_menu,
    _render_menu,
)
from .ui_scope import (
    ImprovementCandidate as _ImprovementCandidate,
)
from .ui_scope import (
    discover_improvement_candidates as _discover_improvement_candidates,
)
from .ui_scope import (
    request_scope_prompt_reason as _request_scope_prompt_reason,
)
from .ui_scope import (
    request_with_scope as _request_with_scope,
)
from .ui_scope import (
    validate_explorer_scope as _validate_explorer_scope,
)


def _sync_primitive_hooks() -> None:
    _ui_primitives._interactive_stdin = _interactive_stdin
    _ui_primitives._RawTerminal = _RawTerminal
    _ui_primitives._read_key = _read_key
    _ui_primitives._read_key_byte = _read_key_byte
    _ui_primitives._read_menu_command = _read_menu_command
    _ui_primitives._render_menu = _render_menu
    _ui_primitives._redraw_menu = _redraw_menu
    _ui_primitives._handle_slash_command = _handle_slash_command


def _menu_prompt(title_lines: list[str], items: list[_MenuItem], *, help_kind: str, default_index: int = 0, allow_blank_default: bool = False) -> _MenuItem:
    _sync_primitive_hooks()
    return _ui_primitives._menu_prompt(
        title_lines,
        items,
        help_kind=help_kind,
        default_index=default_index,
        allow_blank_default=allow_blank_default,
    )


def _text_prompt(prompt: str, *, help_kind: str, multiline_fallback_terminator: str | None = None) -> str:
    _sync_primitive_hooks()
    return _ui_primitives._text_prompt(
        prompt,
        help_kind=help_kind,
        multiline_fallback_terminator=multiline_fallback_terminator,
    )


def _print_scope_candidates(candidates: list[_ImprovementCandidate]) -> None:
    if not candidates:
        print("No improvement artifacts found under docs/explorer/improvements.", file=sys.stderr)
        return
    print("Available improvement artifacts:", file=sys.stderr)
    for index, candidate in enumerate(candidates, 1):
        print(f" {index}. {candidate.title} [{candidate.path}]", file=sys.stderr)


def _prompt_for_explorer_scope(repository: Path) -> str | None:
    candidates = _discover_improvement_candidates(repository)
    _print_scope_candidates(candidates)
    while True:
        print("Explorer scope (number/path, blank for explorer-first): ", end="", file=sys.stderr, flush=True)
        choice = input().strip()
        if _handle_slash_command(choice, kind="scope"):
            continue
        if not choice:
            return None
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(candidates):
                return candidates[index - 1].path
            print("Enter a listed number or repository-relative path.", file=sys.stderr)
            continue
        ok, normalized, reason = _validate_explorer_scope(repository, choice)
        if ok and normalized is not None:
            return normalized
        print(f"Invalid explorer scope: {reason}", file=sys.stderr)


def _prepare_console_request(namespace: Any, request: str) -> str:
    repository = namespace.cwd.resolve()
    reason = _request_scope_prompt_reason(repository, request)
    if reason is None or not sys.stdin.isatty():
        return request
    print(reason, file=sys.stderr)
    scope = _prompt_for_explorer_scope(repository)
    if scope is None:
        print("Continuing without an explorer scope; the backend may route explorer-first.", file=sys.stderr)
        return request
    print(f"Selected explorer scope {scope}.", file=sys.stderr)
    return _request_with_scope(request, scope)


def _ordered_options(request: dict[str, Any]) -> list[dict[str, Any]]:
    raw_options = request.get("options", [])
    if not isinstance(raw_options, list):
        return []
    options = [item for item in raw_options if isinstance(item, dict) and isinstance(item.get("id"), str)]
    scores = request.get("scores", {})
    if not isinstance(scores, dict):
        scores = {}
    ranked = request.get("ranked_paths", [])
    ranked_order = {value: index for index, value in enumerate(ranked) if isinstance(value, str)} if isinstance(ranked, list) else {}

    def option_score(option_id: str) -> int:
        value = scores.get(option_id)
        return value if isinstance(value, int) else 0

    if ranked_order or scores:
        indexed = list(enumerate(options))
        indexed.sort(key=lambda item: (ranked_order.get(str(item[1].get("id")), len(ranked_order)), -option_score(str(item[1].get("id"))), item[0]))
        return [item for _, item in indexed]
    return options


def _print_decision_details(request: dict[str, Any], options: list[dict[str, Any]]) -> None:
    context = request.get("context", [])
    if isinstance(context, list) and context:
        print("Context:", file=sys.stderr)
        for item in context:
            print(f"- {item}", file=sys.stderr)
    scores = request.get("scores", {})
    if isinstance(scores, dict) and scores:
        print("Scores:", file=sys.stderr)
        for option in options:
            option_id = str(option.get("id", ""))
            if option_id in scores:
                print(f"- {option_id}: {scores[option_id]}", file=sys.stderr)
    details = request.get("option_details", {})
    if isinstance(details, dict) and details:
        print("Option details:", file=sys.stderr)
        for option in options:
            option_id = str(option.get("id", ""))
            value = details.get(option_id)
            if isinstance(value, str) and value.strip():
                print(f"- {option_id}: {value}", file=sys.stderr)
            elif isinstance(value, list) and value:
                print(f"- {option_id}: " + "; ".join(str(item) for item in value), file=sys.stderr)
    signals = request.get("score_signals", {})
    if isinstance(signals, dict) and signals:
        print("Signals:", file=sys.stderr)
        for option in options:
            option_id = str(option.get("id", ""))
            values = signals.get(option_id)
            if isinstance(values, list) and values:
                print(f"- {option_id}: " + ", ".join(str(item) for item in values), file=sys.stderr)


def _prompt_for_decision(run_id: str, request: dict[str, Any]) -> tuple[str | None, str | None]:
    options = _ordered_options(request)
    allows_freeform = bool(request.get("allows_freeform", True))
    title_lines = [f"Decision required for run {run_id}"]
    question = str(request.get("question", "")).strip()
    if question:
        title_lines.append(question)
    items: list[_MenuItem] = []
    labels_by_id: dict[str, str] = {}
    for option in options:
        option_id = str(option.get("id", ""))
        label = str(option.get("label", option_id)).strip() or option_id
        labels_by_id[option_id] = label
        consequence = str(option.get("consequence", "")).strip()
        suffix = f" - {consequence}" if consequence else ""
        items.append(_MenuItem(option_id, f"{label} [{option_id}]{suffix}", option_id))
    if request.get("scores") or request.get("score_signals") or request.get("option_details") or request.get("context"):
        items.append(_MenuItem("d", "Details", "__details__", ("details",)))
    if allows_freeform:
        items.append(_MenuItem("f", "Free-form answer", "__freeform__", ("free", "freeform", "free-form")))
    while True:
        selected_item = _menu_prompt(title_lines, items, help_kind="decision")
        if selected_item.value == "__details__":
            _print_decision_details(request, options)
            continue
        if selected_item.value == "__freeform__":
            answer = _text_prompt("Answer: ", help_kind="answer")
            if answer:
                print("Selected free-form answer.", file=sys.stderr)
                return answer, None
            print("Answer cannot be empty.", file=sys.stderr)
            continue
        selected = selected_item.value
        label = labels_by_id.get(selected, selected)
        print(f"Selected {label} ({selected}).", file=sys.stderr)
        return None, selected


def _interactive_request() -> str:
    return _text_prompt("Request: ", help_kind="request", multiline_fallback_terminator=".")
