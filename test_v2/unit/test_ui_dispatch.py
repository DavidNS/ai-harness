from __future__ import annotations

import unittest

from harness_v2.frontends.ui import messages as m
from harness_v2.frontends.ui.dispatch import COMMAND_HELP, CommandError, parse_command


class ParseCommandTests(unittest.TestCase):
    def test_bare_commands_open_guided_screens(self) -> None:
        self.assertEqual(m.Navigate("runs"), parse_command("/select"))
        self.assertEqual(m.Navigate("start-bundle"), parse_command("/start"))
        self.assertEqual(m.Navigate("retry-mode"), parse_command("/retry"))
        self.assertEqual(m.Navigate("decision-options"), parse_command("/decision"))

    def test_commands_with_args_invoke_directly(self) -> None:
        self.assertEqual(m.Invoke("select", ("run-42",)), parse_command("/select run-42"))
        self.assertEqual(
            m.Invoke("start", ("SDD_BUNDLE", "fix the broken UI")),
            parse_command("/start SDD_BUNDLE fix the broken UI"),
        )
        self.assertEqual(
            m.Invoke("retry-step", ("SDD_BUNDLE:020",)),
            parse_command("/retry SDD_BUNDLE:020"),
        )
        self.assertEqual(m.Invoke("decision", ("continue with SDD",)), parse_command("/decision continue with SDD"))

    def test_operational_shortcuts_map_to_effect_commands(self) -> None:
        self.assertEqual(m.Invoke("refresh"), parse_command("/refresh"))
        self.assertEqual(m.Invoke("refresh"), parse_command("/list"))
        self.assertEqual(m.Invoke("watch", ("5",)), parse_command("/watch 5"))
        self.assertEqual(m.Invoke("resume"), parse_command("/resume"))
        self.assertEqual(m.Invoke("cancel"), parse_command("/cancel"))

    def test_retry_bundle_has_explicit_direct_command(self) -> None:
        self.assertEqual(m.Invoke("retry-bundle", ("EXPLORE_BUNDLE",)), parse_command("/retry-bundle EXPLORE_BUNDLE"))

    def test_quit_aliases_and_help(self) -> None:
        self.assertEqual(m.Quit(), parse_command("/quit"))
        self.assertEqual(m.Quit(), parse_command("/exit"))
        self.assertIsNone(parse_command("/help"))
        self.assertIsNone(parse_command("/"))

    def test_shell_quoting_preserves_multi_word_values(self) -> None:
        self.assertEqual(
            m.Invoke("start", ("SDD_BUNDLE", "fix quoted request")),
            parse_command('/start SDD_BUNDLE "fix quoted request"'),
        )

    def test_bad_syntax_and_unknown_commands_are_user_facing_errors(self) -> None:
        with self.assertRaisesRegex(CommandError, "No closing quotation"):
            parse_command('/start SDD_BUNDLE "unfinished')
        with self.assertRaises(CommandError) as captured:
            parse_command("/bogus")
        self.assertEqual(COMMAND_HELP, str(captured.exception))


if __name__ == "__main__":
    unittest.main()
