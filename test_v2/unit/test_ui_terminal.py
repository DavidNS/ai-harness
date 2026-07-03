from __future__ import annotations

import unittest
from unittest import mock

from harness_v2.frontends.ui.terminal import KeyReader, _strip_ansi


class KeyReaderTests(unittest.TestCase):
    def test_maps_common_csi_keys_without_leaking_bytes(self) -> None:
        reader = KeyReader()
        with mock.patch.object(reader, "_read_byte", side_effect=[b"\x1b", b"[", b"3", b"~"]):
            self.assertEqual("delete", reader.read_key())

        reader = KeyReader()
        with mock.patch.object(reader, "_read_byte", side_effect=[b"\x1b", b"[", b"D"]):
            self.assertEqual("left", reader.read_key())

    def test_maps_arrow_keys(self) -> None:
        for final, expected in (("A", "up"), ("B", "down"), ("C", "right")):
            reader = KeyReader()
            with mock.patch.object(reader, "_read_byte", side_effect=[b"\x1b", b"[", final.encode()]):
                self.assertEqual(expected, reader.read_key())

    def test_bare_escape_returns_escape(self) -> None:
        reader = KeyReader()
        with mock.patch.object(reader, "_read_byte", side_effect=[b"\x1b", b""]):
            self.assertEqual("escape", reader.read_key())

    def test_ctrl_c_raises_keyboard_interrupt(self) -> None:
        reader = KeyReader()
        with mock.patch.object(reader, "_read_byte", side_effect=[b"\x03"]):
            with self.assertRaises(KeyboardInterrupt):
                reader.read_key()

    def test_decodes_utf8_character(self) -> None:
        reader = KeyReader()
        encoded = "ñ".encode("utf-8")
        with mock.patch.object(reader, "_read_byte", side_effect=[bytes([encoded[0]]), bytes([encoded[1]])]):
            self.assertEqual("ñ", reader.read_key())


class StripAnsiTests(unittest.TestCase):
    def test_removes_csi_sequences(self) -> None:
        self.assertEqual("hello", _strip_ansi("\x1b[2Khe\x1b[1mllo"))

    def test_plain_text_unchanged(self) -> None:
        self.assertEqual("plain", _strip_ansi("plain"))


if __name__ == "__main__":
    unittest.main()
