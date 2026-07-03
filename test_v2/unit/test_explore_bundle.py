from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness_v2.backend.application.bundle_artifacts import BundleValidationError as ExploreValidationError
from harness_v2.backend.application.phase_artifacts.explore import (
    validate_context_pack,
    validate_evidence_digest,
    validate_exploration_map,
    validate_manifest,
    validate_outcome_bundle,
    validate_outcome_synthesis,
    validate_request_profile,
)
from harness_v2.backend.application.phase_artifacts.explore_builders import (
    build_context_pack,
    build_exploration_map,
    build_manifest,
    build_outcome_bundle,
)
from harness_v2.backend.application.phase_artifacts.explore_ci import ci_evidence_from_artifacts
from harness_v2.backend.application.phase_artifacts.explore_mappers import compact_context_pack
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord


def request_profile() -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "explore_request_profile",
        "summary": "Fix tests",
        "request_type": "feature",
        "complexity": "local_change",
        "ambiguity": "clear",
        "risk": "low",
        "evidence_depth": "standard",
        "request_parts": ["Fix tests"],
        "constraints": [],
        "evidence_questions": ["What fails?"],
        "gatherers": ["code"],
        "clarification_questions": [],
    }


def digest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "explore_evidence_digest",
        "evidence": [
            {
                "id": "E1",
                "kind": "knowledge",
                "claim": "The request is bounded.",
                "status": "supported",
                "confidence": "high",
                "severity": "info",
                "sources": [{"type": "knowledge", "description": "fixture"}],
            }
        ],
        "blockers": [],
    }


def synthesis() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "explore_outcome_synthesis",
        "status": "ready_for_purpose",
        "normalized_request": {"summary": "Fix tests"},
        "triage": {"complexity": "local_change"},
        "entries": [
            {
                "id": "entry-1",
                "classification": "improvement",
                "action": "create",
                "title": "Fix tests",
                "rationale": "Evidence supports a bounded implementation change.",
                "behavioral_delta": "Fix tests should pass after the change.",
                "minimum_verification": "Run the focused tests for the changed behavior.",
                "evidence_refs": ["E1"],
            }
        ],
    }


class ExploreBundleValidationTests(unittest.TestCase):
    def test_valid_minimal_outputs_validate_and_bundle_refs_are_checked(self) -> None:
        profile = request_profile()
        evidence = digest()
        output = synthesis()
        exploration_map = build_exploration_map(evidence)
        bundle = build_outcome_bundle(output, evidence, exploration_map)

        validate_request_profile(profile)
        validate_evidence_digest(evidence)
        validate_outcome_synthesis(output)
        validate_outcome_bundle(bundle)

    def test_manifest_summarizes_publishable_entries(self) -> None:
        evidence = digest()
        bundle = build_outcome_bundle(synthesis(), evidence, build_exploration_map(evidence))

        manifest = build_manifest(bundle)

        validate_manifest(manifest)
        self.assertEqual("explore_manifest", manifest["kind"])
        self.assertEqual("entry-1", manifest["primary_entry_id"])
        self.assertEqual(["create"], manifest["actions"])
        self.assertEqual("ready", manifest["entries"][0]["publishability"])

    def test_outcome_synthesis_rejects_controller_owned_fields(self) -> None:
        output = synthesis()
        output["evidence"] = []

        with self.assertRaises(ExploreValidationError):
            validate_outcome_synthesis(output)

    def test_outcome_bundle_repairs_unknown_evidence_refs(self) -> None:
        output = synthesis()
        output["entries"] = [{"id": "entry-1", "classification": "improvement", "action": "create", "title": "Fix", "rationale": "Evidence supports the fix.", "behavioral_delta": "The fix changes observable behavior.", "minimum_verification": "Run focused tests.", "evidence_refs": ["missing"]}]
        bundle = build_outcome_bundle(output, digest(), build_exploration_map(digest()))

        validate_outcome_bundle(bundle)
        self.assertEqual(["E1"], bundle["entries"][0]["evidence_refs"])




    def test_outcome_gate_requires_question_and_options_for_ask_user(self) -> None:
        output = synthesis()
        output["entries"] = [{
            "id": "entry-decision",
            "classification": "decision_needed",
            "action": "ask_user",
            "title": "Choose direction",
            "rationale": "Two directions remain viable.",
            "question": "Which direction?",
            "options": ["A", "B"],
            "evidence_refs": ["E1"],
        }]
        validate_outcome_bundle(build_outcome_bundle(output, digest(), build_exploration_map(digest())))

        del output["entries"][0]["options"]
        with self.assertRaises(ExploreValidationError):
            validate_outcome_bundle(build_outcome_bundle(output, digest(), build_exploration_map(digest())))

    def test_outcome_gate_rejects_create_when_duplicate_signals_exist_without_counterevidence(self) -> None:
        output = synthesis()
        exploration_map = build_exploration_map(digest())
        exploration_map["duplicate_search"]["matches"] = [{"path": "src/existing.py", "summary": "Existing match", "confidence": "high"}]
        bundle = build_outcome_bundle(output, digest(), exploration_map)

        with self.assertRaises(ExploreValidationError):
            validate_outcome_bundle(bundle)

        output["entries"][0]["counterevidence"] = ["The existing match handles a different behavior."]
        output["entries"][0]["rejected_alternatives"] = [{"id": "alt-1", "reason": "Different behavior."}]
        bundle = build_outcome_bundle(output, digest(), exploration_map)
        validate_outcome_bundle(bundle)

    def test_outcome_gate_accepts_update_duplicate_and_existing_targets_from_map(self) -> None:
        evidence = digest()
        exploration_map = build_exploration_map(evidence)
        exploration_map["similar_functionality"] = [{"path": "docs/explorer/improvements/existing/improvement.md", "checksum": "abc", "summary": "Related improvement."}]
        exploration_map["duplicate_search"]["matches"] = [{"path": "src/existing.py", "summary": "Duplicate behavior."}]
        exploration_map["existing_functionality"] = [{"path": "src/already.py", "summary": "Already implemented."}]
        output = synthesis()
        output["entries"] = [
            {
                "id": "entry-update",
                "classification": "improvement",
                "action": "update_existing",
                "title": "Update related improvement",
                "rationale": "A related improvement already tracks the requested behavior.",
                "behavioral_delta": "The existing improvement is updated with the new behavior.",
                "minimum_verification": "Review the updated improvement target.",
                "target": {"path": "docs/explorer/improvements/existing/improvement.md", "checksum": "abc"},
                "evidence_refs": ["E1"],
            },
            {
                "id": "entry-duplicate",
                "classification": "not_worth_it",
                "action": "duplicate_noop",
                "title": "Duplicate behavior",
                "rationale": "The repository already has a duplicate match.",
                "target": {"path": "src/existing.py"},
                "evidence_refs": ["E1"],
            },
            {
                "id": "entry-existing",
                "classification": "not_worth_it",
                "action": "existing_functionality",
                "title": "Already implemented",
                "rationale": "The requested functionality already exists.",
                "target": {"path": "src/already.py"},
                "evidence_refs": ["E1"],
            },
        ]

        bundle = build_outcome_bundle(output, evidence, exploration_map)

        validate_outcome_bundle(bundle)

    def test_outcome_gate_rejects_bad_update_target_and_missing_value_fields(self) -> None:
        evidence = digest()
        exploration_map = build_exploration_map(evidence)
        exploration_map["similar_functionality"] = [{"path": "docs/explorer/improvements/existing/improvement.md", "checksum": "abc"}]
        output = synthesis()
        output["entries"][0]["action"] = "update_existing"
        output["entries"][0]["target"] = {"path": "docs/explorer/improvements/existing/improvement.md", "checksum": "wrong"}

        with self.assertRaises(ExploreValidationError):
            validate_outcome_bundle(build_outcome_bundle(output, evidence, exploration_map))

        output = synthesis()
        del output["entries"][0]["behavioral_delta"]
        with self.assertRaises(ExploreValidationError):
            validate_outcome_bundle(build_outcome_bundle(output, evidence, build_exploration_map(evidence)))

    def test_exploration_map_derives_surfaces_risks_and_v1_work_shapes(self) -> None:
        evidence = digest()
        evidence["evidence"] = [
            {
                "id": "E1",
                "kind": "test",
                "claim": "Test coverage has a regression gap for this behavior.",
                "status": "supported",
                "confidence": "high",
                "severity": "warning",
                "sources": [{"type": "file", "path": "tests/test_feature.py"}],
            }
        ]

        exploration_map = build_exploration_map(evidence, profile=request_profile())

        validate_exploration_map(exploration_map, {"E1"})
        self.assertEqual("tests/test_feature.py", exploration_map["surfaces"][0]["path"])
        self.assertIn("change_with_test_gap_closure", {item["shape"] for item in exploration_map["candidate_work_shapes"]})
        self.assertEqual("regression_verification", exploration_map["verification_surfaces"][1]["kind"])

    def test_context_pack_includes_ci_digest_and_compaction_excludes_knowledge_requirement(self) -> None:
        class Reader:
            def __init__(self) -> None:
                self.data = {
                    "ci-status.json": {"providers": ["unit"], "warnings": []},
                    "ci-signals.json": {
                        "status": "ready",
                        "signals": [{
                            "tool": "pytest",
                            "category": "tests",
                            "severity": "error",
                            "summary": "tests/test_feature.py fails",
                            "path": "tests/test_feature.py",
                        }],
                    },
                    "git-run.json": {"head": "abc123"},
                    "explore/repository_observations.json": {
                        "observations": [{"kind": "test", "path": "tests/test_feature.py", "score": 20}]
                    },
                    "explore/explorer_scope.json": {"mode": "fixture"},
                }

            def read_json(self, _run_id: str, artifact_id: str) -> dict[str, object] | None:
                return self.data.get(artifact_id)

        run = RunRecord("run-1", "Fix tests", RunStatus.RUNNING, root_bundle=BundleName.EXPLORE_BUNDLE, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING)
        pack = build_context_pack(run, request_profile(), Reader())
        compact = compact_context_pack(pack)
        ci_evidence = ci_evidence_from_artifacts(Reader(), "run-1", relevant_paths={"tests/test_feature.py"})

        validate_context_pack(pack)
        self.assertEqual("ready", pack["ci_digest"]["health"])
        self.assertEqual("abc123", pack["git"]["head"])
        self.assertEqual("fixture", pack["explorer_scope"]["mode"])
        self.assertEqual("tests/test_feature.py", pack["repository_observations"][0]["path"])
        self.assertNotIn("repository", compact)
        self.assertEqual("CI1", ci_evidence[0]["id"])
        self.assertEqual("CI2", ci_evidence[1]["id"])


    def test_context_pack_discovers_related_improvements_and_repository_observations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            improvement = root / "docs/explorer/improvements/palette/improvement.md"
            improvement.parent.mkdir(parents=True)
            improvement.write_text(
                "# Improvement: Palette search\n"
                "## Problem\n"
                "Palette duplicate handling is scattered.\n"
                "## Desired Behavior\n"
                "Palette duplicate search reuses existing functionality.\n",
                encoding="utf-8",
            )
            source = root / "src/palette_search.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "def palette_duplicate_search():\n"
                "    return 'palette duplicate handling'\n",
                encoding="utf-8",
            )

            profile = request_profile()
            profile["summary"] = "Add palette duplicate search"
            profile["request_parts"] = ["Palette duplicate search"]
            run = RunRecord("run-1", "Add palette duplicate search", RunStatus.RUNNING, root_bundle=BundleName.EXPLORE_BUNDLE, current_phase=PhaseName.EXPLORE_REQUEST_UNDERSTANDING)

            pack = build_context_pack(run, profile, repository_root=root)

        validate_context_pack(pack)
        self.assertEqual("docs/explorer/improvements/palette/improvement.md", pack["related_improvements"][0]["path"])
        self.assertTrue(any(item["path"] == "src/palette_search.py" for item in pack["repository_observations"]))

    def test_exploration_map_derives_existing_similar_and_duplicate_search(self) -> None:
        evidence = digest()
        context_pack = {
            "repository_observations": [
                {
                    "kind": "source",
                    "path": "src/palette_search.py",
                    "score": 22,
                    "matched_terms": ["palette", "duplicate"],
                    "symbols": ["palette_duplicate_search"],
                    "matches": ["L1: def palette_duplicate_search():"],
                }
            ],
            "related_improvements": [
                {
                    "path": "docs/explorer/improvements/palette/improvement.md",
                    "summary": "Palette duplicate handling already has an improvement.",
                    "checksum": "abc",
                    "score": 9,
                }
            ],
        }

        exploration_map = build_exploration_map(evidence, profile=request_profile(), context_pack=context_pack)

        validate_exploration_map(exploration_map, {"E1"})
        self.assertEqual("src/palette_search.py", exploration_map["existing_functionality"][0]["path"])
        self.assertEqual("docs/explorer/improvements/palette/improvement.md", exploration_map["similar_functionality"][0]["path"])
        self.assertIn("palette", exploration_map["duplicate_search"]["searched_terms"])
        self.assertTrue(exploration_map["duplicate_search"]["matches"])

    def test_request_profile_requires_string_lists_without_duplicates(self) -> None:
        profile = request_profile()
        profile["gatherers"] = ["code", "code"]

        with self.assertRaises(ExploreValidationError):
            validate_request_profile(profile)


if __name__ == "__main__":
    unittest.main()
