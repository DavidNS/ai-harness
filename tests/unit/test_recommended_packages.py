from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.recommended_packages import (
    install_recommended_packages,
    load_recommended_package_groups,
    pip_packages,
    render_package_install_result,
    selected_package_groups,
)


class RecommendedPackagesTests(unittest.TestCase):
    def test_loads_required_and_optional_groups(self) -> None:
        groups = load_recommended_package_groups()

        self.assertIn("quality-core", [group.id for group in groups])
        self.assertIn("security", [group.id for group in groups])
        self.assertTrue(next(group for group in groups if group.id == "quality-core").required)

    def test_selection_always_includes_required_groups(self) -> None:
        groups = load_recommended_package_groups()
        selected = selected_package_groups(groups, ["security"])

        self.assertEqual(["quality-core", "security"], [group.id for group in selected])
        self.assertEqual(("ruff", "mypy", "pytest", "semgrep"), pip_packages(selected))

    def test_unknown_optional_group_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown package group"):
            selected_package_groups(load_recommended_package_groups(), ["wat"])

    def test_dry_run_does_not_call_pip(self) -> None:
        runner = mock.Mock()

        result = install_recommended_packages(["security"], dry_run=True, runner=runner)

        runner.assert_not_called()
        self.assertTrue(result.dry_run)
        self.assertIn("semgrep", result.pip_packages)
        self.assertIn("Would run", render_package_install_result(result))

    def test_external_commands_are_reported_not_pip_installed(self) -> None:
        with mock.patch("ai_harness.recommended_packages.shutil.which", return_value=None):
            result = install_recommended_packages(["github"], dry_run=True)

        self.assertIn("gh", result.missing_commands)
        self.assertNotIn("gh", result.pip_packages)


if __name__ == "__main__":
    unittest.main()
