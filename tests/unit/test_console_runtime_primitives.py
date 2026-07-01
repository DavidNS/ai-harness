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
    def test_console_update_maps_lines_to_effects_without_slash_mode(self) -> None:
        from harness.cli.console.model import ConsoleActionSpec, ConsoleModel
        from harness.cli.console.messages import SubmitLine
        from harness.cli.console.update import update

        model = ConsoleModel(actions=(ConsoleActionSpec("status", "Show status", "s"),))
        _, status_effects = update(model, SubmitLine("status"))
        menu_model, menu_effects = update(model, SubmitLine(""))
        _, request_effects = update(model, SubmitLine("/status"))
        start_model = ConsoleModel(actions=(ConsoleActionSpec("start", "Start", "n"),))
        _, start_effects = update(start_model, SubmitLine("start Fix   tests"))

        self.assertEqual("dispatch_action", status_effects[0].kind)
        self.assertEqual("status", status_effects[0].value)
        self.assertEqual("menu", menu_model.screen)
        self.assertEqual("open_menu", menu_effects[0].kind)
        self.assertEqual("start_request", request_effects[0].kind)
        self.assertEqual("/status", request_effects[0].value)
        self.assertEqual("dispatch_action", start_effects[0].kind)
        self.assertEqual(("Fix", "tests"), start_effects[0].args)
        self.assertEqual("Fix   tests", start_effects[0].raw_tail)

    def test_console_menu_selection_flows_through_select_action(self) -> None:
        from harness.cli.console.model import ConsoleActionSpec, ConsoleModel
        from harness.cli.console.terminal_driver import ConsoleTerminalDriver
        from harness.cli.ui_primitives import _MenuItem

        class Backend:
            def __init__(self) -> None:
                self.calls = []

            def status(self) -> int:
                return 0

            def runs(self) -> int:
                return 0

            def start_request(self, request: str) -> int:
                self.calls.append(("start_request", request))
                return 0

            def dispatch_action(self, command: str, args: tuple[str, ...], raw_tail: str = "") -> int:
                self.calls.append(("dispatch_action", command, args, raw_tail))
                return 7

        backend = Backend()
        seen_titles = []
        seen_items = []

        def choose(title_lines, items, **_kwargs):
            seen_titles.extend(title_lines)
            seen_items.extend(items)
            return _MenuItem("s", "Show status", "status", ("status",))

        driver = ConsoleTerminalDriver(
            ConsoleModel(actions=(ConsoleActionSpec("status", "Show status", "s"),)),
            backend,
            line_reader=lambda: None,
            menu_prompt=choose,
            launcher_exit=RuntimeError,
        )

        self.assertEqual(7, driver.run_once(""))
        self.assertEqual(["Console actions"], seen_titles)
        self.assertEqual(["status"], [item.value for item in seen_items])
        self.assertEqual([("dispatch_action", "status", (), "")], backend.calls)

    def test_console_view_builds_menu_items_from_model(self) -> None:
        from harness.cli.console.model import ConsoleActionSpec, ConsoleModel
        from harness.cli.console.view import menu_items, menu_title_lines, render_lines

        model = ConsoleModel(actions=(
            ConsoleActionSpec("status", "Show status", "s"),
            ConsoleActionSpec("hidden", "Hidden", "h", menu_visible=False),
        ))

        self.assertEqual(["Console actions"], menu_title_lines(model))
        self.assertEqual(["status"], [item.value for item in menu_items(model)])
        self.assertIn("aihui> ", render_lines(model))


    def test_console_action_plan_parses_resume_answers(self) -> None:
        from harness.cli.console.action_plan import plan_action

        answer_plan = plan_action("resume", ("run-1", "--answer", "Use this"))
        option_plan = plan_action("resume", ("run-1", "--selected-option", "keep"))
        invalid_plan = plan_action("resume", ("run-1", "--answer", "x", "--selected-option", "keep"))

        self.assertIsNotNone(answer_plan)
        self.assertEqual("resume", answer_plan.kind)
        self.assertEqual("run-1", answer_plan.target)
        self.assertEqual("Use this", answer_plan.answer)
        self.assertIsNotNone(option_plan)
        self.assertEqual("keep", option_plan.selected_option)
        self.assertIsNotNone(invalid_plan)
        self.assertEqual("error", invalid_plan.kind)

    def test_legacy_console_action_wrapper_does_not_treat_command_name_as_tail(self) -> None:
        from harness.cli.console_app import _legacy_raw_tail

        self.assertEqual("", _legacy_raw_tail("start", [], "start"))
        self.assertEqual("Fix   tests", _legacy_raw_tail("start", ["Fix", "tests"], "start Fix   tests"))

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
