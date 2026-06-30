from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))


class ConsoleRuntimePrimitiveTests(unittest.TestCase):
    def test_request_context_requires_slash_for_model_command(self) -> None:
        from harness.cli.console_actions import parse_console_line

        bare = parse_console_line("model", context="request")
        slash = parse_console_line("/model", context="request")

        self.assertEqual("request", bare.kind)
        self.assertEqual("model", bare.request)
        self.assertEqual("action", slash.kind)
        self.assertEqual("model", slash.action.name if slash.action else None)

    def test_key_reader_maps_common_csi_keys_without_leaking_bytes(self) -> None:
        from harness.cli.terminal import KeyReader

        reader = KeyReader()
        with mock.patch.object(reader, "_read_byte", side_effect=[b"\x1b", b"[", b"3", b"~"]):
            self.assertEqual("delete", reader.read_key())

        reader = KeyReader()
        with mock.patch.object(reader, "_read_byte", side_effect=[b"\x1b", b"[", b"D"]):
            self.assertEqual("left", reader.read_key())

    def test_key_reader_decodes_utf8_character(self) -> None:
        from harness.cli.terminal import KeyReader

        reader = KeyReader()
        encoded = "ñ".encode("utf-8")
        with mock.patch.object(reader, "_read_byte", side_effect=[bytes([encoded[0]]), bytes([encoded[1]])]):
            self.assertEqual("ñ", reader.read_key())

    def test_job_store_round_trips_metadata_and_events(self) -> None:
        from harness.cli.job_runner import JobHandle, JobStore

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            store = JobStore(repository)
            handle = JobHandle("job-1", ["python", "run.py"], store.job_root("job-1"), store.events_path("job-1"), pid=123)

            store.write_metadata(handle)
            store.append_event("job-1", {"type": "started"})
            offset, events = store.read_events("job-1")

            self.assertGreater(offset, 0)
            self.assertEqual("job-1", store.read_metadata("job-1")["job_id"])
            self.assertEqual(["job-1"], [item["job_id"] for item in store.list_jobs()])
            self.assertEqual("started", events[0]["type"])


if __name__ == "__main__":
    unittest.main()
