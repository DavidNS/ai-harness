from __future__ import annotations

import hashlib
import unittest

from harness_v2.adapters.storage import InMemoryArtifactStore, InMemoryStateStore
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactNotFoundError
from harness_v2.backend.ports.state_store import StateNotFoundError


def completed_run(run_id: str = "run-1") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        request="Fix tests",
        status=RunStatus.COMPLETED,
        strategy=RunStrategy.EXPLORE_BUNDLE,
        completed_phases=(PhaseName.EXPLORE_BUNDLE,),
    )


def running_run(run_id: str = "run-2") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        request="Fix tests",
        status=RunStatus.RUNNING,
        strategy=RunStrategy.SDD,
        current_phase=PhaseName.EXPLORE_BUNDLE,
    )


class InMemoryStateStoreTests(unittest.TestCase):
    def test_save_get_and_list_indexes_preserve_authoritative_state(self) -> None:
        store = InMemoryStateStore()
        active = running_run()
        completed = completed_run()

        store.save(completed)
        store.save(active)

        self.assertEqual(active, store.get("run-2"))
        self.assertEqual(["run-1", "run-2"], [run.run_id for run in store.list_all()])
        self.assertEqual(["run-2"], [run.run_id for run in store.list_active()])
        self.assertEqual(["run-1"], [run.run_id for run in store.list_completed()])

    def test_get_missing_state_fails_closed(self) -> None:
        with self.assertRaises(StateNotFoundError):
            InMemoryStateStore().get("missing")


class InMemoryArtifactStoreTests(unittest.TestCase):
    def test_write_read_list_checksum_and_manifest(self) -> None:
        store = InMemoryArtifactStore()
        content = b"artifact bytes"

        metadata = store.write("run-1", "reports/output.txt", content)

        self.assertEqual(content, store.read("run-1", "reports/output.txt"))
        self.assertEqual(hashlib.sha256(content).hexdigest(), metadata.checksum)
        self.assertEqual(metadata.checksum, store.checksum("run-1", "reports/output.txt"))
        self.assertEqual((metadata,), store.list("run-1"))
        self.assertEqual((metadata,), store.manifest("run-1").artifacts)

    def test_missing_artifact_and_unsafe_artifact_ids_fail_closed(self) -> None:
        store = InMemoryArtifactStore()

        with self.assertRaises(ArtifactNotFoundError):
            store.read("run-1", "missing.txt")
        for artifact_id in ("", ".", "/absolute", "../escape", "nested/./current", "nested//empty"):
            with self.subTest(artifact_id=artifact_id):
                with self.assertRaises(ValueError):
                    store.write("run-1", artifact_id, b"content")


if __name__ == "__main__":
    unittest.main()
