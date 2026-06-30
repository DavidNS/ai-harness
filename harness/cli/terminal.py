"""Terminal input and rendering helpers for the launcher console."""

from __future__ import annotations

import codecs
import os
import select
import shutil
import sys
import termios
import tty
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True, slots=True)
class TerminalIO:
    stdin: TextIO = sys.stdin
    stderr: TextIO = sys.stderr

    @property
    def interactive(self) -> bool:
        return self.stdin.isatty()

    @property
    def ansi(self) -> bool:
        return self.stdin.isatty() and self.stderr.isatty() and os.environ.get("TERM") != "dumb"

    @property
    def width(self) -> int:
        return max(20, shutil.get_terminal_size((80, 24)).columns)


class RawTerminal:
    def __init__(self, stdin: TextIO = sys.stdin) -> None:
        self._stdin = stdin

    def __enter__(self) -> "RawTerminal":
        self._fd = self._stdin.fileno()
        self._settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._settings)


class KeyReader:
    def __init__(self, stdin: TextIO = sys.stdin) -> None:
        self._stdin = stdin
        self._decoder = codecs.getincrementaldecoder("utf-8")("ignore")

    def _read_byte(self, timeout: float | None = None) -> bytes:
        fd = self._stdin.fileno()
        if timeout is not None:
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                return b""
        try:
            return os.read(fd, 1)
        except BlockingIOError:
            return b""

    def _read_text_byte(self, timeout: float | None = None) -> str:
        data = self._read_byte(timeout)
        return data.decode("ascii", errors="ignore") if data else ""

    def read_key(self) -> str:
        data = self._read_byte()
        if not data:
            return ""
        if data == b"\x03":
            raise KeyboardInterrupt
        if data == b"\x1b":
            return self._read_escape()
        text = self._decoder.decode(data)
        while not text:
            more = self._read_byte(0.02)
            if not more:
                return ""
            text = self._decoder.decode(more)
        return text

    def _read_escape(self) -> str:
        second = self._read_text_byte(0.05)
        if second in {"\r", "\n"}:
            return "alt-enter"
        if second not in {"[", "O"}:
            return "escape"
        sequence = second
        while True:
            char = self._read_text_byte(0.02)
            if not char:
                return "unknown"
            sequence += char
            if "@" <= char <= "~":
                break
        return {
            "[A": "up",
            "[B": "down",
            "[C": "right",
            "[D": "left",
            "[H": "home",
            "[F": "end",
            "OH": "home",
            "OF": "end",
            "[1~": "home",
            "[3~": "delete",
            "[4~": "end",
        }.get(sequence, "unknown")


class PromptRenderer:
    def __init__(self, terminal: TerminalIO | None = None) -> None:
        self.terminal = terminal or TerminalIO()

    def clear_previous(self, rows: int) -> None:
        if rows <= 0 or not self.terminal.ansi:
            return
        print(f"\x1b[{rows}F", end="", file=self.terminal.stderr)

    def clear_line(self, text: str = "", *, end: str = "\n") -> None:
        prefix = "\x1b[2K" if self.terminal.ansi else ""
        print(f"{prefix}{text}", end=end, file=self.terminal.stderr)

    def rows_for(self, text: str) -> int:
        width = max(1, self.terminal.width)
        return max(1, (len(_strip_ansi(text)) // width) + 1)


def _strip_ansi(text: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "\x1b" and index + 1 < len(text) and text[index + 1] == "[":
            index += 2
            while index < len(text) and not ("@" <= text[index] <= "~"):
                index += 1
            index += 1
            continue
        result.append(text[index])
        index += 1
    return "".join(result)
