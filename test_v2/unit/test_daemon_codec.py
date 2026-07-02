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
from harness_v2.backend.domain.lifecycle import PhaseName
from harness_v2.hosts.daemon.codec import CodecError, decode_command, decode_event, decode_query, decode_result, encode_envelope


class DaemonCodecTests(unittest.TestCase):
    def test_command_round_trip(self) -> None:
        command = StartRun("Fix tests", root_bundle="EXPLORE_BUNDLE")
        self.assertEqual(command, decode_command(encode_envelope(command)))

    def test_query_round_trip(self) -> None:
        query = ListRuns()
        self.assertEqual(query, decode_query(encode_envelope(query)))

    def test_result_round_trips_nested_views_and_events(self) -> None:
        result = CommandResult(
            run=RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE", completed_phases=tuple(phase.value for phase in _explore_phases())),
            events=(RunCompleted("run-1"),),
        )
        self.assertEqual(result, decode_result(encode_envelope(result)))

    def test_query_result_round_trip(self) -> None:
        result = GetRunStateResult("run-1", "RUNNING", "EXPLORE_BUNDLE", "EXPLORE_REQUEST_UNDERSTANDING")
        self.assertEqual(result, decode_result(encode_envelope(result)))

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
            decode_event(encode_envelope(CommandResult(RunView("run-1", "Fix tests", "COMPLETED", "EXPLORE_BUNDLE", completed_phases=tuple(phase.value for phase in _explore_phases())), ())))


def _explore_phases() -> tuple[PhaseName, ...]:
    return (
        PhaseName.EXPLORE_REQUEST_UNDERSTANDING,
        PhaseName.EXPLORE_CONTEXT_PACK,
        PhaseName.EXPLORE_EVIDENCE_DIGEST,
        PhaseName.EXPLORE_EXPLORATION_MAP,
        PhaseName.EXPLORE_OUTCOME_SYNTHESIS,
        PhaseName.EXPLORE_HANDOFF,
    )


if __name__ == "__main__":
    unittest.main()
