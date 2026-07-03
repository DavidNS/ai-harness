from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness_v2.adapters.storage import InMemoryArtifactStore
from harness_v2.backend.application.bundle_artifacts import BundleArtifactGateway, BundleRuntimeConfig
from harness_v2.backend.application.phase_executor import PhaseExecutionContext
from harness_v2.backend.application.phases.knowledge_synthesis import build_knowledge_inputs
from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord


class StaticClock:
    def now_iso(self) -> str:
        return "2026-07-01T00:00:00+00:00"


class KnowledgeExtractionInputTests(unittest.TestCase):
    def test_build_knowledge_inputs_uses_one_v1_style_context_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "src" / "app.py"
            source_file.parent.mkdir()
            source_file.write_text("def run():\n    return 'ok'\n", encoding="utf-8")
            artifacts = InMemoryArtifactStore()
            gateway = BundleArtifactGateway(artifacts, object(), BundleRuntimeConfig(root))
            run = RunRecord(
                "run-1",
                "Fix tests",
                RunStatus.RUNNING,
                root_bundle=BundleName.SDD_BUNDLE,
                current_step_id="SDD_BUNDLE:007",
                completed_step_ids=tuple(bundle_catalog.step_ids(BundleName.SDD_BUNDLE)[:6]),
            )
            context = PhaseExecutionContext(run, object(), gateway, BundleRuntimeConfig(root), StaticClock())
            source_artifacts = {
                "explore/outcome_bundle.json": {
                    "entries": [{"id": "entry-1", "evidence_refs": ["E1"]}],
                    "evidence": [{"id": "E1", "sources": [{"type": "file", "path": "src/app.py"}]}],
                },
                "published/explore-handoff.json": {"status": "ready_for_purpose"},
            }
            for artifact_id, value in source_artifacts.items():
                gateway.write_json(run.run_id, artifact_id, value)
            gateway.write_json(run.run_id, "git-run.json", {"head": "abc123"})
            gateway.write_text(
                run.run_id,
                "workers/SDD_BUNDLE_001/explore_request_profile/request.json",
                "Return only the required artifact. Controller inputs: nested",
            )

            inputs = build_knowledge_inputs(context, BundleName.EXPLORE_BUNDLE, source_artifacts)

            self.assertEqual("explore_bundle", inputs["source_phase"])
            self.assertIn("explore/outcome_bundle.json", inputs["source_artifacts"])
            self.assertIn("artifact_inventory", inputs)
            self.assertIn("selected_artifacts", inputs)
            self.assertIn("repository_snapshot", inputs)
            self.assertEqual("abc123", inputs["repository_snapshot"]["git_head"])
            self.assertIn(
                "workers/SDD_BUNDLE_001/explore_request_profile/request.json",
                inputs["artifact_inventory"],
            )
            self.assertNotIn(
                "workers/SDD_BUNDLE_001/explore_request_profile/request.json",
                inputs["selected_artifacts"],
            )
            self.assertEqual("src/app.py", inputs["repository_snapshot"]["entries"][0]["path"])
            self.assertEqual("entry-1", inputs["entry_contexts"][0]["entry_id"])
            self.assertEqual("E1", inputs["entry_contexts"][0]["evidence"][0]["id"])
            self.assertEqual(inputs["selected_artifacts"], inputs["context"]["selected_artifacts"])
            self.assertEqual(inputs["entry_contexts"], inputs["context"]["entry_contexts"])


if __name__ == "__main__":
    unittest.main()
