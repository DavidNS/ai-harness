from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.ports.worker_resources import (
    WorkerResourceNotFoundError,
    WorkerResourceValidationError,
)


def write_resource(root: Path, task_id: str = "task") -> None:
    (root / "workers").mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "workers" / f"{task_id}.md").write_text("# Worker\nDo work.\n", encoding="utf-8")
    (root / "prompts" / f"{task_id}.md").write_text("# Prompt\nReturn JSON.\n", encoding="utf-8")
    (root / "capabilities" / f"{task_id}.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase": task_id,
                "paths": [{"pattern": "src/**", "mode": "read"}],
                "commands": [["python3", "-m", "unittest"]],
                "skills": ["skill-a"],
                "mcp_tools": [{"server": "docs", "name": "search", "access": "read"}],
            }
        ),
        encoding="utf-8",
    )


class FileWorkerResourceStoreTests(unittest.TestCase):
    def test_loads_markdown_and_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_resource(root)

            spec = FileWorkerResourceStore(root).get("task")

            self.assertEqual("task", spec.task_id)
            self.assertIn("# Worker", spec.playbook_markdown)
            self.assertEqual("src/**", spec.capabilities.paths[0].pattern)
            self.assertEqual(("python3", "-m", "unittest"), spec.capabilities.commands[0])
            self.assertEqual(("skill-a",), spec.capabilities.skills)
            self.assertEqual("docs", spec.capabilities.mcp_tools[0].server)

    def test_fails_closed_for_missing_resource(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(WorkerResourceNotFoundError):
                FileWorkerResourceStore(Path(temp)).get("missing")

    def test_rejects_unsafe_task_id_empty_markdown_and_invalid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_resource(root)
            with self.assertRaises(WorkerResourceValidationError):
                FileWorkerResourceStore(root).get("../escape")

            (root / "workers" / "task.md").write_text("", encoding="utf-8")
            with self.assertRaises(WorkerResourceValidationError):
                FileWorkerResourceStore(root).get("task")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_resource(root)
            (root / "capabilities" / "task.json").write_text('{"schema_version": 1, "phase": "other"}', encoding="utf-8")
            with self.assertRaises(WorkerResourceValidationError):
                FileWorkerResourceStore(root).get("task")


if __name__ == "__main__":
    unittest.main()
