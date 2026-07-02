"""Run the v2 daemon host."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from harness_v2.hosts.daemon.server import DaemonConfig, serve


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AI Harness v2 daemon host")
    parser.add_argument("--state-root", type=Path, default=Path(".ai-harness") / "v2")
    parser.add_argument("--working-directory", type=Path, default=None)
    parser.add_argument("--allow-repository-mutation", action="store_true")
    parser.add_argument("--branch", choices=("off", "current", "create", "create-from-main"), default="current")
    parser.add_argument("--github-ci-mode", choices=("off", "baseline", "branch"), default="baseline")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    serve(
        DaemonConfig(
            state_root=args.state_root,
            working_directory=args.working_directory,
            allow_repository_mutation=args.allow_repository_mutation,
            branch_mode=args.branch,
            github_ci_mode=args.github_ci_mode,
            host=args.host,
            port=args.port,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
