from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.models import Complexity, Mode, RunState, Strategy, Task, TaskStatus
from ai_harness.pipeline.tdd_loop import ImplementationOutcome, TaskPlan, TddLoop
from ai_harness.stores.state import StateStore


APPROVE = "# Review v1\n## Verdict\nAPPROVE\n## Findings\nNone.\n"


class TddLoopIntegrationTests(unittest.TestCase):
    def make_store(self, repository: Path) -> StateStore:
        store = StateStore(repository)
        store.save(RunState(
            run_id="run", user_input="implement", current_phase="TDD_LOOP",
            strategy=Strategy.SDD, mode=Mode.CODE,
            intent="modify_code", complexity=Complexity.LOW, selected_provider="local",
            tasks=[Task("T1", "Task")],
        ))
        return store

    def test_real_controller_commands_capture_evidence_and_gate_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            store = self.make_store(repository)
            reviewed = []
            plan = TaskPlan("T1", ((sys.executable, "-c", "print('focused')"),),
                            ((sys.executable, "-c", "print('broader')"),))
            loop = TddLoop(repository, store, [plan],
                           lambda *args: ImplementationOutcome(("module.py",), "changed"),
                           lambda *args: reviewed.append(args) or APPROVE)
            result = loop.run_one()
            evidence = store.artifacts.read_json("attempts/T1/1.json")["test_evidence"]
            self.assertEqual(TaskStatus.COMPLETED, result.status)
            self.assertEqual(2, len(evidence))
            self.assertIn("focused", evidence[0]["stdout"])
            self.assertIn("broader", evidence[1]["stdout"])
            self.assertEqual(1, len(reviewed))

    def test_missing_required_executable_fails_without_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            store = self.make_store(repository)
            reviews = []
            loop = TddLoop(repository, store,
                           [TaskPlan("T1", (("definitely-not-a-real-executable",),))],
                           lambda *args: ImplementationOutcome(("module.py",)),
                           lambda *args: reviews.append(args) or APPROVE,
                           max_attempts=1)
            result = loop.run_one()
            evidence = store.artifacts.read_json("attempts/T1/1.json")["test_evidence"][0]
            self.assertEqual(TaskStatus.FAILED, result.status)
            self.assertTrue(evidence["missing"])
            self.assertEqual([], reviews)

    def test_real_repository_change_is_reviewed_instead_of_worker_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            store = self.make_store(repository)
            reviewed = []

            def implement(*args):
                del args
                (repository / "actual.py").write_text("answer = 42\n", encoding="utf-8")
                return ImplementationOutcome(("claimed.py",), "claimed summary")

            loop = TddLoop(repository, store,
                           [TaskPlan("T1", ((sys.executable, "-c", "pass"),))],
                           implement, lambda *args: reviewed.append(args) or APPROVE)
            self.assertEqual(TaskStatus.COMPLETED, loop.run_one().status)
            outcome = reviewed[0][1]
            self.assertEqual(("actual.py",), outcome.changed_paths)
            self.assertIn("A actual.py", outcome.repository_diff)
            self.assertNotIn("claimed summary", outcome.repository_diff)


if __name__ == "__main__":
    unittest.main()
