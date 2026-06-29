"""Low-level terminal prompt primitives for the AI Harness launcher."""

from __future__ import annotations

import os
import select
import sys
import termios
import tty
from typing import NamedTuple


class _LauncherExit(Exception):
    """Clean cancellation from an interactive launcher prompt."""


class _MenuItem(NamedTuple):
    key: str
    label: str
    value: str
    shortcuts: tuple[str, ...] = ()


def _interactive_stdin() -> bool:
    return sys.stdin.isatty()


def _print_prompt_help(kind: str) -> None:
    print("Controls:", file=sys.stderr)
    if kind in {"action", "decision"}:
        print("  Up/Down: move selection", file=sys.stderr)
        print("  Enter: select highlighted item", file=sys.stderr)
        print("  Number keys: select by number", file=sys.stderr)
    if kind in {"request", "answer"}:
        print("  Enter: submit", file=sys.stderr)
        print("  Alt+Enter: insert newline when supported by the terminal", file=sys.stderr)
    if kind == "model":
        print("  Enter: select the highlighted model", file=sys.stderr)
    if kind == "scope":
        print("  Enter a menu number, repository-relative path, or blank for explorer-first", file=sys.stderr)
    if kind == "console":
        print("  / or /menu: open the action menu", file=sys.stderr)
        print("  Slash actions include /status, /runs, /resume, /archive, /install-ci, /install-packages, /model, /help, and /exit", file=sys.stderr)
        print("  Any other text starts a harness run", file=sys.stderr)
    if kind == "multi":
        print("  Up/Down: move selection", file=sys.stderr)
        print("  Space: toggle highlighted item", file=sys.stderr)
        print("  Enter: confirm selection", file=sys.stderr)
        print("  Number keys: toggle by number", file=sys.stderr)
    print("  /help: show this help", file=sys.stderr)
    print("  /exit: exit without invoking the backend", file=sys.stderr)


def _handle_slash_command(value: str, *, kind: str) -> bool:
    command = value.strip()
    if not command.startswith("/"):
        return False
    if command == "/exit":
        raise _LauncherExit
    if command == "/help":
        _print_prompt_help(kind)
        return True
    if kind == "console" and command == "/model":
        return False
    print(f"Unknown slash command: {command}", file=sys.stderr)
    return True


class _RawTerminal:
    def __enter__(self) -> "_RawTerminal":
        self._fd = sys.stdin.fileno()
        self._settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._settings)


def _read_key_byte(timeout: float | None = None) -> str:
    fd = sys.stdin.fileno()
    if timeout is not None:
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return ""
    try:
        data = os.read(fd, 1)
    except BlockingIOError:
        return ""
    return data.decode("utf-8", errors="ignore")


def _read_key() -> str:
    first = _read_key_byte()
    if first == "\x03":
        raise KeyboardInterrupt
    if first != "\x1b":
        return first
    second = _read_key_byte(0.20)
    if second in {"\r", "\n"}:
        return "alt-enter"
    if second in {"[", "O"}:
        third = _read_key_byte(0.20)
        if third == "A":
            return "up"
        if third == "B":
            return "down"
        return first + second + third
    return first + second


def _read_menu_command() -> str:
    command = ["/"]
    print("/", end="", file=sys.stderr, flush=True)
    while True:
        key = _read_key()
        if key in {"\r", "\n"}:
            print(file=sys.stderr)
            return "".join(command)
        if key in {"\x7f", "\b"}:
            if len(command) > 1:
                command.pop()
                print("\b \b", end="", file=sys.stderr, flush=True)
            continue
        if len(key) == 1 and key.isprintable():
            command.append(key)
            print(key, end="", file=sys.stderr, flush=True)


def _render_menu(title_lines: list[str], items: list[_MenuItem], selected: int) -> None:
    for line in title_lines:
        print(f"\x1b[2K{line}", file=sys.stderr)
    for index, item in enumerate(items, 1):
        prefix = ">" if index - 1 == selected else " "
        print(f"\x1b[2K{prefix} {index}. {item.label}", file=sys.stderr)


def _redraw_menu(title_lines: list[str], items: list[_MenuItem], selected: int) -> None:
    line_count = len(title_lines) + len(items) + 1
    print(f"\x1b[{line_count}F", end="", file=sys.stderr)
    _render_menu(title_lines, items, selected)
    print("\x1b[2KUse Up/Down, Enter, number keys, /help, or /exit.", file=sys.stderr, flush=True)


def _menu_prompt(title_lines: list[str], items: list[_MenuItem], *, help_kind: str, default_index: int = 0, allow_blank_default: bool = False) -> _MenuItem:
    if not items:
        raise ValueError("menu requires at least one item")
    if _interactive_stdin():
        try:
            selected = max(0, min(default_index, len(items) - 1))
            with _RawTerminal():
                _render_menu(title_lines, items, selected)
                print("Use Up/Down, Enter, number keys, /help, or /exit.", file=sys.stderr, flush=True)
                while True:
                    key = _read_key()
                    if key == "up":
                        selected = (selected - 1) % len(items)
                        _redraw_menu(title_lines, items, selected)
                        continue
                    if key == "down":
                        selected = (selected + 1) % len(items)
                        _redraw_menu(title_lines, items, selected)
                        continue
                    if key in {"\r", "\n"}:
                        return items[selected]
                    if key == "/":
                        if _handle_slash_command(_read_menu_command(), kind=help_kind):
                            continue
                    if len(key) == 1:
                        lowered = key.casefold()
                        for index, item in enumerate(items, 1):
                            if key == str(index) or lowered == item.key.casefold() or lowered in {shortcut.casefold() for shortcut in item.shortcuts}:
                                return item
        except _LauncherExit:
            raise
        except (OSError, termios.error):
            pass
    for line in title_lines:
        print(line, file=sys.stderr)
    for index, item in enumerate(items, 1):
        print(f" {index}. {item.label}", file=sys.stderr)
    while True:
        choice = input("Select: ").strip()
        if allow_blank_default and not choice:
            return items[default_index]
        if _handle_slash_command(choice, kind=help_kind):
            continue
        lowered = choice.casefold()
        for index, item in enumerate(items, 1):
            if choice == str(index) or lowered == item.key.casefold() or lowered in {shortcut.casefold() for shortcut in item.shortcuts}:
                return item
        print("Enter a menu number.", file=sys.stderr)



def _render_multi_select(title_lines: list[str], items: list[_MenuItem], selected: int, checked: set[int]) -> None:
    for line in title_lines:
        print(f"\x1b[2K{line}", file=sys.stderr)
    for index, item in enumerate(items, 1):
        pointer = ">" if index - 1 == selected else " "
        marker = "[x]" if index - 1 in checked else "[ ]"
        print(f"\x1b[2K{pointer} {index}. {marker} {item.label}", file=sys.stderr)


def _redraw_multi_select(title_lines: list[str], items: list[_MenuItem], selected: int, checked: set[int]) -> None:
    line_count = len(title_lines) + len(items) + 1
    print(f"\x1b[{line_count}F", end="", file=sys.stderr)
    _render_multi_select(title_lines, items, selected, checked)
    print("\x1b[2KUse Up/Down, Space, Enter, number keys, /help, or /exit.", file=sys.stderr, flush=True)


def _multi_select_prompt(title_lines: list[str], items: list[_MenuItem], *, help_kind: str = "multi", default_indexes: set[int] | None = None) -> list[_MenuItem]:
    if not items:
        return []
    checked = {index for index in (default_indexes or set()) if 0 <= index < len(items)}
    if _interactive_stdin():
        try:
            selected = 0
            with _RawTerminal():
                _render_multi_select(title_lines, items, selected, checked)
                print("Use Up/Down, Space, Enter, number keys, /help, or /exit.", file=sys.stderr, flush=True)
                while True:
                    key = _read_key()
                    if key == "up":
                        selected = (selected - 1) % len(items)
                        _redraw_multi_select(title_lines, items, selected, checked)
                        continue
                    if key == "down":
                        selected = (selected + 1) % len(items)
                        _redraw_multi_select(title_lines, items, selected, checked)
                        continue
                    if key == " ":
                        checked.symmetric_difference_update({selected})
                        _redraw_multi_select(title_lines, items, selected, checked)
                        continue
                    if key in {"\r", "\n"}:
                        return [item for index, item in enumerate(items) if index in checked]
                    if key == "/":
                        if _handle_slash_command(_read_menu_command(), kind=help_kind):
                            continue
                    if len(key) == 1:
                        lowered = key.casefold()
                        for index, item in enumerate(items, 1):
                            if key == str(index) or lowered == item.key.casefold() or lowered in {shortcut.casefold() for shortcut in item.shortcuts}:
                                checked.symmetric_difference_update({index - 1})
                                selected = index - 1
                                _redraw_multi_select(title_lines, items, selected, checked)
                                break
        except _LauncherExit:
            raise
        except (OSError, termios.error):
            pass
    for line in title_lines:
        print(line, file=sys.stderr)
    for index, item in enumerate(items, 1):
        marker = "[x]" if index - 1 in checked else "[ ]"
        print(f" {index}. {marker} {item.label}", file=sys.stderr)
    while True:
        choice = input("Select optional numbers, comma separated; blank for none: ").strip()
        if not choice:
            return []
        if _handle_slash_command(choice, kind=help_kind):
            continue
        indexes: set[int] = set()
        valid = True
        for part in choice.replace(",", " ").split():
            if not part.isdigit() or not (1 <= int(part) <= len(items)):
                valid = False
                break
            indexes.add(int(part) - 1)
        if valid:
            return [item for index, item in enumerate(items) if index in indexes]
        print("Enter listed numbers separated by commas.", file=sys.stderr)

def _text_prompt(prompt: str, *, help_kind: str, multiline_fallback_terminator: str | None = None) -> str:
    if _interactive_stdin():
        try:
            with _RawTerminal():
                buffer: list[str] = []
                print(prompt, end="", file=sys.stderr, flush=True)
                while True:
                    key = _read_key()
                    if key in {"\r", "\n"}:
                        print(file=sys.stderr)
                        value = "".join(buffer).strip()
                        if _handle_slash_command(value, kind=help_kind):
                            buffer.clear()
                            print(prompt, end="", file=sys.stderr, flush=True)
                            continue
                        return value
                    if key == "alt-enter":
                        buffer.append("\n")
                        print("\n... ", end="", file=sys.stderr, flush=True)
                        continue
                    if key.startswith("\x1b"):
                        continue
                    if key in {"\x7f", "\b"}:
                        if buffer:
                            buffer.pop()
                            print("\b \b", end="", file=sys.stderr, flush=True)
                        continue
                    if len(key) == 1 and key.isprintable():
                        buffer.append(key)
                        print(key, end="", file=sys.stderr, flush=True)
        except _LauncherExit:
            raise
        except (OSError, termios.error):
            pass
    if multiline_fallback_terminator is not None:
        print("Paste the request. Finish with a line containing only a single dot.", file=sys.stderr)
        while True:
            lines: list[str] = []
            while True:
                try:
                    line = input()
                except EOFError:
                    return "\n".join(lines).strip()
                if line == multiline_fallback_terminator:
                    break
                if _handle_slash_command(line.strip(), kind=help_kind):
                    continue
                lines.append(line)
            if lines:
                return "\n".join(lines).strip()
    while True:
        value = input(prompt).strip()
        if _handle_slash_command(value, kind=help_kind):
            continue
        return value


def _line_prompt(prompt: str, *, help_kind: str, allow_blank: bool = False) -> str | None:
    while True:
        value = input(prompt).strip()
        if _handle_slash_command(value, kind=help_kind):
            continue
        if not value and allow_blank:
            return None
        return value
