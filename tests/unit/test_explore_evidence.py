from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_harness.orchestrator.explore_evidence import ci_digest_from_artifacts, ci_evidence_from_artifacts, compact_context_pack, context_pack
from ai_harness.stores.artifact import ArtifactStore


class ExploreEvidenceTests(unittest.TestCase):
    def _store(self) -> ArtifactStore:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return ArtifactStore(Path(directory.name))

    def _write_ci(self, store: ArtifactStore) -> None:
        store.write_json("ci-status.json", {
            "schema_version": 1,
            "providers": [{"provider": "github", "path": ".github/workflows/ai-harness-ci.yml", "managed": True, "in_sync": True}],
            "warnings": [],
        })
        store.write_json("ci-signals.json", {
            "schema_version": 2,
            "kind": "ai_harness_ci_signals",
            "status": "ready",
            "providers": {"github": {"summary": {"status": "failed", "signal_count": 5}}},
            "signals": [
                {"id": "S1", "tool": "check_architecture", "category": "contract", "severity": "error", "summary": "registered phase is unused", "confidence": "high"},
                {"id": "S2", "tool": "check_architecture", "category": "budget", "severity": "warning", "path": "harness/cli/commands.py", "summary": "harness/cli/commands.py has 767 lines; budget is 400", "confidence": "high"},
                {"id": "S3", "tool": "ruff", "category": "lint", "severity": "warning", "path": "harness/ai_harness/ci_support.py", "summary": "I001 import block unsorted", "confidence": "high"},
                {"id": "S4", "tool": "semgrep", "category": "security", "severity": "error", "path": "harness/cli/runtime.py", "summary": "unsafe subprocess input", "confidence": "medium"},
                {"id": "S5", "tool": "pytest", "category": "tests", "severity": "error", "summary": "Pytest failed on trunk baseline.", "confidence": "high"},
            ],
        })

    def test_ci_digest_compacts_raw_signals_and_preserves_actionable_findings(self) -> None:
        store = self._store()
        self._write_ci(store)

        digest = ci_digest_from_artifacts(store, relevant_paths={"harness/cli/ui.py", "tests/unit/test_decision_menu.py"})

        self.assertEqual("ci_digest", digest["kind"])
        self.assertEqual("ready", digest["health"])
        self.assertEqual(5, digest["signal_count"])
        self.assertTrue(any(item["summary"] == "registered phase is unused" for item in digest["blocking_findings"]))
        self.assertTrue(any(item.get("path") == "harness/cli/commands.py" for item in digest["structural_refactor_hints"]))
        self.assertFalse(any(item.get("path") == "harness/ai_harness/ci_support.py" for item in digest["relevant_findings"]))
        self.assertEqual(1, digest["baseline_noise"]["by_tool"]["ruff"])

    def test_context_pack_includes_ci_digest_not_raw_ci_signals(self) -> None:
        store = self._store()
        self._write_ci(store)

        pack = context_pack(
            request="Add slash command autocomplete.",
            profile={"summary": "Add slash command autocomplete."},
            knowledge=[],
            related_improvements=[],
            repository_observations=[{"path": "harness/cli/ui.py"}],
            artifacts=store,
            explorer_scope={"artifacts": []},
        )

        self.assertIn("ci_digest", pack)
        self.assertNotIn("ci_signals", pack)
        self.assertEqual("ci_digest", pack["ci_digest"]["kind"])
        self.assertNotIn("signals", pack["ci_digest"])
        self.assertNotIn("path_index", pack["ci_digest"])

    def test_compact_context_pack_drops_ci_observations_and_caps_repository_observations(self) -> None:
        store = self._store()
        self._write_ci(store)
        observations = [
            {"kind": "ci_signal", "path": f"harness/ci/{index}.py", "matches": ["CI noise"]}
            for index in range(30)
        ] + [
            {"kind": "source", "path": f"harness/cli/ui_{index}.py", "score": 50 - index, "symbols": ["a", "b", "c"], "matches": ["m1", "m2", "m3", "m4"]}
            for index in range(20)
        ]
        pack = context_pack(
            request="Add slash command autocomplete.",
            profile={"summary": "Add slash command autocomplete."},
            knowledge=[],
            related_improvements=[],
            repository_observations=observations,
            artifacts=store,
            explorer_scope={"artifacts": []},
        )

        compact = compact_context_pack(pack)

        self.assertEqual(12, len(compact["repository_observations"]))
        self.assertFalse(any(item["kind"] == "ci_signal" for item in compact["repository_observations"]))
        self.assertLessEqual(len(compact["repository_observations"][0]["symbols"]), 8)
        self.assertLessEqual(len(compact["repository_observations"][0]["matches"]), 3)

    def test_controller_ci_evidence_is_compact(self) -> None:
        store = self._store()
        self._write_ci(store)

        evidence = ci_evidence_from_artifacts(store, relevant_paths={"harness/cli/ui.py"})

        self.assertLessEqual(len(evidence), 7)
        self.assertEqual("artifact", evidence[0]["sources"][0]["type"])
        self.assertTrue(any(item["claim"] == "registered phase is unused" for item in evidence))


if __name__ == "__main__":
    unittest.main()
