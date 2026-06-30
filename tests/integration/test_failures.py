from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.config import HarnessConfig
from ai_harness.errors import HarnessError, StateError
from ai_harness.orchestrator import Orchestrator
from ai_harness.stores.artifact import ArtifactStore
from ai_harness.stores.runtime import RunLock
from ai_harness.stores.state import StateStore
from tests.fixtures.flow import run_with_flow
from tests.fixtures.scripted_provider import ScriptedProvider


def write_analysis_artifact(repository: Path, name: str = "jwt-authentication.md") -> str:
    slug = Path(name).stem
    relative = Path("docs") / "explorer" / "improvements" / slug / "improvement.md"
    artifact = repository / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        "# Improvement Analysis v1\n## Problem\nImplement JWT authentication.\n## Context\nRequired by test.\n## Findings\nViable.\n## Options\nImplement.\n## Risks\nNone.\n## Recommendation\nProceed.\n## Outcome\nimprovement\n## Open Questions\nNone.\n",
        encoding="utf-8",
    )
    return str(relative)

class FailureIntegrationTests(unittest.TestCase):
    def test_snapshot_failure_persists_failed_state(self) -> None:
        class FailingSnapshotStore(ArtifactStore):
            def snapshot_run(self, run_id: str, overrides: object = None) -> Path:
                if not run_id.endswith("-failed"):
                    raise OSError("snapshot storage unavailable")
                return super().snapshot_run(run_id)

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifacts = FailingSnapshotStore(repository)
            with self.assertRaises(OSError):
                run_with_flow(
                    Orchestrator(
                        repository,
                        HarnessConfig(provider="local"),
                        ScriptedProvider(),
                        artifacts=artifacts,
                    ),
                    f"Implement {write_analysis_artifact(repository)}",
                    "sdd_high",
                )

            state = StateStore(repository, artifacts).load()
            self.assertNotIn("SNAPSHOTTING", state.completed_phases)
            self.assertNotIn("COMPLETED", state.completed_phases)
            self.assertFalse((artifacts.runs / state.run_id).exists())
            diagnostic = artifacts.runs / f"{state.run_id}-failed"
            self.assertTrue(diagnostic.is_dir())
            archived = json.loads((diagnostic / "state.json").read_text())
            self.assertEqual(state.run_id, archived["run_id"])

    def test_retry_exhaustion_persists_diagnostic_snapshot_and_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ScriptedProvider(implementation_contents=("wrong\n",))
            with self.assertRaises(HarnessError):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local"), provider),
                    f"Implement {write_analysis_artifact(repository)}",
                    "sdd_high",
                )
            state = StateStore(repository).load()
            self.assertEqual("failed", state.status.value)
            self.assertEqual(3, state.tasks[0].attempts)
            self.assertTrue((repository / f".ai-harness/artifacts/runs/{state.run_id}-failed").is_dir())
            with RunLock(repository):
                pass

    def test_corrupt_artifact_is_rejected_before_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            provider = ScriptedProvider(implementation_contents=("wrong\n",))
            with self.assertRaises(HarnessError):
                run_with_flow(
                    Orchestrator(repository, HarnessConfig(provider="local", max_attempts=1), provider),
                    f"Implement {write_analysis_artifact(repository)}",
                    "sdd_high",
                )
            store = StateStore(repository)
            run_id = store.load().run_id
            store.artifacts.write("design.md", "corrupted")
            with self.assertRaises(StateError):
                store.validate_resume(run_id)


if __name__ == "__main__":
    unittest.main()
