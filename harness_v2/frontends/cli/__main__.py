"""Minimal command-line frontend for the v2 walking skeleton."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from harness_v2.backend.application.contracts import CommandResult, StartRun
from harness_v2.hosts.in_process.host import InProcessHost


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AI Harness v2 walking skeleton")
    subcommands = parser.add_subparsers(dest="command", required=True)
    start = subcommands.add_parser("start", help="start a simulated v2 run")
    start.add_argument("request", nargs="+", help="request text")
    return parser


def _render_start(result: CommandResult) -> None:
    print(f"Run: {result.run.run_id}")
    print(f"Status: {result.run.status.value}")
    for event in result.events:
        phase = getattr(event, "phase", None)
        suffix = f" phase={phase}" if phase else ""
        print(f"Event: {type(event).__name__}{suffix}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    host = InProcessHost()
    if args.command == "start":
        request = " ".join(args.request)
        result = host.execute(StartRun(request=request))
        if not isinstance(result, CommandResult):
            raise TypeError(f"unexpected result: {type(result).__name__}")
        _render_start(result)
        return 0
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

