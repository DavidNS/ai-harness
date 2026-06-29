#!/usr/bin/env python3
"""Structured lifecycle checks for the temporary refactor process."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


PHASES = {
    "discovery",
    "decision",
    "implementation",
    "validation",
    "closeout",
    "committed",
    "blocked",
}
ACTIVE_BOUNDARY_PHASES = {"decision", "implementation", "validation", "closeout", "committed"}
WRITESET_PHASES = {"implementation", "validation", "closeout"}
VALIDATED_PHASES = {"closeout", "committed"}
TERMINAL_SESSION_PHASES = {"committed", "blocked"}
REQUIRED_LIFECYCLE_ACTIONS = [
    "inspect_state",
    "select_one_boundary",
    "record_boundary_scope",
    "collect_worker_reports_before_boundary_selection",
    "implement_inside_scope",
    "record_validations",
    "commit_or_record_blocker",
    "run_closeout_check",
]
LIFECYCLE_CONTRACT_KEYS = {
    "role",
    "startup_context",
    "session_overlay",
    "worker_policy",
    "worker_requirements",
    "archive_policy",
    "required_actions",
    "closeout_command",
}
SESSION_KEYS = {
    "checkpoint_id",
    "phase",
    "active_boundary",
    "required_validations",
    "worker_reports",
    "commit_hash",
    "blockers",
    "next_action",
}


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    messages: tuple[str, ...]


class ControlError(ValueError):
    """Raised when lifecycle state is malformed or violates a gate."""


def repository_root(start: Path) -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ControlError(completed.stderr.strip() or "not inside a git repository")
    return Path(completed.stdout.strip()).resolve()


def default_checkpoint_path(root: Path) -> Path:
    return root / "refactor" / "control" / "checkpoint.json"


def default_session_path(root: Path) -> Path:
    return root / "refactor" / "control" / "session.local.json"


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ControlError(f"{label} file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ControlError(f"{label} file is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ControlError(f"{label} must be a JSON object")
    return value


def load_state(path: Path) -> dict[str, Any]:
    return read_json_object(path, label="state")


def load_session_overlay(checkpoint_state: dict[str, Any], session_path: Path) -> dict[str, Any] | None:
    if not session_path.exists():
        return None
    overlay = read_json_object(session_path, label="session")
    checkpoint_id = require_string(checkpoint_state, "checkpoint_id")
    session_checkpoint_id = require_string(overlay, "checkpoint_id")
    if session_checkpoint_id != checkpoint_id:
        raise ControlError(
            "session.local.json was created for checkpoint "
            f"{session_checkpoint_id}, but tracked checkpoint is {checkpoint_id}; "
            "run `python3 refactor/control/control.py init --force` to re-create it"
        )
    unexpected = sorted(set(overlay) - SESSION_KEYS)
    if unexpected:
        raise ControlError(f"session contains unsupported keys: {', '.join(unexpected)}")
    return overlay


def is_terminal_session(overlay: dict[str, Any]) -> bool:
    return require_string(overlay, "phase") in TERMINAL_SESSION_PHASES


def load_control_state(
    root: Path,
    *,
    checkpoint: Path | None = None,
    session: Path | None = None,
    include_terminal_session: bool = True,
) -> dict[str, Any]:
    checkpoint_path = checkpoint or default_checkpoint_path(root)
    session_path = session or default_session_path(root)
    state = read_json_object(checkpoint_path, label="checkpoint")
    overlay = load_session_overlay(state, session_path)
    if overlay is not None and (include_terminal_session or not is_terminal_session(overlay)):
        state.update(overlay)
    return state


def load_last_terminal_session(root: Path, *, checkpoint: Path | None = None, session: Path | None = None) -> dict[str, Any] | None:
    checkpoint_path = checkpoint or default_checkpoint_path(root)
    session_path = session or default_session_path(root)
    state = read_json_object(checkpoint_path, label="checkpoint")
    overlay = load_session_overlay(state, session_path)
    if overlay is not None and is_terminal_session(overlay):
        return overlay
    return None


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_string(value: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or (not allow_empty and not raw.strip()):
        raise ControlError(f"{key} must be a nonempty string")
    return raw


def optional_string(value: dict[str, Any], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ControlError(f"{key} must be null or a nonempty string")
    return raw


def optional_string_list(value: dict[str, Any], key: str) -> list[str]:
    raw = value.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ControlError(f"{key} must be a list")
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ControlError(f"{key} must contain only nonempty strings")
        result.append(item)
    return result


def require_string_list(value: dict[str, Any], key: str) -> list[str]:
    raw = value.get(key)
    if not isinstance(raw, list):
        raise ControlError(f"{key} must be a list")
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ControlError(f"{key} must contain only nonempty strings")
        result.append(item)
    return result


def require_object(value: dict[str, Any], key: str) -> dict[str, Any] | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ControlError(f"{key} must be an object or null")
    return raw


def require_lifecycle_contract(state: dict[str, Any]) -> dict[str, Any]:
    contract = require_object(state, "lifecycle_contract")
    if contract is None:
        raise ControlError("lifecycle_contract must be an object")
    unexpected = sorted(set(contract) - LIFECYCLE_CONTRACT_KEYS)
    if unexpected:
        raise ControlError(f"lifecycle_contract contains unsupported keys: {', '.join(unexpected)}")
    role = require_string(contract, "role")
    if role != "orchestrator":
        raise ControlError("lifecycle_contract.role must be orchestrator")
    startup_context = require_string_list(contract, "startup_context")
    if startup_context != ["refactor/control/checkpoint.json"]:
        raise ControlError("lifecycle_contract.startup_context must only contain refactor/control/checkpoint.json")
    session_overlay = normalize_path(require_string(contract, "session_overlay"))
    if session_overlay != "refactor/control/session.local.json":
        raise ControlError("lifecycle_contract.session_overlay must be refactor/control/session.local.json")
    worker_policy = require_string(contract, "worker_policy")
    if worker_policy != "mandatory_scoped_evidence":
        raise ControlError("lifecycle_contract.worker_policy must be mandatory_scoped_evidence")
    worker_requirements = require_object(contract, "worker_requirements")
    if worker_requirements is None:
        raise ControlError("lifecycle_contract.worker_requirements must be an object")
    unexpected_worker_keys = sorted(set(worker_requirements) - {"minimum_reports_before_active_boundary", "required_report_statuses"})
    if unexpected_worker_keys:
        raise ControlError(
            "lifecycle_contract.worker_requirements contains unsupported keys: "
            f"{', '.join(unexpected_worker_keys)}"
        )
    minimum_reports = worker_requirements.get("minimum_reports_before_active_boundary")
    if not isinstance(minimum_reports, int) or minimum_reports < 1:
        raise ControlError("lifecycle_contract.worker_requirements.minimum_reports_before_active_boundary must be an integer >= 1")
    required_report_statuses = require_string_list(worker_requirements, "required_report_statuses")
    if required_report_statuses != ["completed"]:
        raise ControlError("lifecycle_contract.worker_requirements.required_report_statuses must be ['completed']")
    archive_policy = require_string(contract, "archive_policy")
    if archive_policy != "lazy_product_evidence_only":
        raise ControlError("lifecycle_contract.archive_policy must be lazy_product_evidence_only")
    actions = require_string_list(contract, "required_actions")
    if actions != REQUIRED_LIFECYCLE_ACTIONS:
        raise ControlError("lifecycle_contract.required_actions must match the required orchestrator lifecycle")
    closeout_command = require_string(contract, "closeout_command")
    if closeout_command != "python3 refactor/control/control.py check-closeout":
        raise ControlError("lifecycle_contract.closeout_command must be python3 refactor/control/control.py check-closeout")
    return contract


def require_worker_reports(state: dict[str, Any]) -> list[dict[str, Any]]:
    raw = state.get("worker_reports")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ControlError("worker_reports must be a list")
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ControlError("worker_reports entries must be objects")
        require_string(item, "worker")
        status = require_string(item, "status")
        if status not in {"completed", "blocked", "needs-decision"}:
            raise ControlError("worker_reports status must be completed, blocked, or needs-decision")
        require_string(item, "finding")
        result.append(item)
    return result


def normalize_path(path: str) -> str:
    raw = PurePosixPath(path)
    if not path or raw.is_absolute() or ".." in raw.parts:
        raise ControlError(f"path must be repository-relative and contained: {path}")
    return raw.as_posix()


def normalize_patterns(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(normalize_path(path) for path in paths))


def path_matches(path: str, patterns: Sequence[str]) -> bool:
    normalized = normalize_path(path)
    for pattern in patterns:
        pattern = normalize_path(pattern)
        if pattern.endswith("/") and normalized.startswith(pattern):
            return True
        if normalized == pattern or normalized.startswith(f"{pattern}/"):
            return True
    return False


def changed_paths(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ControlError(completed.stderr.strip() or "git status failed")
    paths: list[str] = []
    for line in completed.stdout.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        paths.append(normalize_path(path))
    return sorted(dict.fromkeys(paths))


def commit_exists(root: Path, commit_hash: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{commit_hash}^{{commit}}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def required_validations(state: dict[str, Any]) -> list[dict[str, Any]]:
    raw = state.get("required_validations")
    if not isinstance(raw, list):
        raise ControlError("required_validations must be a list")
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ControlError("required_validations entries must be objects")
        command = item.get("command")
        status = item.get("status")
        if not isinstance(command, str) or not command.strip():
            raise ControlError("validation command must be a nonempty string")
        if status not in {"pending", "passed", "failed"}:
            raise ControlError("validation status must be pending, passed, or failed")
        result.append(item)
    return result


def validate_state(state: dict[str, Any], root: Path, *, check_git: bool = False) -> CheckResult:
    messages: list[str] = []
    if state.get("schema_version") != 1:
        raise ControlError("schema_version must be 1")
    require_string(state, "checkpoint_id")
    phase = require_string(state, "phase")
    if phase not in PHASES:
        raise ControlError(f"phase must be one of: {', '.join(sorted(PHASES))}")
    require_string(state, "objective")
    require_string(state, "next_action")
    boundary = require_object(state, "active_boundary")
    if phase in ACTIVE_BOUNDARY_PHASES and boundary is None:
        raise ControlError(f"{phase} phase requires active_boundary")
    if boundary is not None:
        require_string(boundary, "name")
        require_string_list(boundary, "allowed_files")
        require_string_list(boundary, "forbidden_files")
        require_string(boundary, "decision", allow_empty=True)
    validations = required_validations(state)
    blockers = optional_string_list(state, "blockers")
    commit_hash = optional_string(state, "commit_hash")
    contract = require_lifecycle_contract(state)
    worker_requirements = require_object(contract, "worker_requirements")
    assert worker_requirements is not None
    worker_reports = require_worker_reports(state)

    if phase in WRITESET_PHASES and boundary is not None:
        allowed = normalize_patterns(require_string_list(boundary, "allowed_files"))
        forbidden = normalize_patterns(require_string_list(boundary, "forbidden_files"))
        if not allowed:
            raise ControlError(f"{phase} phase requires allowed_files")
        if check_git:
            touched = changed_paths(root)
            illegal = [path for path in touched if not path_matches(path, allowed)]
            forbidden_touches = [path for path in touched if path_matches(path, forbidden)]
            if forbidden_touches:
                raise ControlError(f"changed forbidden files: {', '.join(forbidden_touches)}")
            if illegal:
                raise ControlError(f"changed files outside allowed_files: {', '.join(illegal)}")
            messages.append(f"changed files checked: {len(touched)}")

    if phase in {"decision", "implementation", "validation", "closeout"}:
        minimum_reports = worker_requirements["minimum_reports_before_active_boundary"]
        if len(worker_reports) < minimum_reports:
            raise ControlError(
                "worker_reports must contain at least "
                f"{minimum_reports} completed report(s) before active boundary phases"
            )

    if phase in VALIDATED_PHASES:
        if not validations:
            raise ControlError(f"{phase} phase requires at least one required validation")
        pending = [item["command"] for item in validations if item["status"] != "passed"]
        if pending:
            raise ControlError(f"required validations are not passed: {', '.join(pending)}")

    if phase in {"closeout", "committed"}:
        if commit_hash is None and not blockers:
            raise ControlError(f"{phase} phase requires commit_hash or an exact blocker")
        if commit_hash is not None and check_git and not commit_exists(root, commit_hash):
            raise ControlError(f"commit_hash does not exist locally: {commit_hash}")
    if phase == "blocked" and not blockers:
        raise ControlError("blocked phase requires at least one exact blocker")

    messages.append(f"state valid: phase={phase}")
    return CheckResult(True, tuple(messages))


def command_status(args: argparse.Namespace) -> int:
    root = repository_root(Path.cwd())
    checkpoint = Path(args.checkpoint) if args.checkpoint else None
    session = Path(args.session) if args.session else None
    state = load_state(Path(args.state)) if args.state else load_control_state(
        root,
        checkpoint=checkpoint,
        session=session,
        include_terminal_session=False,
    )
    phase = require_string(state, "phase")
    boundary = require_object(state, "active_boundary")
    contract = require_lifecycle_contract(state)
    print(f"phase: {phase}")
    print(f"role: {contract['role']}")
    print(f"boundary: {boundary.get('name') if boundary else 'none'}")
    print(f"next_action: {require_string(state, 'next_action')}")
    print(f"closeout_command: {contract['closeout_command']}")
    if worker_reports := require_worker_reports(state):
        print(f"worker_reports: {len(worker_reports)}")
    if optional_string(state, "commit_hash"):
        print(f"commit_hash: {state['commit_hash']}")
    if state.get("blockers"):
        print("blockers:")
        for item in require_string_list(state, "blockers"):
            print(f"- {item}")
    if not args.state:
        terminal = load_last_terminal_session(root, checkpoint=checkpoint, session=session)
        if terminal is not None:
            terminal_boundary = require_object(terminal, "active_boundary")
            print(f"last_closeout_phase: {require_string(terminal, 'phase')}")
            print(f"last_closeout_boundary: {terminal_boundary.get('name') if terminal_boundary else 'none'}")
            if optional_string(terminal, "commit_hash"):
                print(f"last_closeout_commit: {terminal['commit_hash']}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    root = repository_root(Path.cwd())
    state = load_state(Path(args.state)) if args.state else load_control_state(root, checkpoint=Path(args.checkpoint) if args.checkpoint else None, session=Path(args.session) if args.session else None)
    result = validate_state(state, root, check_git=args.git)
    for message in result.messages:
        print(message)
    return 0


def command_check_closeout(args: argparse.Namespace) -> int:
    root = repository_root(Path.cwd())
    state = load_state(Path(args.state)) if args.state else load_control_state(root, checkpoint=Path(args.checkpoint) if args.checkpoint else None, session=Path(args.session) if args.session else None)
    phase = require_string(state, "phase")
    if phase not in {"closeout", "committed", "blocked"}:
        raise ControlError("closeout check requires phase closeout, committed, or blocked")
    result = validate_state(state, root, check_git=True)
    for message in result.messages:
        print(message)
    return 0


def command_init(args: argparse.Namespace) -> int:
    root = repository_root(Path.cwd())
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else default_checkpoint_path(root)
    session_path = Path(args.session) if args.session else default_session_path(root)
    if session_path.exists() and not args.force:
        raise ControlError(f"session already exists: {session_path}")
    checkpoint = read_json_object(checkpoint_path, label="checkpoint")
    checkpoint_id = require_string(checkpoint, "checkpoint_id")
    require_string(checkpoint, "phase")
    session = {
        "checkpoint_id": checkpoint_id,
        "phase": checkpoint.get("phase"),
        "active_boundary": checkpoint.get("active_boundary"),
        "required_validations": checkpoint.get("required_validations", []),
        "worker_reports": checkpoint.get("worker_reports", []),
        "commit_hash": None,
        "blockers": [],
        "next_action": checkpoint.get("next_action", "Continue from tracked checkpoint."),
    }
    write_json(session_path, session)
    print(f"created local session: {session_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", help="path to lifecycle state JSON")
    parser.add_argument("--checkpoint", help="path to tracked checkpoint JSON")
    parser.add_argument("--session", help="path to ignored local session JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--force", action="store_true", help="overwrite an existing local session")
    sub.add_parser("status")
    validate = sub.add_parser("validate")
    validate.add_argument("--git", action="store_true", help="also validate current git changes against write scope")
    closeout = sub.add_parser("check-closeout")
    closeout.add_argument("--git", action="store_true", default=True, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return command_init(args)
        if args.command == "status":
            return command_status(args)
        if args.command == "validate":
            return command_validate(args)
        if args.command == "check-closeout":
            return command_check_closeout(args)
    except ControlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
