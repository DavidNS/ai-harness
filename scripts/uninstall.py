#!/usr/bin/env python3
"""Safely remove AI Code Harness files owned by this checkout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from install import (
    CHECKOUT,
    Link,
    is_owned_bootstrap,
    is_owned_launcher,
    launcher_links_for,
    legacy_skill_links_for,
    links_for,
    points_to,
)


def uninstall_link(link: Link, *, dry_run: bool = False) -> tuple[bool, str]:
    destination = link.destination
    if link.provider is None:
        if is_owned_launcher(destination, link.source.parent, destination.name):
            if not dry_run:
                destination.unlink()
            verb = "would remove" if dry_run else "removed"
            return True, f"{verb}: {link.label}: {destination}"
        if destination.exists() or destination.is_symlink():
            return False, f"skipped: {destination} is not owned by this checkout"
        return True, f"absent: {link.label}: {destination}"
    if is_owned_bootstrap(destination, link.source.parents[1], link.provider):
        if not dry_run:
            destination.unlink()
        verb = "would remove" if dry_run else "removed"
        return True, f"{verb}: {link.label}: {destination}"
    if points_to(destination, link.source):
        if not dry_run:
            destination.unlink()
        verb = "would remove" if dry_run else "removed"
        return True, f"{verb}: {link.label}: {destination}"
    if destination.exists() or destination.is_symlink():
        return False, f"skipped: {destination} is not owned by this checkout"
    return True, f"absent: {link.label}: {destination}"


def uninstall(links: Sequence[Link], *, dry_run: bool = False) -> tuple[bool, list[str]]:
    ok = True
    messages: list[str] = []
    for link in links:
        item_ok, message = uninstall_link(link, dry_run=dry_run)
        ok = item_ok and ok
        messages.append(message)
    return ok, messages


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", action="store_true")
    parser.add_argument("--claude", action="store_true")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--global", dest="global_scope", action="store_true")
    scope.add_argument("--project", nargs="?", const=".", metavar="PATH")
    parser.add_argument("--launcher", action="store_true", help="also remove the aih shortcut if owned")
    parser.add_argument("--bin-dir", type=Path, help="directory containing launcher shortcuts (default: ~/.local/bin)")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    providers = [name for name in ("codex", "claude") if getattr(args, name)]
    if not providers and not args.launcher:
        parser.error("at least one of --codex, --claude, or --launcher is required")
    scope = {"home": Path.home()} if args.global_scope else {"project": Path(args.project)}
    plan: list[Link] = []
    if providers:
        plan.extend(links_for(CHECKOUT, providers, **scope))
        plan.extend(legacy_skill_links_for(CHECKOUT, providers, **scope))
    if args.launcher:
        plan.extend(launcher_links_for(CHECKOUT, args.bin_dir or (Path.home() / ".local" / "bin")))
    ok, messages = uninstall(plan, dry_run=args.dry_run)
    print("\n".join(messages))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
