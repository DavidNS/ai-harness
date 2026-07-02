from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness_v2.adapters.storage import FileStateStore
from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.lifecycle import BundleName, RunStatus
from harness_v2.backend.domain.runs import RunRecord


class FileStorageIntegrationTests(unittest.TestCase):
    def test_file_state_store_round_trips_root_bundle_and_completed_phases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = FileStateStore(Path(directory))
            run = RunRecord("run-1", "Fix tests", RunStatus.COMPLETED, root_bundle=BundleName.EXPLORE_BUNDLE, completed_phases=bundle_catalog.phases(BundleName.EXPLORE_BUNDLE))

            store.save(run)

            self.assertEqual(run, store.get("run-1"))
            self.assertEqual(["run-1"], [item.run_id for item in store.list_completed()])


if __name__ == "__main__":
    unittest.main()
