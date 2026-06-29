import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import install
import uninstall
from tests.unit.test_install import checkout


class UninstallTests(unittest.TestCase):
    def test_only_owned_bootstraps_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir()
            links = install.links_for(checkout(root), ["codex"], project=project)
            install.install(links); self.assertTrue(uninstall.uninstall(links)[0])
            self.assertTrue(all(not x.destination.exists() for x in links))

    def test_foreign_link_and_file_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir(); foreign = root / "foreign"; foreign.mkdir()
            links = install.links_for(checkout(root), ["codex"], project=project)
            links[0].destination.symlink_to(foreign)
            self.assertFalse(uninstall.uninstall(links)[0])
            self.assertTrue(links[0].destination.is_symlink())
            links[0].destination.unlink()
            links[0].destination.write_text("keep\n", encoding="utf-8")
            self.assertFalse(uninstall.uninstall(links)[0])
            self.assertEqual(links[0].destination.read_text(encoding="utf-8"), "keep\n")

    def test_foreign_marker_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir()
            links = install.links_for(checkout(root), ["codex"], project=project)
            links[0].destination.write_text(install.bootstrap_content(root / "foreign", "codex"), encoding="utf-8")
            self.assertFalse(uninstall.uninstall(links)[0])
            self.assertTrue(links[0].destination.exists())

    def test_dry_run_preserves_owned_bootstraps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir()
            links = install.links_for(checkout(root), ["codex"], project=project); install.install(links)
            self.assertTrue(uninstall.uninstall(links, dry_run=True)[0]); self.assertTrue(all(x.destination.exists() for x in links))

    def test_legacy_owned_skill_symlinks_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir(); co = checkout(root)
            legacy = install.legacy_skill_links_for(co, ["codex"], project=project)
            for link in legacy:
                link.destination.parent.mkdir(parents=True, exist_ok=True)
                relative = os.path.relpath(link.source, start=link.destination.parent)
                link.destination.symlink_to(relative, target_is_directory=True)
            self.assertTrue(uninstall.uninstall(legacy)[0])
            self.assertTrue(all(not link.destination.exists() for link in legacy))

    def test_owned_shortcut_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); co = checkout(root); bin_dir = root / "bin"
            links = install.launcher_links_for(co, bin_dir)
            self.assertTrue(install.install(links)[0])

            ok, messages = uninstall.uninstall(links)

            self.assertTrue(ok, messages)
            self.assertFalse(links[0].destination.exists())

    def test_foreign_shortcut_file_or_symlink_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); co = checkout(root); bin_dir = root / "bin"; bin_dir.mkdir()
            link = install.launcher_links_for(co, bin_dir)[0]
            link.destination.write_text("keep\n", encoding="utf-8")
            self.assertFalse(uninstall.uninstall([link])[0])
            self.assertEqual("keep\n", link.destination.read_text(encoding="utf-8"))
            link.destination.unlink()
            foreign = root / "foreign"; foreign.write_text("foreign\n", encoding="utf-8")
            link.destination.symlink_to(foreign)
            self.assertFalse(uninstall.uninstall([link])[0])
            self.assertTrue(link.destination.is_symlink())


if __name__ == "__main__": unittest.main()
