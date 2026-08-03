import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nova.actions.service import (
    ActionRequest,
    ActionService,
    MacOSActionExecutor,
)
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

    def test_note_action_preserves_body_and_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))

            pending = service.process(
                "Create a note called Shopping saying Buy milk"
            )

            self.assertEqual(pending["action_status"], "pending_confirmation")
            self.assertEqual(pending["action"]["details"]["body"], "Buy milk")
            self.assertEqual(executor.requests, [])

            service.process("yes")

            self.assertEqual(executor.requests[0].kind, "create_note")
            self.assertEqual(executor.requests[0].target, "Shopping")

    def test_scheduled_reminder_parses_natural_language_time(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))

            pending = service.process(
                "Remind me to check Nova tomorrow at 9 am"
            )
            service.process("confirm")

            due_at = pending["action"]["details"]["due_at"]
            self.assertRegex(due_at, r"T09:00:00$")
            self.assertEqual(executor.requests[0].kind, "create_reminder")
            self.assertEqual(executor.requests[0].target, "check Nova")

    def test_calendar_event_parses_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))

            pending = service.process(
                "Create calendar event Nova demo tomorrow at 3 pm for 30 minutes"
            )
            service.process("do it")

            details = pending["action"]["details"]
            self.assertRegex(details["start_at"], r"T15:00:00$")
            self.assertEqual(details["duration_minutes"], "30")
            self.assertEqual(executor.requests[0].kind, "create_event")

    def test_invalid_or_past_scheduled_action_is_not_recognized(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _ = self.make_service(Path(directory))

            invalid = service.process(
                "Create calendar event Bad time tomorrow at 29 pm"
            )
            past = service.process(
                "Create calendar event Old event on 2000-01-01 at 9 am"
            )

            self.assertFalse(invalid["handled"])
            self.assertFalse(past["handled"])

    def test_file_action_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))

            pending = service.process("Open file ~/Documents/example.txt")
            service.process("yes")

            self.assertEqual(pending["action_status"], "pending_confirmation")
            self.assertEqual(executor.requests[0].kind, "open_path")

    def test_web_search_requires_website_permission_and_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))

            blocked = service.process("Search the web for Nova AI assistant")
            service.set_websites_enabled(True)
            pending = service.process("Search the web for Nova AI assistant")
            service.process("yes")

            self.assertEqual(blocked["action_status"], "blocked")
            self.assertEqual(pending["action_status"], "pending_confirmation")
            self.assertEqual(executor.requests[0].kind, "web_search")

    def test_disabling_websites_cancels_pending_web_search(self):
        with tempfile.TemporaryDirectory() as directory:
            service, executor = self.make_service(Path(directory))
            service.set_websites_enabled(True)
            service.process("Search the internet for Nova")

            service.set_websites_enabled(False)
            result = service.process("yes")

            self.assertFalse(result["handled"])
            self.assertEqual(executor.requests, [])

    @patch("nova.actions.service.subprocess.run")
    def test_note_executor_passes_user_text_as_osascript_arguments(
        self,
        run,
    ):
        malicious = 'Buy milk" & do shell script "touch /tmp/unsafe" & "'
        request = ActionRequest(
            "create_note",
            "Shopping",
            "create a note",
            (("body", malicious),),
        )

        MacOSActionExecutor().execute(request)

        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["/usr/bin/osascript", "-e"])
        self.assertNotIn(malicious, command[2])
        self.assertEqual(command[3:], ["--", "Shopping", malicious])

    @patch("nova.actions.service.subprocess.run")
    def test_path_executor_uses_open_argv_without_a_shell(self, run):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Nova document.txt"
            path.touch()

            MacOSActionExecutor().execute(
                ActionRequest("open_path", str(path), "open a file")
            )

            self.assertEqual(
                run.call_args.args[0],
                ["open", str(path.resolve())],
            )
            self.assertNotIn("shell", run.call_args.kwargs)

    @patch("nova.actions.service.subprocess.run")
    def test_web_search_executor_url_encodes_query(self, run):
        MacOSActionExecutor().execute(
            ActionRequest("web_search", "Nova AI & privacy", "search the web")
        )

        self.assertEqual(
            run.call_args.args[0],
            ["open", "https://duckduckgo.com/?q=Nova+AI+%26+privacy"],
        )

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
