from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = ROOT / "refactor" / "control" / "control.py"
spec = importlib.util.spec_from_file_location("refactor_control", CONTROL_PATH)
assert spec is not None and spec.loader is not None
control = importlib.util.module_from_spec(spec)
sys.modules["refactor_control"] = control
spec.loader.exec_module(control)


LIFECYCLE_CONTRACT = {
    "role": "orchestrator",
    "startup_context": ["refactor/control/checkpoint.json"],
    "session_overlay": "refactor/control/session.local.json",
    "worker_policy": "mandatory_scoped_evidence",
    "worker_requirements": {
        "minimum_reports_before_active_boundary": 1,
        "required_report_statuses": ["completed"],
    },
    "archive_policy": "lazy_product_evidence_only",
    "required_actions": [
        "inspect_state",
        "select_one_boundary",
        "record_boundary_scope",
        "collect_worker_reports_before_boundary_selection",
        "implement_inside_scope",
        "record_validations",
        "commit_or_record_blocker",
        "run_closeout_check",
    ],
    "closeout_command": "python3 refactor/control/control.py check-closeout",
}


def lifecycle_contract() -> dict[str, object]:
    return json.loads(json.dumps(LIFECYCLE_CONTRACT))


def run_git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout.strip()


def init_repository(root: Path) -> str:
    run_git(root, "init")
    run_git(root, "config", "user.email", "test@example.com")
    run_git(root, "config", "user.name", "Test User")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    run_git(root, "add", "seed.txt")
    run_git(root, "commit", "-m", "seed")
    return run_git(root, "rev-parse", "--short", "HEAD")


def run_control_raw(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CONTROL_PATH), *args],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
    )


def run_control(repository: Path, *args: str) -> str:
    completed = run_control_raw(repository, *args)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout.strip()


def base_state(phase: str = "implementation") -> dict[str, object]:
    return {
        "schema_version": 1,
        "checkpoint_id": "test-checkpoint",
        "objective": "Keep refactor lifecycle closed.",
        "phase": phase,
        "active_boundary": {
            "name": "test boundary",
            "decision": "Exercise lifecycle control.",
            "allowed_files": ["allowed/", "refactor/control/session.local.json"],
            "forbidden_files": ["forbidden/"],
        },
        "required_validations": [],
        "next_action": "Continue.",
        "worker_reports": [
            {
                "worker": "boundary-scout",
                "status": "completed",
                "finding": "Scoped evidence collected.",
            }
        ],
        "lifecycle_contract": lifecycle_contract(),
    }


class RefactorControlTests(unittest.TestCase):
    def test_implementation_rejects_changed_files_outside_allowed_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            (repository / "other.txt").write_text("changed\n", encoding="utf-8")

            with self.assertRaisesRegex(control.ControlError, "outside allowed_files"):
                control.validate_state(base_state(), repository, check_git=True)

    def test_implementation_rejects_forbidden_file_touches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            path = repository / "forbidden" / "item.txt"
            path.parent.mkdir()
            path.write_text("changed\n", encoding="utf-8")

            with self.assertRaisesRegex(control.ControlError, "changed forbidden files"):
                control.validate_state(base_state(), repository, check_git=True)

    def test_implementation_accepts_changed_files_inside_allowed_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            path = repository / "allowed" / "item.txt"
            path.parent.mkdir()
            path.write_text("changed\n", encoding="utf-8")

            result = control.validate_state(base_state(), repository, check_git=True)

            self.assertTrue(result.ok)
            self.assertIn("changed files checked: 1", result.messages)

    def test_closeout_requires_passed_validations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("closeout")
            state["required_validations"] = [{"command": "tests", "status": "pending"}]

            with self.assertRaisesRegex(control.ControlError, "not passed"):
                control.validate_state(state, repository)

    def test_closeout_requires_commit_hash_or_exact_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("closeout")
            state["required_validations"] = [{"command": "tests", "status": "passed"}]

            with self.assertRaisesRegex(control.ControlError, "closeout phase requires commit_hash"):
                control.validate_state(state, repository)

            state["blockers"] = ["git commit failed because index.lock is held by another process"]
            result = control.validate_state(state, repository)
            self.assertTrue(result.ok)

    def test_committed_requires_commit_hash_or_exact_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("committed")
            state["required_validations"] = [{"command": "tests", "status": "passed"}]

            with self.assertRaisesRegex(control.ControlError, "committed phase requires commit_hash"):
                control.validate_state(state, repository)

            state["blockers"] = ["git commit failed because index.lock is held by another process"]
            result = control.validate_state(state, repository)
            self.assertTrue(result.ok)

    def test_committed_commit_hash_must_exist_when_git_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            commit = init_repository(repository)
            state = base_state("committed")
            state["required_validations"] = [{"command": "tests", "status": "passed"}]
            state["commit_hash"] = commit

            result = control.validate_state(state, repository, check_git=True)

            self.assertTrue(result.ok)

            state["commit_hash"] = "deadbee"
            with self.assertRaisesRegex(control.ControlError, "does not exist locally"):
                control.validate_state(state, repository, check_git=True)

    def test_minimal_checkpoint_accepts_single_startup_context_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("discovery")
            state["active_boundary"] = None

            result = control.validate_state(state, repository)

            self.assertTrue(result.ok)
            self.assertIn("state valid: phase=discovery", result.messages)

    def test_tracked_checkpoint_contains_valid_lifecycle_contract(self) -> None:
        checkpoint = json.loads((ROOT / "refactor/control/checkpoint.json").read_text(encoding="utf-8"))

        result = control.validate_state(checkpoint, ROOT)

        self.assertTrue(result.ok)
        self.assertEqual(LIFECYCLE_CONTRACT, checkpoint["lifecycle_contract"])

    def test_validate_state_rejects_missing_lifecycle_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("discovery")
            state["active_boundary"] = None
            del state["lifecycle_contract"]

            with self.assertRaisesRegex(control.ControlError, "lifecycle_contract must be an object"):
                control.validate_state(state, repository)

    def test_validate_state_rejects_startup_context_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("discovery")
            state["active_boundary"] = None
            assert isinstance(state["lifecycle_contract"], dict)
            state["lifecycle_contract"]["startup_context"] = [
                "refactor/control/checkpoint.json",
                "refactor/archive/workers/status.md",
            ]

            with self.assertRaisesRegex(control.ControlError, "startup_context"):
                control.validate_state(state, repository)

    def test_validate_state_rejects_non_orchestrator_role(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("discovery")
            state["active_boundary"] = None
            assert isinstance(state["lifecycle_contract"], dict)
            state["lifecycle_contract"]["role"] = "worker"

            with self.assertRaisesRegex(control.ControlError, "role must be orchestrator"):
                control.validate_state(state, repository)

    def test_validate_state_rejects_missing_required_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("discovery")
            state["active_boundary"] = None
            assert isinstance(state["lifecycle_contract"], dict)
            actions = state["lifecycle_contract"]["required_actions"]
            assert isinstance(actions, list)
            actions.remove("commit_or_record_blocker")

            with self.assertRaisesRegex(control.ControlError, "required_actions"):
                control.validate_state(state, repository)

    def test_validate_state_rejects_bad_closeout_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("discovery")
            state["active_boundary"] = None
            assert isinstance(state["lifecycle_contract"], dict)
            state["lifecycle_contract"]["closeout_command"] = "python3 refactor/control/control.py validate"

            with self.assertRaisesRegex(control.ControlError, "closeout_command"):
                control.validate_state(state, repository)

    def test_decision_requires_worker_reports_before_active_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("decision")
            state["worker_reports"] = []

            with self.assertRaisesRegex(control.ControlError, "worker_reports must contain at least 1"):
                control.validate_state(state, repository)

    def test_blocked_requires_exact_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            state = base_state("blocked")
            state["active_boundary"] = None

            with self.assertRaisesRegex(control.ControlError, "blocked phase requires"):
                control.validate_state(state, repository)

            state["blockers"] = ["waiting for a human decision on behavior change scope"]
            result = control.validate_state(state, repository)
            self.assertTrue(result.ok)

    def test_load_control_state_merges_tracked_checkpoint_and_local_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            checkpoint = repository / "refactor/control" / "checkpoint.json"
            session = repository / "refactor/control" / "session.local.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text(json.dumps(base_state("discovery")), encoding="utf-8")
            session.write_text(json.dumps({
                "checkpoint_id": "test-checkpoint",
                "phase": "closeout",
                "blockers": ["waiting for review"],
            }), encoding="utf-8")

            state = control.load_control_state(repository, checkpoint=checkpoint, session=session)

            self.assertEqual("closeout", state["phase"])
            self.assertEqual(["waiting for review"], state["blockers"])
            self.assertEqual("Keep refactor lifecycle closed.", state["objective"])

    def test_terminal_local_session_does_not_replace_active_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            commit = init_repository(repository)
            checkpoint = repository / "refactor/control" / "checkpoint.json"
            session = repository / "refactor/control" / "session.local.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint_state = base_state("discovery")
            checkpoint_state["active_boundary"] = None
            checkpoint.write_text(json.dumps(checkpoint_state), encoding="utf-8")
            session_state = base_state("committed")
            session_state["required_validations"] = [{"command": "tests", "status": "passed"}]
            session_state["commit_hash"] = commit
            session.write_text(json.dumps({
                key: session_state[key]
                for key in [
                    "checkpoint_id",
                    "phase",
                    "active_boundary",
                    "required_validations",
                    "commit_hash",
                    "next_action",
                ]
            }), encoding="utf-8")

            state = control.load_control_state(
                repository,
                checkpoint=checkpoint,
                session=session,
                include_terminal_session=False,
            )
            status = run_control(repository, "--checkpoint", str(checkpoint), "--session", str(session), "status")

            self.assertEqual("discovery", state["phase"])
            self.assertIsNone(state["active_boundary"])
            self.assertIn("phase: discovery", status)
            self.assertIn("boundary: none", status)
            self.assertIn("last_closeout_phase: committed", status)
            self.assertIn("last_closeout_boundary: test boundary", status)
            self.assertIn(f"last_closeout_commit: {commit}", status)

    def test_load_control_state_rejects_stale_local_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            checkpoint = repository / "refactor/control" / "checkpoint.json"
            session = repository / "refactor/control" / "session.local.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text(json.dumps(base_state("discovery")), encoding="utf-8")
            session.write_text(json.dumps({"checkpoint_id": "old-checkpoint", "phase": "closeout"}), encoding="utf-8")

            with self.assertRaisesRegex(control.ControlError, "was created for checkpoint"):
                control.load_control_state(repository, checkpoint=checkpoint, session=session)

    def test_session_cannot_override_lifecycle_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            checkpoint = repository / "refactor/control" / "checkpoint.json"
            session = repository / "refactor/control" / "session.local.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text(json.dumps(base_state("discovery")), encoding="utf-8")
            session.write_text(json.dumps({
                "checkpoint_id": "test-checkpoint",
                "phase": "discovery",
                "lifecycle_contract": {"role": "worker"},
            }), encoding="utf-8")

            with self.assertRaisesRegex(control.ControlError, "unsupported keys: lifecycle_contract"):
                control.load_control_state(repository, checkpoint=checkpoint, session=session)

    def test_init_creates_local_session_from_tracked_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            checkpoint = repository / "refactor/control" / "checkpoint.json"
            session = repository / "refactor/control" / "session.local.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text(json.dumps(base_state("decision")), encoding="utf-8")

            exit_code = control.main([
                "--checkpoint", str(checkpoint),
                "--session", str(session),
                "init",
            ])

            self.assertEqual(0, exit_code)
            created = json.loads(session.read_text(encoding="utf-8"))
            self.assertEqual("test-checkpoint", created["checkpoint_id"])
            self.assertEqual("decision", created["phase"])
            self.assertEqual("test boundary", created["active_boundary"]["name"])
            self.assertIsNone(created["commit_hash"])

    def test_fresh_checkout_can_init_status_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            checkpoint = repository / "refactor/control" / "checkpoint.json"
            checkpoint.parent.mkdir(parents=True)
            state = base_state("discovery")
            state["active_boundary"] = None
            checkpoint.write_text(json.dumps(state), encoding="utf-8")

            self.assertFalse((repository / "refactor/control" / "session.local.json").exists())
            self.assertIn("created local session", run_control(repository, "init"))
            status = run_control(repository, "status")
            self.assertIn("phase: discovery", status)
            self.assertIn("role: orchestrator", status)
            self.assertIn("closeout_command: python3 refactor/control/control.py check-closeout", status)
            self.assertIn("state valid: phase=discovery", run_control(repository, "validate"))

    def test_check_closeout_rejects_missing_commit_or_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            init_repository(repository)
            checkpoint = repository / "refactor/control" / "checkpoint.json"
            checkpoint.parent.mkdir(parents=True)
            state = base_state("closeout")
            assert isinstance(state["active_boundary"], dict)
            state["active_boundary"]["allowed_files"] = ["refactor/control/"]
            state["required_validations"] = [{"command": "tests", "status": "passed"}]
            checkpoint.write_text(json.dumps(state), encoding="utf-8")

            failed = run_control_raw(repository, "check-closeout")

            self.assertEqual(2, failed.returncode)
            self.assertIn("closeout phase requires commit_hash", failed.stderr)


if __name__ == "__main__":
    unittest.main()
