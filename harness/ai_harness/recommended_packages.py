"""Recommended package groups for optional harness tooling."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
RECOMMENDATIONS = ROOT / "recommended-packages.json"


@dataclass(frozen=True, slots=True)
class PackageGroup:
    id: str
    label: str
    required: bool
    pip: tuple[str, ...]
    commands: tuple[str, ...]
    environment: tuple[str, ...]
    description: str


@dataclass(frozen=True, slots=True)
class PackageInstallResult:
    selected: tuple[str, ...]
    pip_packages: tuple[str, ...]
    command: tuple[str, ...]
    missing_commands: tuple[str, ...]
    environment: tuple[str, ...]
    dry_run: bool
    returncode: int


def load_recommended_package_groups(path: Path = RECOMMENDATIONS) -> tuple[PackageGroup, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported recommended packages schema")
    groups: list[PackageGroup] = []
    for item in data.get("groups", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("recommended package group requires an id")
        groups.append(
            PackageGroup(
                id=item["id"],
                label=str(item.get("label") or item["id"]),
                required=bool(item.get("required", False)),
                pip=tuple(str(value) for value in item.get("pip", []) if str(value).strip()),
                commands=tuple(str(value) for value in item.get("commands", []) if str(value).strip()),
                environment=tuple(str(value) for value in item.get("environment", []) if str(value).strip()),
                description=str(item.get("description") or ""),
            )
        )
    return tuple(groups)


def selected_package_groups(groups: Sequence[PackageGroup], optional_ids: Sequence[str], *, all_optional: bool = False) -> tuple[PackageGroup, ...]:
    by_id = {group.id: group for group in groups}
    unknown = [value for value in optional_ids if value not in by_id]
    if unknown:
        raise ValueError("unknown package group: " + ", ".join(unknown))
    selected = [group for group in groups if group.required]
    optionals = [group for group in groups if not group.required and (all_optional or group.id in set(optional_ids))]
    return tuple(selected + optionals)


def pip_packages(groups: Sequence[PackageGroup]) -> tuple[str, ...]:
    seen: set[str] = set()
    packages: list[str] = []
    for group in groups:
        for package in group.pip:
            if package not in seen:
                seen.add(package)
                packages.append(package)
    return tuple(packages)


def install_recommended_packages(
    optional_ids: Sequence[str] = (),
    *,
    all_optional: bool = False,
    dry_run: bool = False,
    runner: Callable[..., Any] = subprocess.run,
) -> PackageInstallResult:
    selected = selected_package_groups(load_recommended_package_groups(), optional_ids, all_optional=all_optional)
    packages = pip_packages(selected)
    command = (sys.executable, "-m", "pip", "install", *packages) if packages else ()
    missing_commands = tuple(command for group in selected for command in group.commands if shutil.which(command) is None)
    environment = tuple(value for group in selected for value in group.environment)
    returncode = 0
    if command and not dry_run:
        completed = runner(command, check=False)
        returncode = int(getattr(completed, "returncode", 1))
    return PackageInstallResult(
        selected=tuple(group.id for group in selected),
        pip_packages=packages,
        command=command,
        missing_commands=missing_commands,
        environment=environment,
        dry_run=dry_run,
        returncode=returncode,
    )


def render_package_install_result(result: PackageInstallResult) -> str:
    lines = ["Recommended package groups: " + ", ".join(result.selected)]
    if result.command:
        prefix = "Would run" if result.dry_run else "Ran"
        lines.append(prefix + ": " + " ".join(result.command))
    else:
        lines.append("No pip packages selected.")
    if result.missing_commands:
        lines.append("Missing external commands: " + ", ".join(result.missing_commands))
    if result.environment:
        lines.append("Optional environment expected when used: " + ", ".join(result.environment))
    if result.returncode:
        lines.append(f"Package installation failed with exit code {result.returncode}.")
    return "\n".join(lines) + "\n"
