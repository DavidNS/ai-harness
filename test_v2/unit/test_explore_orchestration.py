from __future__ import annotations

import unittest

from harness_v2.backend.application.explore_orchestration import (
    ExploreValidationError,
    build_context_pack,
    build_exploration_map,
    build_outcome_bundle,
    ci_evidence_from_artifacts,
    compact_context_pack,
    validate_context_pack,
    validate_evidence_digest,
    validate_exploration_map,
    validate_outcome_bundle,
    validate_outcome_synthesis,
    validate_request_profile,
)
from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy
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
                "title": "Fix tests",
                "evidence_refs": ["E1"],
            }
        ],
    }


class ExploreOrchestrationValidationTests(unittest.TestCase):
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

    def test_outcome_synthesis_rejects_controller_owned_fields(self) -> None:
        output = synthesis()
        output["evidence"] = []

        with self.assertRaises(ExploreValidationError):
            validate_outcome_synthesis(output)

    def test_outcome_bundle_repairs_unknown_evidence_refs(self) -> None:
        output = synthesis()
        output["entries"] = [{"id": "entry-1", "classification": "improvement", "title": "Fix", "evidence_refs": ["missing"]}]
        bundle = build_outcome_bundle(output, digest(), build_exploration_map(digest()))

        validate_outcome_bundle(bundle)
        self.assertEqual(["E1"], bundle["entries"][0]["evidence_refs"])


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

        run = RunRecord("run-1", "Fix tests", RunStatus.RUNNING, RunStrategy.EXPLORE_BUNDLE, current_phase=PhaseName.EXPLORE_BUNDLE)
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

    def test_request_profile_requires_string_lists_without_duplicates(self) -> None:
        profile = request_profile()
        profile["gatherers"] = ["code", "code"]

        with self.assertRaises(ExploreValidationError):
            validate_request_profile(profile)


if __name__ == "__main__":
    unittest.main()
