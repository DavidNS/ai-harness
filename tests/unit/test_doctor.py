import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import doctor
import install
from tests.unit.test_install import checkout


class DoctorTests(unittest.TestCase):
    def test_direct_runner_bootstrap_and_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir(); co = checkout(root)
            for dirname in doctor.REQUIRED_HARNESS_DIRS:
                (co / "harness" / dirname).mkdir(parents=True, exist_ok=True)
            link = install.links_for(co, ["codex"], project=project)[0]
            self.assertTrue(install.install([link])[0])
            self.assertTrue(all(check.ok for check in doctor.check_direct_runner(co)))
            self.assertTrue(doctor.check_bootstrap(link).ok)
            self.assertTrue(doctor.check_runtime(root).ok)

    def test_direct_runner_missing_resource_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            co = checkout(Path(tmp))
            checks = doctor.check_direct_runner(co)
            self.assertFalse(all(check.ok for check in checks))
            self.assertIn("resource:ai_harness", [check.name for check in checks if not check.ok])

    def test_foreign_or_drifted_bootstrap_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir(); co = checkout(root)
            link = install.links_for(co, ["codex"], project=project)[0]
            link.destination.write_text(install.bootstrap_content(root / "foreign", "codex"), encoding="utf-8")
            self.assertFalse(doctor.check_bootstrap(link).ok)
            link.destination.write_text(install.bootstrap_content(co, "codex") + "drift\n", encoding="utf-8")
            self.assertFalse(doctor.check_bootstrap(link).ok)

    def test_runtime_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / ".ai-harness").write_text("file\n", encoding="utf-8")
            self.assertFalse(doctor.check_runtime(root).ok)

    def test_sqlite_fts_and_missing_provider(self):
        self.assertEqual([x.name for x in doctor.check_sqlite()], ["sqlite", "sqlite-fts5"])
        with mock.patch("doctor.shutil.which", return_value=None): check = doctor.check_provider("codex")
        self.assertFalse(check.ok); self.assertFalse(check.required)

    def test_owned_shortcut_passes_doctor_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); co = checkout(root); bin_dir = root / "bin"
            links = install.launcher_links_for(co, bin_dir)
            self.assertTrue(install.install(links)[0])
            self.assertTrue(all(doctor.check_launcher_shortcut(link).ok for link in links))

    def test_missing_or_drifted_shortcut_fails_doctor_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); co = checkout(root); bin_dir = root / "bin"; bin_dir.mkdir()
            links = install.launcher_links_for(co, bin_dir)
            self.assertTrue(all(not doctor.check_launcher_shortcut(link).ok for link in links))
            for link in links:
                link.destination.write_text(install.launcher_content(co, link.destination.name) + "drift\n", encoding="utf-8")
                link.destination.chmod(0o755)
                self.assertFalse(doctor.check_launcher_shortcut(link).ok)


if __name__ == "__main__": unittest.main()
