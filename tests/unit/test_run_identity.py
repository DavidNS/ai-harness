import re
import unittest
from datetime import datetime, timezone
from unittest import mock

from ai_harness.run_identity import new_run_id, run_id_date, run_id_token


class RunIdentityTests(unittest.TestCase):
    def test_new_run_id_is_timestamped_and_has_random_suffix(self) -> None:
        with mock.patch("ai_harness.run_identity.uuid.uuid4") as uuid4:
            uuid4.return_value.hex = "abcdef1234567890"
            run_id = new_run_id(datetime(2026, 6, 30, 12, 34, 56, tzinfo=timezone.utc))

        self.assertEqual("20260630T123456Z-abcdef123456", run_id)
        self.assertRegex(run_id, re.compile(r"^\d{8}T\d{6}Z-[a-f0-9]{12}$"))
        self.assertEqual("20260630", run_id_date(run_id))
        self.assertEqual("abcdef123456", run_id_token(run_id))

    def test_legacy_run_ids_remain_branch_name_compatible(self) -> None:
        self.assertEqual("legacy", run_id_date("abcdef123456"))
        self.assertEqual("abcdef123456", run_id_token("abcdef1234567890"))


if __name__ == "__main__":
    unittest.main()
