import tempfile
import unittest
from pathlib import Path

from nova.app import NovaApplication


class TaskServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = NovaApplication(base_dir=Path(self.directory.name))
        self.app.start()

    def tearDown(self):
        self.app.stop()
        self.directory.cleanup()

    def test_task_lifecycle_is_persistent(self):
        task = self.app.tasks.create(
            "Design a phone stand",
            project="3D Studio",
            priority=3,
        )
        self.assertEqual(task["status"], "open")

        started = self.app.tasks.set_status(task["id"], "in_progress")
        self.assertEqual(started["status"], "in_progress")
        self.assertEqual(self.app.tasks.list()[0]["project"], "3D Studio")

        self.app.stop()
        self.app.start()
        completed = self.app.tasks.set_status(task["id"], "completed")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(self.app.tasks.list(), [])
        self.assertEqual(len(self.app.tasks.list(include_finished=True)), 1)

    def test_natural_language_task_commands_are_deterministic(self):
        created = self.app.handle_message("Add a task to calibrate the printer")
        self.assertEqual(created["intent"], "task_created")
        task_id = created["task"]["id"]

        listed = self.app.handle_message("show my tasks")
        self.assertEqual(listed["intent"], "task_list")
        self.assertIn("calibrate the printer", listed["response"])

        completed = self.app.handle_message(f"complete task {task_id}")
        self.assertEqual(completed["task"]["status"], "completed")

    def test_invalid_task_data_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "title"):
            self.app.tasks.create("   ")
        with self.assertRaisesRegex(ValueError, "status"):
            task = self.app.tasks.create("Safe task")
            self.app.tasks.set_status(task["id"], "unknown")

    def test_application_status_counts_only_open_tasks(self):
        first = self.app.tasks.create("First")
        self.app.tasks.create("Second")
        self.app.tasks.set_status(first["id"], "completed")

        self.assertEqual(self.app.status()["open_tasks"], 1)


if __name__ == "__main__":
    unittest.main()
