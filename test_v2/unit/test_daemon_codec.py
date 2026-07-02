from __future__ import annotations

import unittest

from harness_v2.backend.application.contracts import (
    CommandResult,
    GetAvailableActions,
    GetRunStateResult,
    ListRuns,
    RunCompleted,
    RunView,
    StartRun,
)
from harness_v2.hosts.daemon.codec import (
    CodecError,
    decode_command,
    decode_event,
    decode_query,
    decode_result,
    encode_envelope,
)


class DaemonCodecTests(unittest.TestCase):
    def test_command_round_trip(self) -> None:
        command = StartRun("Fix tests", strategy="EXPLORER")

        decoded = decode_command(encode_envelope(command))

        self.assertEqual(command, decoded)

    def test_query_round_trip(self) -> None:
        query = ListRuns()

        decoded = decode_query(encode_envelope(query))

        self.assertEqual(query, decoded)

    def test_result_round_trips_nested_views_and_events(self) -> None:
        result = CommandResult(
            run=RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE", completed_phases=("EXPLORE_BUNDLE",)),
            events=(RunCompleted("run-1"),),
        )

        decoded = decode_result(encode_envelope(result))

        self.assertEqual(result, decoded)

    def test_query_result_round_trip(self) -> None:
        result = GetRunStateResult("run-1", "RUNNING", "EXPLORE_BUNDLE")

        decoded = decode_result(encode_envelope(result))

        self.assertEqual(result, decoded)

    def test_rejects_unknown_type(self) -> None:
        with self.assertRaises(CodecError):
            decode_command({"type": "NotACommand", "payload": {}})

    def test_rejects_unexpected_payload_fields(self) -> None:
        with self.assertRaises(CodecError):
            decode_query({"type": "GetAvailableActions", "payload": {"run_id": "run-1", "extra": "bad"}})

    def test_rejects_wrong_boundary_type(self) -> None:
        with self.assertRaises(CodecError):
            decode_command(encode_envelope(GetAvailableActions("run-1")))
        with self.assertRaises(CodecError):
            decode_result(encode_envelope(StartRun("Fix tests")))
        with self.assertRaises(CodecError):
            decode_event(encode_envelope(CommandResult(RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE"), ())))


if __name__ == "__main__":
    unittest.main()
