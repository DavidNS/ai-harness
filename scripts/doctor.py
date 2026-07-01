#!/usr/bin/env python3
"""Diagnose an AI Code Harness installation and local runtime support."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from install import (
    CHECKOUT,
    Link,
    bootstrap_content,
    is_owned_bootstrap,
    is_owned_launcher,
    launcher_content,
    launcher_links_for,
    links_for,
)

REQUIRED_HARNESS_DIRS = (
    "ai_harness",
    "prompts",
    "workers",
    "capabilities",
    "schemas",
    "references",
)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def check_python() -> Check:
    version = sys.version_info
    ok = version >= (3, 11)
    return Check("python", ok, f"{version.major}.{version.minor}.{version.micro}")


def check_sqlite() -> list[Check]:
    checks = [Check("sqlite", True, sqlite3.sqlite_version)]
    connection = sqlite3.connect(":memory:")
    try:
        try:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(value)")
            checks.append(Check("sqlite-fts5", True, "available"))
        except sqlite3.OperationalError as error:
            checks.append(Check("sqlite-fts5", False, str(error)))
    finally:
        connection.close()
    return checks


def check_direct_runner(checkout: Path = CHECKOUT) -> list[Check]:
    harness = checkout / "harness"
    runner = harness / "run.py"
    launcher = checkout / "ai-harness"
    ui_launcher = checkout / "ai-harness-ui"
    checks = [
        Check("runner", runner.is_file(), str(runner)),
        Check("launcher:aih", launcher.is_file(), str(launcher)),
        Check("launcher:aihui", ui_launcher.is_file(), str(ui_launcher)),
    ]
    for dirname in REQUIRED_HARNESS_DIRS:
        path = harness / dirname
        checks.append(Check(f"resource:{dirname}", path.is_dir(), str(path)))
    return checks


def check_bootstrap(link: Link) -> Check:
    provider = link.provider or "unknown"
    if not link.destination.exists() and not link.destination.is_symlink():
        return Check(f"bootstrap:{link.label}", False, f"missing: {link.destination}")
    if link.destination.is_symlink():
        return Check(f"bootstrap:{link.label}", False, f"symlink is not a generated bootstrap: {link.destination}")
    if not link.destination.is_file():
        return Check(f"bootstrap:{link.label}", False, f"not a file: {link.destination}")
    checkout = link.source.parents[1]
    if not is_owned_bootstrap(link.destination, checkout, provider):
        return Check(f"bootstrap:{link.label}", False, f"foreign or missing owner marker: {link.destination}")
    try:
        actual = link.destination.read_text(encoding="utf-8")
    except OSError as error:
        return Check(f"bootstrap:{link.label}", False, f"{link.destination}: {error}")
    expected = bootstrap_content(checkout, provider)
    if actual != expected:
        return Check(f"bootstrap:{link.label}", False, f"content drift: {link.destination}")
    return Check(f"bootstrap:{link.label}", True, str(link.destination))


def check_launcher_shortcut(link: Link) -> Check:
    if not link.destination.exists() and not link.destination.is_symlink():
        return Check(f"launcher:{link.label}", False, f"missing: {link.destination}")
    if link.destination.is_symlink():
        return Check(f"launcher:{link.label}", False, f"symlink is not a generated launcher: {link.destination}")
    if not link.destination.is_file():
        return Check(f"launcher:{link.label}", False, f"not a file: {link.destination}")
    checkout = link.source.parent
    command = link.destination.name
    if not is_owned_launcher(link.destination, checkout, command):
        return Check(f"launcher:{link.label}", False, f"foreign or missing owner marker: {link.destination}")
    try:
        actual = link.destination.read_text(encoding="utf-8")
    except OSError as error:
        return Check(f"launcher:{link.label}", False, f"{link.destination}: {error}")
    expected = launcher_content(checkout, command)
    if actual != expected:
        return Check(f"launcher:{link.label}", False, f"content drift: {link.destination}")
    if not shutil.which(str(link.destination)) and not link.destination.stat().st_mode & 0o111:
        return Check(f"launcher:{link.label}", False, f"not executable: {link.destination}")
    return Check(f"launcher:{link.label}", True, str(link.destination))


def check_provider(name: str) -> Check:
    command = shutil.which(name)
    return Check(f"provider:{name}", command is not None, command or "not found", required=False)


def check_runtime(project: Path) -> Check:
    runtime = project.resolve() / ".ai-harness"
    if runtime.exists() and not runtime.is_dir():
        return Check("runtime-path", False, f"not a directory: {runtime}")
    probe_parent = runtime if runtime.exists() else runtime.parent
    try:
        with tempfile.NamedTemporaryFile(prefix=".ai-harness-probe-", dir=probe_parent):
            pass
    except OSError as error:
        return Check("runtime-path", False, f"{runtime}: {error}")
    return Check("runtime-path", True, str(runtime))


def diagnose(
    links: Sequence[Link],
    providers: Sequence[str],
    project: Path,
    launcher_links: Sequence[Link] = (),
) -> list[Check]:
    checks = [check_python()]
    checks.extend(check_sqlite())
    checks.extend(check_direct_runner())
    checks.extend(check_bootstrap(link) for link in links)
    checks.extend(check_launcher_shortcut(link) for link in launcher_links)
    checks.extend(check_provider(provider) for provider in providers)
    checks.append(check_runtime(project))
    return checks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", action="store_true")
    parser.add_argument("--claude", action="store_true")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--global", dest="global_scope", action="store_true")
    scope.add_argument("--project", nargs="?", const=".", metavar="PATH")
    parser.add_argument("--launcher", action="store_true", help="also check the aih and aihui shortcuts")
    parser.add_argument("--bin-dir", type=Path, help="directory containing launcher shortcuts (default: ~/.local/bin)")
    parser.add_argument(
        "--runtime-project",
        type=Path,
        default=Path.cwd(),
        help="repository whose .ai-harness runtime path should be checked",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    providers = [name for name in ("codex", "claude") if getattr(args, name)]
    if not providers and not args.launcher:
        parser.error("at least one of --codex, --claude, or --launcher is required")
    scope = {"home": Path.home()} if args.global_scope else {"project": Path(args.project)}
    launcher_plan = launcher_links_for(CHECKOUT, args.bin_dir or (Path.home() / ".local" / "bin")) if args.launcher else []
    checks = diagnose(links_for(CHECKOUT, providers, **scope), providers, args.runtime_project, launcher_plan)
    for check in checks:
        status = "OK" if check.ok else ("WARN" if not check.required else "FAIL")
        print(f"{status} {check.name}: {check.detail}")
    return 0 if all(check.ok for check in checks if check.required) else 1


if __name__ == "__main__":
    sys.exit(main())
