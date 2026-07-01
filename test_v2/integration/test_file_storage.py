from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from harness_v2.adapters.storage import FileArtifactStore, FileStateStore
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactNotFoundError, ArtifactStoreError
from harness_v2.backend.ports.state_store import StateNotFoundError, StateStoreCorruptionError


def completed_run(run_id: str = "run-1") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        request="Fix tests",
        status=RunStatus.COMPLETED,
        strategy=RunStrategy.EXPLORE_BUNDLE,
        completed_phases=(PhaseName.EXPLORE_BUNDLE,),
        events=("transient",),
    )


def running_run(run_id: str = "run-2") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        request="Fix tests",
        status=RunStatus.RUNNING,
        strategy=RunStrategy.SDD,
        current_phase=PhaseName.EXPLORE_BUNDLE,
    )


class FileStateStoreIntegrationTests(unittest.TestCase):
    def test_file_state_round_trips_valid_runs_and_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = FileStateStore(Path(temp))
            store.save(completed_run("run-1"))
            store.save(running_run("run-2"))

            loaded = store.get("run-1")

            self.assertEqual(RunStatus.COMPLETED, loaded.status)
            self.assertEqual((), loaded.events)
            self.assertEqual(["run-1", "run-2"], [run.run_id for run in store.list_all()])
            self.assertEqual(["run-2"], [run.run_id for run in store.list_active()])
            self.assertEqual(["run-1"], [run.run_id for run in store.list_completed()])

    def test_missing_and_malformed_state_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileStateStore(root)

            with self.assertRaises(StateNotFoundError):
                store.get("missing")

            malformed = root / "runs" / "bad-json" / "state.json"
            malformed.parent.mkdir(parents=True)
            malformed.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(StateStoreCorruptionError):
                store.get("bad-json")

    def test_unknown_status_or_phase_fails_closed(self) -> None:
        base = {
            "schema_version": 1,
            "run": {
                "run_id": "bad-enum",
                "request": "Fix tests",
                "status": "RUNNING",
                "strategy": "SDD",
                "current_phase": "EXPLORE_BUNDLE",
                "completed_phases": [],
                "pending_decision": None,
                "tasks": [],
                "errors": [],
            },
        }
        cases = (
            ("bad-status", {"status": "UNKNOWN"}),
            ("bad-phase", {"current_phase": "UNKNOWN"}),
        )
        for run_id, overrides in cases:
            with self.subTest(run_id=run_id), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                payload = json.loads(json.dumps(base))
                payload["run"].update({"run_id": run_id, **overrides})
                path = root / "runs" / run_id / "state.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(payload), encoding="utf-8")

                with self.assertRaises(StateStoreCorruptionError):
                    FileStateStore(root).get(run_id)

    def test_domain_invalid_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "runs" / "bad-domain" / "state.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run": {
                            "run_id": "bad-domain",
                            "request": "Fix tests",
                            "status": "RUNNING",
                            "strategy": "SDD",
                            "current_phase": "EXPLORE_BUNDLE",
                            "completed_phases": ["EXPLORE_BUNDLE"],
                            "pending_decision": None,
                            "tasks": [],
                            "errors": [],
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(StateStoreCorruptionError):
                FileStateStore(root).get("bad-domain")

    def test_save_replaces_state_without_leaving_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileStateStore(root)

            store.save(running_run("run-1"))
            store.save(completed_run("run-1"))

            self.assertEqual(RunStatus.COMPLETED, store.get("run-1").status)
            state_dir = root / "runs" / "run-1"
            self.assertEqual([], list(state_dir.glob(".state.json.*.tmp")))


class FileArtifactStoreIntegrationTests(unittest.TestCase):
    def test_file_artifacts_preserve_bytes_and_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = FileArtifactStore(Path(temp))
            content = b"artifact bytes"

            metadata = store.write("run-1", "reports/output.txt", content)

            self.assertEqual(content, store.read("run-1", "reports/output.txt"))
            self.assertEqual(hashlib.sha256(content).hexdigest(), metadata.checksum)
            self.assertEqual(metadata.checksum, store.checksum("run-1", "reports/output.txt"))
            self.assertEqual((metadata,), store.list("run-1"))
            self.assertEqual((metadata,), store.manifest("run-1").artifacts)

    def test_missing_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ArtifactNotFoundError):
                FileArtifactStore(Path(temp)).read("run-1", "missing.txt")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_artifact_final_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileArtifactStore(root)
            artifacts = root / "runs" / "run-1" / "artifacts"
            artifacts.mkdir(parents=True)
            escaped = root / "escaped.txt"
            (artifacts / "link.txt").symlink_to(escaped)

            with self.assertRaises(ArtifactStoreError):
                store.write("run-1", "link.txt", b"escaped")
            with self.assertRaises(ArtifactStoreError):
                store.read("run-1", "link.txt")
            with self.assertRaises(ArtifactStoreError):
                store.list("run-1")
            with self.assertRaises(ArtifactStoreError):
                store.manifest("run-1")
            self.assertFalse(escaped.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_artifact_intermediate_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = FileArtifactStore(root)
            artifacts = root / "runs" / "run-1" / "artifacts"
            artifacts.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_bytes(b"secret")
            (artifacts / "linked").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(ArtifactStoreError):
                store.write("run-1", "linked/new.txt", b"escaped")
            with self.assertRaises(ArtifactStoreError):
                store.read("run-1", "linked/secret.txt")
            with self.assertRaises(ArtifactStoreError):
                store.list("run-1")
            with self.assertRaises(ArtifactStoreError):
                store.manifest("run-1")
            self.assertFalse((outside / "new.txt").exists())


if __name__ == "__main__":
    unittest.main()
