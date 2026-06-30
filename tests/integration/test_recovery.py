from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.config import HarnessConfig
from ai_harness.models import Complexity, Mode, PendingDecision, RunState, RunStatus, Strategy
from ai_harness.orchestrator import Orchestrator
from ai_harness.stores.artifact import ArtifactStore
from ai_harness.stores.state import StateStore
from tests.fixtures.flow import run_with_flow
from tests.fixtures.scripted_provider import ScriptedProvider


RUNNER = ROOT / "harness" / "run.py"


def write_analysis_artifact(repository: Path, name: str = "jwt-authentication.md") -> str:
    slug = Path(name).stem
    relative = Path("docs") / "explorer" / "improvements" / slug / "improvement.md"
    artifact = repository / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        "# Improvement Explorer v1\n## Problem\nImplement JWT authentication.\n## Context\nRequired by test.\n## Findings\nViable.\n## Options\nImplement.\n## Risks\nNone.\n## Recommendation\nProceed.\n## Outcome\nimprovement\n## Open Questions\nNone.\n",
        encoding="utf-8",
    )
    return str(relative)


def write_active_state(repository: Path, run_id: str):
    artifacts = ArtifactStore.for_run(repository, run_id)
    StateStore(repository, artifacts).save(
        RunState(
            run_id,
            f"Request for {run_id}",
            "INITIALIZING",
            Strategy.SDD,
            Mode.CODE,
            "modify_code",
            Complexity.LOW,
            "local",
        )
    )
    return artifacts


def write_waiting_state(repository: Path, run_id: str):
    artifacts = ArtifactStore.for_run(repository, run_id)
    artifacts.write_json("decisions/D0001/request.json", {
        "schema_version": 1,
        "decision_id": "D0001",
        "origin_phase": "SELECTING_STRATEGY",
        "target_phase": "EXPLORE",
        "question": "Which path?",
        "options": [],
        "context": [],
    })
    StateStore(repository, artifacts).save(
        RunState(
            run_id,
            f"Request for {run_id}",
            "EXPLORE",
            Strategy.SDD,
            Mode.CODE,
            "modify_code",
            Complexity.MEDIUM,
            "local",
            status=RunStatus.WAITING_FOR_USER,
            pending_decision=PendingDecision("D0001", "SELECTING_STRATEGY", "EXPLORE", "decisions/D0001/request.json"),
        )
    )
    return artifacts


def write_terminal_live_state(repository: Path, run_id: str):
    artifacts = ArtifactStore.for_run(repository, run_id)
    StateStore(repository, artifacts).save(
        RunState(
            run_id,
            f"Request for {run_id}",
            "COMPLETED",
            Strategy.SDD,
            Mode.CODE,
            "modify_code",
            Complexity.LOW,
            "local",
            completed_phases=["INITIALIZING", "COMPLETED"],
            status=RunStatus.COMPLETED,
        )
    )
    return artifacts

class InterruptOnExplore:
    def __init__(self) -> None:
        self.delegate = ScriptedProvider()

    def run_prompt(self, prompt: str, *, cwd: Path, permissions=None, progress=None):
        if "# Explore Request Understanding Worker v1" in prompt:
            raise KeyboardInterrupt("simulated process interruption")
        return self.delegate.run_prompt(prompt, cwd=cwd, permissions=permissions, progress=progress)


class RecoveryIntegrationTests(unittest.TestCase):
    def _interrupt(self, repository: Path, request: str):
        orchestrator = Orchestrator(
            repository,
            HarnessConfig(provider="local"),
            InterruptOnExplore(),
        )
        with self.assertRaises(KeyboardInterrupt):
            run_with_flow(orchestrator, request, "sdd_high")
        return StateStore(repository).load()

    def test_interrupted_active_run_resumes_with_a_fresh_orchestrator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            request = f"Implement {write_analysis_artifact(repository)}"
            interrupted = self._interrupt(repository, request)
            self.assertEqual("active", interrupted.status.value)
            self.assertEqual("EXPLORE", interrupted.current_phase)

            result = Orchestrator(
                repository, HarnessConfig(provider="local"), ScriptedProvider()
            ).run(request, resume_run_id=interrupted.run_id)
            self.assertEqual(interrupted.run_id, result.run_id)
            self.assertEqual("success", result.outcome)
            self.assertTrue(result.snapshot_path.is_dir())


    def test_status_reports_no_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--status"],
                input="ignored",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("Status: no run", completed.stdout)

    def test_status_reports_active_waiting_and_latest_job_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            active = write_active_state(repository, "run-a")
            active.write_json("jobs/J0001/request.json", {"job_id": "J0001", "temp_dir": str(repository / ".ai-harness/tmp/run-a/implement/J0001")})
            active.write_json("jobs/J0001/result.json", {"job_id": "J0001", "exit_code": 0})
            waiting = write_waiting_state(repository, "run-b")

            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--status"],
                input="ignored",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("Run ID: run-a", completed.stdout)
            self.assertIn("Status: active", completed.stdout)
            self.assertIn("Strategy: SDD", completed.stdout)
            self.assertIn("Current phase: INITIALIZING", completed.stdout)
            self.assertIn("Selected provider: local", completed.stdout)
            self.assertIn(f"Artifact dir: {active.current}", completed.stdout)
            self.assertIn("Latest job: J0001", completed.stdout)
            self.assertIn("Job request:", completed.stdout)
            self.assertIn("Job result:", completed.stdout)
            self.assertIn("Job temp dir:", completed.stdout)
            self.assertIn("Run ID: run-b", completed.stdout)
            self.assertIn("Status: waiting_for_user", completed.stdout)
            self.assertIn("Pending decision ID: D0001", completed.stdout)
            self.assertIn(f"Artifact dir: {waiting.current}", completed.stdout)
            self.assertIn("--resume run-a", completed.stdout)
            self.assertIn("--archive run-b", completed.stdout)

    def test_status_is_read_only_and_does_not_cleanup_terminal_live_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            terminal = write_terminal_live_state(repository, "done")
            state_path = terminal.current / "state.json"
            before = state_path.read_bytes()

            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--status"],
                input="ignored",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("Run ID: done", completed.stdout)
            self.assertIn("Status: completed", completed.stdout)
            self.assertTrue(state_path.is_file())
            self.assertEqual(before, state_path.read_bytes())

    def test_launcher_reports_unfinished_run_without_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            interrupted = self._interrupt(
                repository,
                f"Implement {write_analysis_artifact(repository)}",
            )
            state_path = repository / ".ai-harness/artifacts/current/state.json"
            before = state_path.read_bytes()

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(RUNNER),
                    "--cwd",
                    directory,
                    "--provider",
                    "local",
                ],
                input="Start an unrelated request",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(3, completed.returncode)
            self.assertIn(f"unfinished run {interrupted.run_id}", completed.stderr)
            self.assertIn(f"--resume {interrupted.run_id}", completed.stderr)
            self.assertIn(f"--archive {interrupted.run_id}", completed.stderr)
            self.assertEqual(before, state_path.read_bytes())

    def test_launcher_archives_unfinished_run_and_clears_current_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            interrupted = self._interrupt(
                repository,
                f"Implement {write_analysis_artifact(repository)}",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(RUNNER),
                    "--cwd",
                    directory,
                    "--archive",
                    interrupted.run_id,
                ],
                input="",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            snapshot = (
                repository
                / ".ai-harness"
                / "artifacts"
                / "runs"
                / interrupted.run_id
            )
            self.assertTrue((snapshot / "state.json").is_file())
            self.assertTrue((snapshot / "archive.json").is_file())
            current = repository / ".ai-harness/artifacts/current"
            self.assertFalse(current.exists())

    def test_launcher_rejects_wrong_archive_run_id_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            interrupted = self._interrupt(
                repository,
                f"Implement {write_analysis_artifact(repository)}",
            )
            state_path = repository / ".ai-harness/artifacts/current/state.json"
            before = state_path.read_bytes()

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(RUNNER),
                    "--cwd",
                    directory,
                    "--archive",
                    "wrong",
                ],
                input="",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(1, completed.returncode)
            self.assertIn(
                "archive run ID does not match persisted state",
                completed.stderr,
            )
            self.assertEqual(interrupted.run_id, StateStore(repository).load().run_id)
            self.assertEqual(before, state_path.read_bytes())

    def test_show_runs_prints_compact_rows_and_action_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            active = write_active_state(repository, "run-a")

            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--show-runs"],
                input="",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("[", completed.stdout)
            self.assertIn("][active]: Request for run-a", completed.stdout)
            self.assertIn("id: run-a", completed.stdout)
            self.assertIn(str(active.current), completed.stdout)
            self.assertIn("resume:", completed.stdout)
            self.assertIn("--resume run-a", completed.stdout)
            self.assertIn("archive:", completed.stdout)
            self.assertIn("--archive run-a", completed.stdout)

    def test_archive_requested_run_when_multiple_unfinished_runs_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            first = write_active_state(repository, "run-a")
            second = write_active_state(repository, "run-b")

            completed = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--cwd", directory, "--archive", "run-a"],
                input="",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertFalse(first.current.exists())
            self.assertTrue(second.current.exists())
            self.assertTrue((repository / ".ai-harness/artifacts/runs/run-a/archive.json").is_file())


if __name__ == "__main__":
    unittest.main()
