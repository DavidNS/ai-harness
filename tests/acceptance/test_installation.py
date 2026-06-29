from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "scripts" / "install.py"
UNINSTALL = ROOT / "scripts" / "uninstall.py"


def run_script(script: Path, *arguments: str, cwd: Path, home: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, "-B", str(script), *arguments],
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def assert_bootstrap(testcase: unittest.TestCase, path: Path, provider: str) -> None:
    testcase.assertTrue(path.is_file(), path)
    testcase.assertFalse(path.is_symlink(), path)
    text = path.read_text(encoding="utf-8")
    testcase.assertIn("ai-code-harness-bootstrap", text)
    testcase.assertIn(f'checkout="{ROOT}"', text)
    testcase.assertIn(f'provider="{provider}"', text)
    testcase.assertIn(f"python3 -B {ROOT / 'harness' / 'run.py'}", text)
    testcase.assertIn(f"--provider {provider}", text)
    testcase.assertIn("--activated", text)
    testcase.assertIn("original request unchanged", text)


def assert_shortcut(testcase: unittest.TestCase, path: Path) -> None:
    testcase.assertTrue(path.is_file(), path)
    testcase.assertFalse(path.is_symlink(), path)
    testcase.assertTrue(os.access(path, os.X_OK), path)
    text = path.read_text(encoding="utf-8")
    testcase.assertIn("ai-code-harness-launcher", text)
    testcase.assertIn(f'checkout="{ROOT}"', text)
    testcase.assertIn("ai-harness", text)


class IsolatedInstallationAcceptanceTests(unittest.TestCase):
    def test_global_install_is_idempotent_and_safely_uninstalled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            repository = root / "repository"
            home.mkdir()
            repository.mkdir()

            first = run_script(INSTALL, "--codex", "--claude", "--global", cwd=repository, home=home)
            self.assertEqual(0, first.returncode, first.stderr)

            expected = {
                home / ".codex/AGENTS.md": "codex",
                home / ".claude/CLAUDE.md": "claude",
            }
            for destination, provider in expected.items():
                assert_bootstrap(self, destination, provider)
            self.assertFalse((home / ".agents/skills/ai-code-harness").exists())
            self.assertFalse((home / ".claude/skills/ai-code-harness").exists())

            second = run_script(INSTALL, "--codex", "--claude", "--global", cwd=repository, home=home)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(2, second.stdout.count("unchanged:"))

            removed = run_script(UNINSTALL, "--codex", "--claude", "--global", cwd=repository, home=home)
            self.assertEqual(0, removed.returncode, removed.stderr)
            self.assertTrue(all(not destination.exists() for destination in expected))


    def test_global_install_with_shortcut_creates_bootstrap_and_executable_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            repository = root / "repository"
            home.mkdir()
            repository.mkdir()

            result = run_script(INSTALL, "--codex", "--global", "--launcher", cwd=repository, home=home)
            self.assertEqual(0, result.returncode, result.stderr)
            assert_bootstrap(self, home / ".codex/AGENTS.md", "codex")
            shortcut = home / ".local/bin/aih"
            assert_shortcut(self, shortcut)

            removed = run_script(UNINSTALL, "--codex", "--global", "--launcher", cwd=repository, home=home)
            self.assertEqual(0, removed.returncode, removed.stderr)
            self.assertFalse((home / ".codex/AGENTS.md").exists())
            self.assertFalse(shortcut.exists())

    def test_project_install_uses_repository_local_bootstraps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            repository = root / "repository"
            home.mkdir()
            repository.mkdir()

            result = run_script(
                INSTALL, "--codex", "--claude", "--project", str(repository),
                cwd=root, home=home,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            assert_bootstrap(self, repository / "AGENTS.md", "codex")
            assert_bootstrap(self, repository / "CLAUDE.md", "claude")
            self.assertFalse((repository / ".agents/skills/ai-code-harness").exists())
            self.assertFalse((repository / ".claude/skills/ai-code-harness").exists())

            removed = run_script(
                UNINSTALL, "--codex", "--claude", "--project", str(repository),
                cwd=root, home=home,
            )
            self.assertEqual(0, removed.returncode, removed.stderr)
            self.assertFalse((repository / "AGENTS.md").exists())
            self.assertFalse((repository / "CLAUDE.md").exists())

    def test_uninstall_removes_old_owned_skill_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            repository = root / "repository"
            home.mkdir()
            repository.mkdir()
            old_codex = home / ".agents/skills/ai-code-harness"
            old_claude = home / ".claude/skills/ai-code-harness"
            for destination in (old_codex, old_claude):
                destination.parent.mkdir(parents=True)
                destination.symlink_to(ROOT / "skills" / "ai-code-harness", target_is_directory=True)

            removed = run_script(UNINSTALL, "--codex", "--claude", "--global", cwd=repository, home=home)
            self.assertEqual(0, removed.returncode, removed.stderr)
            self.assertFalse(old_codex.exists())
            self.assertFalse(old_claude.exists())

    def test_global_conflict_preserves_existing_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            repository = root / "repository"
            bootstrap = home / ".codex/AGENTS.md"
            bootstrap.parent.mkdir(parents=True)
            bootstrap.write_text("user configuration\n", encoding="utf-8")
            repository.mkdir()

            result = run_script(INSTALL, "--codex", "--global", cwd=repository, home=home)
            self.assertEqual(1, result.returncode)
            self.assertEqual("user configuration\n", bootstrap.read_text(encoding="utf-8"))
            self.assertIn("project-local install", result.stdout)
            self.assertIn("manual one-line include", result.stdout)
            self.assertIn("merge", result.stdout)


if __name__ == "__main__":
    unittest.main()
