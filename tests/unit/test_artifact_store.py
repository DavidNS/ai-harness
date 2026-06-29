import json
from pathlib import Path
import tempfile
import unittest
from ai_harness.errors import ArtifactError
from ai_harness.stores.artifact import ArtifactStore, cleanup_terminal_live_artifacts, discover_live_artifacts
from ai_harness.stores.live_registry import LiveRunRegistry


class ArtifactStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ArtifactStore(Path(self.temp.name))

    def tearDown(self): self.temp.cleanup()

    def test_stable_json_and_snapshot(self):
        self.store.write_json("nested/a.json", {"z": 1, "a": 2})
        self.assertEqual(self.store.read("nested/a.json"), '{\n  "a": 2,\n  "z": 1\n}\n')
        self.assertTrue((self.store.snapshot_run("run-1") / "nested/a.json").is_file())
        with self.assertRaises(ArtifactError): self.store.snapshot_run("run-1")

    def test_rejects_absolute_traversal_and_symlink_escape(self):
        for name in ("/tmp/x", "../x"):
            with self.assertRaises(ArtifactError): self.store.write(name, "x")
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.store.current / "link").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ArtifactError): self.store.write("link/x", "x")

    def test_run_scoped_store_publishes_active_pointer_and_compatibility_link(self):
        root = Path(self.temp.name)
        self.store.current.rmdir()
        store = ArtifactStore.for_run(root, "run-2")
        store.write("state.json", "{}")
        self.assertEqual("current-run-2", store.current.name)
        self.assertEqual(store.current.resolve(), (root / ".ai-harness/artifacts/current").resolve())
        active = json.loads((root / ".ai-harness/artifacts/active.json").read_text(encoding="utf-8"))
        self.assertEqual({"schema_version": 1, "run_id": "run-2", "current": "current-run-2"}, active)
        discovered = discover_live_artifacts(root)
        self.assertEqual([store.current.resolve()], [item.current.resolve() for item in discovered])

    def test_snapshot_can_filter_to_recorded_artifacts(self):
        self.store.write("recorded.txt", "keep")
        self.store.write("stale.txt", "drop")
        snapshot = self.store.snapshot_run("run-3", artifact_names=["recorded.txt"])
        self.assertTrue((snapshot / "recorded.txt").is_file())
        self.assertFalse((snapshot / "stale.txt").exists())

    def test_live_registry_tracks_and_closes_run_scoped_store(self):
        root = Path(self.temp.name)
        self.store.current.rmdir()
        store = ArtifactStore.for_run(root, "run-4")
        entry = LiveRunRegistry(root).get("run-4")
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual("active", entry.status)
        self.assertEqual(str(store.current.resolve()), entry.current_dir)

        store.clear_live("run-4", "archived")

        closed = LiveRunRegistry(root).get("run-4")
        self.assertIsNotNone(closed)
        assert closed is not None
        self.assertEqual("archived", closed.status)
        self.assertFalse(store.current.exists())
        self.assertFalse((root / ".ai-harness/artifacts/current").exists())

    def test_startup_cleanup_removes_terminal_live_dirs_only(self):
        root = Path(self.temp.name)
        self.store.current.rmdir()
        completed = ArtifactStore.for_run(root, "done")
        completed.write_json("state.json", {"run_id": "done", "status": "completed"})
        active = ArtifactStore.for_run(root, "open")
        active.write_json("state.json", {"run_id": "open", "status": "active"})

        diagnostics = cleanup_terminal_live_artifacts(root)

        self.assertEqual([], diagnostics)
        self.assertFalse(completed.current.exists())
        self.assertTrue(active.current.exists())
