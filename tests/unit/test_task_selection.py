import unittest

from ai_harness.errors import ValidationError
from ai_harness.models import Task, TaskStatus, select_ready_task


class TaskSelectionTests(unittest.TestCase):
    def test_first_ready_task_is_stable(self):
        tasks = [Task("a", "A", status=TaskStatus.COMPLETED), Task("b", "B", ("a",)), Task("c", "C")]
        self.assertEqual(select_ready_task(tasks).id, "b")

    def test_rejects_multiple_in_progress_tasks(self):
        tasks = [Task("a", "A", status=TaskStatus.IN_PROGRESS), Task("b", "B", status=TaskStatus.IN_PROGRESS)]
        with self.assertRaises(ValidationError):
            select_ready_task(tasks)
