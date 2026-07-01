import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import install


def checkout(root):
    path = root / "checkout"
    (path / "harness").mkdir(parents=True)
    (path / "harness" / "run.py").write_text("runner\n", encoding="utf-8")
    launcher = path / "ai-harness"
    launcher.write_text("#!/bin/sh\nexec echo launcher \"$@\"\n", encoding="utf-8")
    launcher.chmod(0o755)
    ui_launcher = path / "ai-harness-ui"
    ui_launcher.write_text("#!/bin/sh\nexec echo ui launcher \"$@\"\n", encoding="utf-8")
    ui_launcher.chmod(0o755)
    (path / "skills" / "ai-code-harness").mkdir(parents=True)
    return path


class InstallTests(unittest.TestCase):
    def test_generated_bootstraps_are_idempotent_regular_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir()
            links = install.links_for(checkout(root), ["codex", "claude"], project=project)
            self.assertTrue(install.install(links)[0])
            self.assertTrue(all(x.destination.is_file() and not x.destination.is_symlink() for x in links))
            for link in links:
                text = link.destination.read_text(encoding="utf-8")
                self.assertIn("ai-code-harness-bootstrap", text)
                self.assertIn(f'provider="{link.provider}"', text)
                self.assertIn(str(root / "checkout"), text)
                self.assertIn("python3 -B", text)
                self.assertIn("harness/run.py", text)
                self.assertIn("--cwd", text)
                self.assertIn("--provider", text)
                self.assertIn("--activated", text)
            ok, messages = install.install(links)
            self.assertTrue(ok); self.assertTrue(all(x.startswith("unchanged:") for x in messages))

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"
            links = install.links_for(checkout(root), ["codex"], project=project)
            self.assertTrue(install.install(links, dry_run=True)[0]); self.assertFalse(project.exists())

    def test_regular_file_conflict_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir()
            existing = project / "AGENTS.md"; existing.write_text("keep\n", encoding="utf-8")
            ok, messages = install.install(install.links_for(checkout(root), ["codex"], project=project))
            self.assertFalse(ok); self.assertEqual(existing.read_text(encoding="utf-8"), "keep\n")
            self.assertIn("project-local", " ".join(messages))

    def test_foreign_marker_conflict_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir()
            existing = project / "AGENTS.md"
            existing.write_text(install.bootstrap_content(root / "foreign", "codex"), encoding="utf-8")
            ok, messages = install.install(install.links_for(checkout(root), ["codex"], project=project))
            self.assertFalse(ok)
            self.assertIn(str(root / "foreign"), existing.read_text(encoding="utf-8"))
            self.assertIn("conflict:", " ".join(messages))

    def test_owned_marker_file_is_updated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir(); co = checkout(root)
            link = install.links_for(co, ["codex"], project=project)[0]
            link.destination.write_text(
                install.bootstrap_content(co, "codex") + "drift\n",
                encoding="utf-8",
            )
            ok, messages = install.install([link])
            self.assertTrue(ok); self.assertTrue(messages[0].startswith("updated:"))
            self.assertEqual(install.bootstrap_content(co, "codex"), link.destination.read_text(encoding="utf-8"))

    def test_missing_source_does_not_create_broken_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); destination = root / "destination"
            link = install.Link(root / "missing" / "harness" / "run.py", destination, "missing", provider="codex")
            ok, messages = install.install([link])
            self.assertFalse(ok); self.assertFalse(destination.exists())
            self.assertIn("source is missing", messages[0])

    def test_symlinked_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "project"; project.mkdir()
            outside = root / "outside"; outside.mkdir()
            (project / ".codex").symlink_to(outside, target_is_directory=True)
            links = install.links_for(checkout(root), ["codex"], home=project)

            ok, messages = install.install(links)

            self.assertFalse(ok)
            self.assertFalse((outside / "AGENTS.md").exists())
            self.assertIn("unsafe parent symlink", " ".join(messages))

    def test_shortcut_dry_run_reports_destination_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); co = checkout(root); bin_dir = root / "bin"
            links = install.launcher_links_for(co, bin_dir)

            ok, messages = install.install(links, dry_run=True)

            self.assertTrue(ok)
            self.assertIn(str(bin_dir / "aih"), messages[0])
            self.assertIn(str(bin_dir / "aihui"), messages[1])
            self.assertTrue(all("would write" in message for message in messages))
            self.assertFalse(bin_dir.exists())

    def test_shortcut_install_creates_executable_owned_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); co = checkout(root); bin_dir = root / "bin"
            links = install.launcher_links_for(co, bin_dir)

            ok, messages = install.install(links)

            self.assertTrue(ok, messages)
            destinations = {link.destination.name: link.destination for link in links}
            for destination in destinations.values():
                self.assertTrue(destination.is_file())
                self.assertTrue(destination.stat().st_mode & 0o111)
                text = destination.read_text(encoding="utf-8")
                self.assertIn("ai-code-harness-launcher", text)
                self.assertIn(f'checkout="{co.resolve()}"', text)
                self.assertIn("exec", text)
            self.assertIn("ai-harness", destinations["aih"].read_text(encoding="utf-8"))
            self.assertIn("ai-harness-ui", destinations["aihui"].read_text(encoding="utf-8"))
            ok, messages = install.install(links)
            self.assertTrue(ok)
            self.assertTrue(all(message.startswith("unchanged:") for message in messages))

    def test_shortcut_regular_file_conflict_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); co = checkout(root); bin_dir = root / "bin"; bin_dir.mkdir()
            link = install.launcher_links_for(co, bin_dir)[0]
            link.destination.write_text("keep\n", encoding="utf-8")

            ok, messages = install.install([link])

            self.assertFalse(ok)
            self.assertEqual("keep\n", link.destination.read_text(encoding="utf-8"))
            self.assertIn("conflict:", " ".join(messages))

    def test_shortcut_foreign_symlink_conflict_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); co = checkout(root); bin_dir = root / "bin"; bin_dir.mkdir()
            foreign = root / "foreign"; foreign.write_text("foreign\n", encoding="utf-8")
            link = install.launcher_links_for(co, bin_dir)[0]
            link.destination.symlink_to(foreign)

            ok, messages = install.install([link])

            self.assertFalse(ok)
            self.assertTrue(link.destination.is_symlink())
            self.assertIn("conflict:", " ".join(messages))

    def test_shortcut_symlinked_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); co = checkout(root); real = root / "real"; real.mkdir()
            bin_dir = root / "bin"; bin_dir.symlink_to(real, target_is_directory=True)
            links = install.launcher_links_for(co, bin_dir)

            ok, messages = install.install(links)

            self.assertFalse(ok)
            self.assertFalse((real / "aih").exists())
            self.assertFalse((real / "aihui").exists())
            self.assertIn("unsafe parent", " ".join(messages))


if __name__ == "__main__": unittest.main()
