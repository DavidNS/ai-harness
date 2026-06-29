from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ai_harness.control_outputs import ControlFlowSignal, ImpossibleOutcome, PhaseEscalation
from ai_harness.errors import ValidationError
from ai_harness.models import Complexity, Mode, RunState, Strategy, Task, TaskStatus
from ai_harness.pipeline.tdd_loop import (
    CommandEvidence,
    ImplementationOutcome,
    TaskPlan,
    TddLoop,
)
from ai_harness.stores.state import StateStore


APPROVE = "# Review v1\n## Verdict\nAPPROVE\n## Findings\nNone.\n"
CHANGES = "# Review v1\n## Verdict\nREQUEST_CHANGES\n## Findings\nFix it.\n"


class TddLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name)
        self.store = StateStore(self.repository)
        self.store.save(RunState(
            run_id="run", user_input="change it", current_phase="TDD_LOOP",
            strategy=Strategy.SDD, mode=Mode.CODE,
            intent="modify_code", complexity=Complexity.LOW, selected_provider="local",
            tasks=[Task("T1", "First"), Task("T2", "Second", ("T1",))],
        ))

    @staticmethod
    def passed(command, cwd, timeout):
        del cwd, timeout
        return CommandEvidence(command, "ok", "", 0, 0.01)

    def loop(self, implement, review=lambda *args: APPROVE, **kwargs):
        return TddLoop(
            self.repository, self.store,
            [TaskPlan("T1", (("focused",),), (("broader",),)),
             TaskPlan("T2", (("focused-2",),))],
            implement, review, command_runner=kwargs.pop("command_runner", self.passed), **kwargs,
        )

    def test_attempt_is_persisted_before_focused_then_broader_tests(self) -> None:
        calls = []

        def runner(command, cwd, timeout):
            del cwd, timeout
            calls.append(command)
            attempt = self.store.artifacts.read_json("attempts/T1/1.json")
            self.assertEqual("implemented", attempt["status"])
            self.assertEqual(1, self.store.load().tasks[0].attempts)
            return CommandEvidence(command, "", "", 0, 0)

        result = self.loop(lambda *args: ImplementationOutcome(("src/a.py",)), command_runner=runner).run_one()
        self.assertEqual([("focused",), ("broader",)], calls)
        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual(TaskStatus.COMPLETED, self.store.load().tasks[0].status)
        self.assertEqual(TaskStatus.PENDING, self.store.load().tasks[1].status)

    def test_failed_focused_test_skips_broader_and_review(self) -> None:
        calls = []
        reviews = []

        def runner(command, cwd, timeout):
            del cwd, timeout
            calls.append(command)
            return CommandEvidence(command, "", "failure", 1, 0)

        result = self.loop(
            lambda *args: ImplementationOutcome(("a.py",)),
            lambda *args: reviews.append(args) or APPROVE,
            command_runner=runner, max_attempts=1,
        ).run_one()
        self.assertEqual([("focused",)], calls)
        self.assertEqual([], reviews)
        self.assertEqual(TaskStatus.FAILED, result.status)

    def test_request_changes_retries_with_failure_context_then_approves(self) -> None:
        attempts = []
        reviewed = self.repository / "reviewed.py"
        reviews = iter((CHANGES, APPROVE))

        def implement(task, attempt, failures):
            attempts.append((task.id, attempt, failures))
            if attempt == 2:
                self.assertFalse(reviewed.exists())
            reviewed.write_text(f"attempt = {attempt}\n", encoding="utf-8")
            return ImplementationOutcome(("reviewed.py",))

        result = self.loop(implement, lambda *args: next(reviews)).run_one()
        self.assertEqual(2, result.attempts)
        self.assertEqual((), attempts[0][2])
        self.assertEqual(1, len(attempts[1][2]))
        self.assertIn("review requested changes", attempts[1][2][0])
        self.assertIn("Fix it.", attempts[1][2][0])
        first = self.store.artifacts.read_json("attempts/T1/1.json")
        self.assertEqual(CHANGES, first["review"])
        self.assertIn("review requested changes", first["failure"])
        self.assertIn("Fix it.", first["failure"])
        self.assertEqual(["reviewed.py"], first["implementation"]["changed_paths"])
        self.assertIn("+attempt = 1", first["implementation"]["repository_diff"])
        self.assertEqual("completed", self.store.artifacts.read_json("attempts/T1/2.json")["status"])
        self.assertEqual("attempt = 2\n", reviewed.read_text(encoding="utf-8"))

    def test_request_changes_multiline_findings_are_retry_feedback(self) -> None:
        attempts = []
        reviews = iter((
            "# Review v1\n## Verdict\nREQUEST_CHANGES\n## Findings\n- Fix docs/explorer/improvements/a/improvement.md.\n- Add focused coverage.\n",
            APPROVE,
        ))

        def implement(task, attempt, failures):
            del task
            attempts.append((attempt, failures))
            (self.repository / "reviewed.py").write_text(f"attempt = {attempt}\n", encoding="utf-8")
            return ImplementationOutcome(("reviewed.py",))

        result = self.loop(implement, lambda *args: next(reviews)).run_one()

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        retry_feedback = attempts[1][1][0]
        self.assertIn("review requested changes", retry_feedback)
        self.assertIn("docs/explorer/improvements/a/improvement.md", retry_feedback)
        self.assertIn("Add focused coverage.", retry_feedback)
        self.assertNotIn("## Findings", retry_feedback)
        self.assertNotIn("## Verdict", retry_feedback)

    def test_accepts_retry_ceiling_of_ten_and_records_attempt_ten(self) -> None:
        attempts = []
        progress = []

        def implement(task, attempt, failures):
            del task, failures
            attempts.append(attempt)
            (self.repository / "retry.py").write_text(f"attempt = {attempt}\n", encoding="utf-8")
            return ImplementationOutcome(("retry.py",), exit_code=1)

        result = self.loop(implement, max_attempts=10, progress=progress.append).run_one()

        self.assertEqual(list(range(1, 11)), attempts)
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual(10, result.attempts)
        tenth = self.store.artifacts.read_json("attempts/T1/10.json")
        self.assertEqual(10, tenth["attempt"])
        self.assertEqual("failed", tenth["status"])
        self.assertIn("Task T1 attempt 10/10: implement", progress)

    def test_rejects_tdd_loop_attempts_above_controller_limit(self) -> None:
        with self.assertRaisesRegex(ValidationError, "one and ten"):
            self.loop(lambda *args: ImplementationOutcome(("a.py",)), max_attempts=11)

    def test_rejects_tdd_loop_boolean_max_attempts(self) -> None:
        for value in (False, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "one and ten"):
                    self.loop(lambda *args: ImplementationOutcome(("a.py",)), max_attempts=value)

    def test_review_control_signal_restores_attempt_changes(self) -> None:
        created = self.repository / "created.py"

        def implement(*args):
            del args
            created.write_text("partial\n", encoding="utf-8")
            return ImplementationOutcome(("created.py",))

        def review(*args):
            del args
            raise ControlFlowSignal(ImpossibleOutcome(
                "REVIEW",
                "The implementation cannot be reviewed without a user decision.",
                ("The supplied evidence exposes an unresolved product choice.",),
            ))

        with self.assertRaises(ControlFlowSignal):
            self.loop(implement, review).run_one()
        self.assertFalse(created.exists())

    def test_invalid_review_fails_closed_and_exhausts_three_attempts(self) -> None:
        invoked = []
        result = self.loop(
            lambda task, attempt, failures: invoked.append(attempt) or ImplementationOutcome(("a.py",)),
            lambda *args: "LGTM",
        ).run_one()
        self.assertEqual([1, 2, 3], invoked)
        self.assertEqual(3, result.attempts)
        self.assertEqual(TaskStatus.FAILED, result.status)

    def test_review_worker_exception_is_recorded_and_retried(self) -> None:
        invoked = []
        reviews = []

        def implement(task, attempt, failures):
            del task
            invoked.append((attempt, failures))
            return ImplementationOutcome(("a.py",))

        def review(*args):
            reviews.append(args)
            if len(reviews) == 1:
                raise RuntimeError("review provider returned malformed output")
            return APPROVE

        result = self.loop(implement, review, max_attempts=2).run_one()

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual(2, result.attempts)
        self.assertIn("review worker raised RuntimeError", invoked[1][1][0])
        first = self.store.artifacts.read_json("attempts/T1/1.json")
        self.assertEqual("failed", first["status"])
        self.assertIn("review provider returned malformed output", first["failure"])
        self.assertEqual("completed", self.store.artifacts.read_json("attempts/T1/2.json")["status"])

    def test_outside_changed_path_is_rejected_before_tests(self) -> None:
        commands = []
        outside = self.repository.parent / "outside.py"
        result = self.loop(
            lambda *args: ImplementationOutcome((str(outside),)),
            command_runner=lambda *args: commands.append(args) or self.passed(*args),
            max_attempts=1,
        ).run_one()
        self.assertEqual([], commands)
        self.assertEqual(TaskStatus.FAILED, result.status)
        attempt = self.store.artifacts.read_json("attempts/T1/1.json")
        self.assertIn("outside target repository", attempt["failure"])

    def test_run_processes_exactly_one_ready_task(self) -> None:
        loop = self.loop(lambda *args: ImplementationOutcome(("a.py",)))
        self.assertEqual("T1", loop.run_one().task_id)
        state = self.store.load()
        self.assertEqual([TaskStatus.COMPLETED, TaskStatus.PENDING], [task.status for task in state.tasks])

    def test_controller_captures_untracked_change_and_sends_diff_to_review(self) -> None:
        reviews = []

        def implement(*args):
            del args
            (self.repository / "created.py").write_text("value = 1\n", encoding="utf-8")
            return ImplementationOutcome(("worker-claim.py",), "worker summary")

        result = self.loop(implement, lambda *args: reviews.append(args) or APPROVE).run_one()
        outcome = reviews[0][1]
        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual(("created.py",), outcome.changed_paths)
        self.assertIn("A created.py", outcome.repository_diff)
        self.assertIn("+value = 1", outcome.repository_diff)
        attempt = self.store.artifacts.read_json("attempts/T1/1.json")
        self.assertEqual(["created.py"], attempt["implementation"]["changed_paths"])
        self.assertEqual(outcome.repository_diff, attempt["implementation"]["repository_diff"])

    def test_preexisting_dirty_content_is_not_attributed_to_attempt(self) -> None:
        (self.repository / "dirty.py").write_text("already changed\n", encoding="utf-8")

        def implement(*args):
            del args
            (self.repository / "new.py").write_text("new\n", encoding="utf-8")
            return ImplementationOutcome(("new.py",))

        reviewed = []
        self.loop(implement, lambda *args: reviewed.append(args) or APPROVE).run_one()
        self.assertEqual(("new.py",), reviewed[0][1].changed_paths)
        self.assertNotIn("dirty.py", reviewed[0][1].repository_diff)

    def test_generated_cache_changes_are_ignored_for_scope_validation(self) -> None:
        reviews = []

        def implement(*args):
            del args
            (self.repository / "src").mkdir()
            (self.repository / "src" / "allowed.py").write_text("value = 1\n", encoding="utf-8")
            (self.repository / ".pytest_cache" / "v" / "cache").mkdir(parents=True)
            (self.repository / ".pytest_cache" / "v" / "cache" / "nodeids").write_text("[]\n", encoding="utf-8")
            (self.repository / "src" / "__pycache__").mkdir()
            (self.repository / "src" / "__pycache__" / "allowed.cpython-312.pyc").write_bytes(b"cache")
            return ImplementationOutcome(("src/allowed.py",))

        loop = TddLoop(
            self.repository,
            self.store,
            [TaskPlan("T1", (("focused",),), allowed_paths=("src/allowed.py",)),
             TaskPlan("T2", (("focused-2",),))],
            implement,
            lambda *args: reviews.append(args) or APPROVE,
            command_runner=self.passed,
            max_attempts=1,
        )
        result = loop.run_one()

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        attempt = self.store.artifacts.read_json("attempts/T1/1.json")
        self.assertEqual(["src/allowed.py"], attempt["implementation"]["changed_paths"])
        self.assertNotIn("pytest_cache", attempt["implementation"]["repository_diff"])
        self.assertNotIn("__pycache__", attempt["implementation"]["repository_diff"])
        self.assertEqual(("src/allowed.py",), reviews[0][1].changed_paths)

    def test_observed_change_outside_task_scope_is_rejected(self) -> None:
        commands = []
        attempts = []

        def implement(task, attempt, failures):
            del task
            attempts.append((attempt, failures))
            (self.repository / "outside.py").write_text("changed\n", encoding="utf-8")
            return ImplementationOutcome(("src/allowed.py",))

        loop = TddLoop(self.repository, self.store,
                       [TaskPlan("T1", (("focused",),), allowed_paths=("src",)),
                        TaskPlan("T2", (("focused-2",),))],
                       implement, lambda *args: APPROVE,
                       command_runner=lambda *args: commands.append(args) or self.passed(*args),
                       max_attempts=1)
        result = loop.run_one()
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual([], commands)
        self.assertEqual(1, len(attempts))
        attempt = self.store.artifacts.read_json("attempts/T1/1.json")
        self.assertIn("hard task-scope violation", attempt["failure"])
        self.assertIn("outside.py", attempt["failure"])
        self.assertIn("Allowed paths for this task are: src", attempt["failure"])
        self.assertFalse((self.repository / "outside.py").exists())

    def test_repeated_observed_scope_violation_escalates_to_tasks(self) -> None:
        state = self.store.load()
        state.strategy = Strategy.SDD
        self.store.save(state)
        commands = []
        attempts = []

        def implement(task, attempt, failures):
            del task
            attempts.append((attempt, failures))
            (self.repository / "outside.py").write_text(f"attempt {attempt}\n", encoding="utf-8")
            return ImplementationOutcome(("src/allowed.py",))

        loop = TddLoop(self.repository, self.store,
                       [TaskPlan("T1", (("focused",),), allowed_paths=("src",)),
                        TaskPlan("T2", (("focused-2",),))],
                       implement, lambda *args: APPROVE,
                       command_runner=lambda *args: commands.append(args) or self.passed(*args),
                       max_attempts=3)

        with self.assertRaises(ControlFlowSignal) as raised:
            loop.run_one()

        self.assertIsInstance(raised.exception.output, PhaseEscalation)
        escalation = raised.exception.output
        self.assertEqual("IMPLEMENT", escalation.origin_phase)
        self.assertEqual("SIMPLE_TASK", escalation.target_phase)
        self.assertIn("repeatedly changed", escalation.reason)
        self.assertIn("outside.py", escalation.reason)
        self.assertEqual([], commands)
        self.assertEqual(2, len(attempts))
        self.assertEqual((), attempts[0][1])
        self.assertIn("hard task-scope violation", attempts[1][1][0])
        self.assertFalse((self.repository / "outside.py").exists())
        first = self.store.artifacts.read_json("attempts/T1/1.json")
        second = self.store.artifacts.read_json("attempts/T1/2.json")
        self.assertEqual("failed", first["status"])
        self.assertEqual("failed", second["status"])
        self.assertIn("outside.py", second["failure"])

    def test_worker_exception_still_captures_and_rejects_observed_change(self) -> None:
        commands = []
        dirty = self.repository / "dirty.py"
        dirty.write_text("keep\n", encoding="utf-8")

        def implement(*args):
            del args
            (self.repository / "outside.py").write_text("changed\n", encoding="utf-8")
            raise RuntimeError("provider failed after editing")

        loop = TddLoop(
            self.repository,
            self.store,
            [
                TaskPlan("T1", (("focused",),), allowed_paths=("src",)),
                TaskPlan("T2", (("focused-2",),)),
            ],
            implement,
            lambda *args: APPROVE,
            command_runner=lambda *args: commands.append(args) or self.passed(*args),
            max_attempts=1,
        )
        result = loop.run_one()

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual(1, result.attempts)
        self.assertEqual([], commands)
        attempt = self.store.artifacts.read_json("attempts/T1/1.json")
        self.assertEqual("failed", attempt["status"])
        self.assertEqual(["outside.py"], attempt["implementation"]["changed_paths"])
        self.assertIn("A outside.py", attempt["implementation"]["repository_diff"])
        self.assertIn("outside task scope", attempt["failure"])
        self.assertIn("RuntimeError", attempt["implementation"]["stderr"])
        self.assertFalse((self.repository / "outside.py").exists())
        self.assertEqual("keep\n", dirty.read_text(encoding="utf-8"))
        self.assertEqual(1, self.store.load().tasks[0].attempts)

    def test_failed_attempt_restores_empty_directory_state(self) -> None:
        original = self.repository / "empty"
        original.mkdir()
        created = self.repository / "created-empty"

        def implement(*args):
            del args
            original.rmdir()
            created.mkdir()
            raise RuntimeError("provider failed after changing empty directories")

        result = self.loop(implement, max_attempts=1).run_one()

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertTrue(original.is_dir())
        self.assertFalse(created.exists())

    def test_failed_attempt_restores_file_replaced_by_directory(self) -> None:
        original = self.repository / "node"
        original.write_text("original\n", encoding="utf-8")

        def implement(*args):
            del args
            original.unlink()
            original.mkdir()
            (original / "child.py").write_text("partial\n", encoding="utf-8")
            raise RuntimeError("provider timed out after changing path kind")

        result = self.loop(implement, max_attempts=1).run_one()

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertTrue(original.is_file())
        self.assertEqual("original\n", original.read_text(encoding="utf-8"))
        attempt = self.store.artifacts.read_json("attempts/T1/1.json")
        self.assertEqual("failed", attempt["status"])
        self.assertIn("D node", attempt["implementation"]["repository_diff"])
        self.assertIn("A node/child.py", attempt["implementation"]["repository_diff"])

    def test_worker_exception_is_persisted_and_retry_is_bounded(self) -> None:
        calls = []

        def implement(task, attempt, failures):
            del task
            calls.append((attempt, failures))
            if attempt == 1:
                (self.repository / "src").mkdir()
                (self.repository / "src" / "allowed.py").write_text(
                    "value = 1\n", encoding="utf-8"
                )
                raise RuntimeError("malformed provider output")
            self.assertFalse((self.repository / "src" / "allowed.py").exists())
            (self.repository / "src").mkdir(exist_ok=True)
            (self.repository / "src" / "allowed.py").write_text(
                "value = 2\n", encoding="utf-8"
            )
            return ImplementationOutcome(("src/allowed.py",))

        loop = TddLoop(
            self.repository,
            self.store,
            [
                TaskPlan("T1", (("focused",),), allowed_paths=("src",)),
                TaskPlan("T2", (("focused-2",),)),
            ],
            implement,
            lambda *args: APPROVE,
            command_runner=self.passed,
            max_attempts=2,
        )
        result = loop.run_one()

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual(2, result.attempts)
        self.assertEqual(1, len(calls[1][1]))
        self.assertIn("implementation worker raised RuntimeError", calls[1][1][0])
        first = self.store.artifacts.read_json("attempts/T1/1.json")
        self.assertEqual("failed", first["status"])
        self.assertEqual(["src/allowed.py"], first["implementation"]["changed_paths"])
        self.assertIn("malformed provider output", first["failure"])
        self.assertEqual(
            "completed",
            self.store.artifacts.read_json("attempts/T1/2.json")["status"],
        )
        self.assertEqual(
            "value = 2\n",
            (self.repository / "src" / "allowed.py").read_text(encoding="utf-8"),
        )
        self.assertEqual(2, self.store.load().tasks[0].attempts)

    def test_in_progress_task_resumes_at_next_attempt(self) -> None:
        state = self.store.load()
        state.tasks[0] = replace(state.tasks[0], status=TaskStatus.IN_PROGRESS, attempts=1)
        self.store.save(state)
        calls = []

        def implement(task, attempt, failures):
            calls.append((task.id, attempt, failures))
            return ImplementationOutcome(("a.py",))

        result = self.loop(implement).run_one()
        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual(2, result.attempts)
        self.assertEqual(("T1", 2, ("resuming interrupted task after attempt 1",)), calls[0])

    def test_exhausted_in_progress_task_fails_without_another_attempt(self) -> None:
        state = self.store.load()
        state.tasks[0] = replace(state.tasks[0], status=TaskStatus.IN_PROGRESS, attempts=3)
        self.store.save(state)
        calls = []
        result = self.loop(lambda *args: calls.append(args) or ImplementationOutcome(("a.py",))).run_one()
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual(3, result.attempts)
        self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
