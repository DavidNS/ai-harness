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


def write_resource(root: Path, task_id: str = "task", output_schema: str | None = "task_output") -> None:
    (root / "workers").mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "backend" / "application" / "json_schemas").mkdir(parents=True, exist_ok=True)
    (root / "workers" / f"{task_id}.md").write_text("# Worker\nDo work.\n", encoding="utf-8")
    (root / "prompts" / f"{task_id}.md").write_text("# Prompt\nReturn JSON.\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "phase": task_id,
        "paths": [{"pattern": "src/**", "mode": "read"}],
        "commands": [["python3", "-m", "unittest"]],
        "skills": ["skill-a"],
        "mcp_tools": [{"server": "docs", "name": "search", "access": "read"}],
    }
    if output_schema is not None:
        manifest["output_schema"] = output_schema
        (root / "backend" / "application" / "json_schemas" / f"{output_schema}.schema.json").write_text(
            json.dumps({"type": "object", "required": ["schema_version"]}),
            encoding="utf-8",
        )
    (root / "capabilities" / f"{task_id}.json").write_text(json.dumps(manifest), encoding="utf-8")


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
            self.assertIsNotNone(spec.output_schema)
            assert spec.output_schema is not None
            self.assertEqual("task_output", spec.output_schema.name)
            self.assertEqual("object", spec.output_schema.schema["type"])


    def test_package_workers_wire_known_output_schemas(self) -> None:
        expected = {
            "artifact_delta_repair": "json_artifact_delta",
            "design": "design_document",
            "explore_evidence_digest": "evidence_digest",
            "explore_outcome_synthesis": "outcome_synthesis",
            "explore_request_profile": "request_profile",
            "knowledge_synthesis": "knowledge_synthesis",
            "purpose": "purpose_bundle",
            "spec": "spec_document",
            "tasks": "tasks_document",
            "tdd_review": "tdd_review",
        }
        store = FileWorkerResourceStore()

        for task_id, schema_name in expected.items():
            with self.subTest(task_id=task_id):
                spec = store.get(task_id)
                self.assertIsNotNone(spec.output_schema)
                assert spec.output_schema is not None
                self.assertEqual(schema_name, spec.output_schema.name)
                self.assertTrue(spec.output_schema.schema)

    def test_output_schema_is_optional(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_resource(root, output_schema=None)

            spec = FileWorkerResourceStore(root).get("task")

            self.assertIsNone(spec.output_schema)

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

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_resource(root)
            (root / "capabilities" / "task.json").write_text(
                '{"schema_version": 1, "phase": "task", "output_schema": "missing"}',
                encoding="utf-8",
            )
            with self.assertRaises(WorkerResourceNotFoundError):
                FileWorkerResourceStore(root).get("task")


if __name__ == "__main__":
    unittest.main()
