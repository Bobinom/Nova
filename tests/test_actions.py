import subprocess
import tempfile
import unittest
from pathlib import Path

from nova.actions.service import ActionRequest, ActionService
from nova.app import NovaApplication
from nova.core.settings import SettingsManager


class RecordingExecutor:
    def __init__(self, error: Exception | None = None) -> None:
        self.requests: list[ActionRequest] = []
        self.error = error

    def execute(self, request: ActionRequest) -> None:
        self.requests.append(request)
        if self.error is not None:
            raise self.error


class ActionServiceTests(unittest.TestCase):
    def make_service(
        self,
        root: Path,
        executor: RecordingExecutor | None = None,
    ) -> tuple[ActionService, RecordingExecutor]:
        settings = SettingsManager(root / "settings.json")
        settings.load()
        settings.set("actions.enabled", True)
        recording = executor or RecordingExecutor()
        return ActionService(settings, recording), recording

    def test_actions_are_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = SettingsManager(root / "settings.json")
            settings.load()
            service = ActionService(settings, RecordingExecutor())

            result = service.process("Open Safari")

            self.assertEqual(result["action_status"], "blocked")

    def test_app_action_requires_confirmation_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))

            pending = service.process("Open Safari")

            self.assertEqual(pending["action_status"], "pending_confirmation")
            self.assertEqual(executor.requests, [])

            completed = service.process("yes")

            self.assertEqual(completed["action_status"], "completed")
            self.assertEqual(executor.requests[0].target, "Safari")

    def test_action_can_be_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))
            service.process("Launch Notes")

            cancelled = service.process("no")

            self.assertEqual(cancelled["action_status"], "cancelled")
            self.assertEqual(executor.requests, [])

    def test_unrecognized_app_is_not_treated_as_an_action(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _ = self.make_service(Path(directory))

            self.assertEqual(service.process("Open Unknown Utility"), {
                "handled": False,
            })

    def test_website_actions_are_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))

            result = service.process("Visit example.com")

            self.assertEqual(result["action_status"], "blocked")
            self.assertEqual(executor.requests, [])

    def test_enabled_website_action_is_normalized_and_confirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))
            service.set_websites_enabled(True)

            pending = service.process("Open website example.com")
            completed = service.process("go ahead")

            self.assertEqual(pending["action"]["target"], "https://example.com")
            self.assertEqual(completed["action_status"], "completed")
            self.assertEqual(executor.requests[0].kind, "open_url")

    def test_executor_failure_is_reported_without_retrying(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = RecordingExecutor(subprocess.SubprocessError("failed"))
            service, _ = self.make_service(Path(directory), executor)
            service.process("Open Calendar")

            result = service.process("confirm")

            self.assertEqual(result["action_status"], "failed")
            self.assertEqual(len(executor.requests), 1)

    def test_disabling_actions_cancels_pending_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))
            service.process("Open Music")

            service.set_enabled(False)
            result = service.process("yes")

            self.assertFalse(result["handled"])
            self.assertEqual(executor.requests, [])

    def test_disabling_websites_cancels_pending_website(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))
            service.set_websites_enabled(True)
            service.process("Visit example.com")

            service.set_websites_enabled(False)
            result = service.process("yes")

            self.assertFalse(result["handled"])
            self.assertEqual(executor.requests, [])

    def test_application_routes_action_and_records_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            executor = RecordingExecutor()
            app.actions.executor = executor
            app.start()
            app.actions.set_enabled(True)

            pending = app.handle_message("Open Finder")
            completed = app.handle_message("yes")

            self.assertEqual(pending["action_status"], "pending_confirmation")
            self.assertEqual(completed["action_status"], "completed")
            self.assertEqual(executor.requests[0].target, "Finder")
            self.assertEqual(len(app.conversation.history()), 4)
            app.stop()

    def test_application_stop_cancels_pending_action(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            executor = RecordingExecutor()
            app.actions.executor = executor
            app.start()
            app.actions.set_enabled(True)
            app.handle_message("Open Finder")

            app.stop()
            app.start()
            result = app.handle_message("yes")

            self.assertNotEqual(result.get("action_status"), "completed")
            self.assertEqual(executor.requests, [])
            app.stop()


if __name__ == "__main__":
    unittest.main()
