"""Parse a typed command line into an MVU message.

Bare commands travel to a menu (``Navigate``); commands with arguments run
directly (``Invoke``) as a power-user shortcut. This is the only place that
turns text into messages; everything downstream is message-driven.
"""

from __future__ import annotations

import shlex

from harness_v2.frontends.ui import messages as m

COMMAND_HELP = (
    "commands: /help, /refresh, /list, /select [run_id], /start [root_bundle] [request], "
    "/resume, /cancel, /retry [step_id], /retry-bundle [bundle], /decision [response], /watch [timeout], /quit "
    "(a command with no arguments opens its menu)"
)


class CommandError(ValueError):
    """Raised for malformed command input; the message is user-facing."""


def parse_command(raw: str) -> m.Msg | None:
    """Return the message for a ``/command`` line, or None to show help."""
    try:
        parts = shlex.split(raw[1:] if raw.startswith("/") else raw)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    if not parts:
        return None
    name, args = parts[0], tuple(parts[1:])

    if name in {"quit", "exit"}:
        return m.Quit()
    if name in {"refresh", "list"}:
        return m.Invoke("refresh")
    if name == "watch":
        return m.Invoke("watch", args[:1])
    if name == "resume":
        return m.Invoke("resume")
    if name == "cancel":
        return m.Invoke("cancel")
    if name == "select":
        return m.Invoke("select", (args[0],)) if args else m.Navigate("runs")
    if name == "start":
        if not args:
            return m.Navigate("start-bundle")
        if len(args) == 1:
            return m.Navigate("start-request", (args[0],))
        return m.Invoke("start", (args[0], " ".join(args[1:])))
    if name == "retry":
        if not args:
            return m.Navigate("retry-mode")
        return m.Invoke("retry-step", (args[0],))
    if name == "retry-bundle":
        return m.Invoke("retry-bundle", (args[0],)) if args else m.Navigate("retry-bundle")
    if name == "decision":
        return m.Invoke("decision", (" ".join(args),)) if args else m.Navigate("decision-options")
    if name == "help":
        return None
    raise CommandError(COMMAND_HELP)
