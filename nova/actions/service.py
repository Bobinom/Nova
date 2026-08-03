from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote_plus, urlparse

from nova.core.settings import SettingsManager


@dataclass(frozen=True)
class ActionRequest:
    kind: str
    target: str
    description: str
    details: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "target": self.target,
            "description": self.description,
        }
        if self.details:
            result["details"] = dict(self.details)
        return result

    def detail(self, name: str, default: str = "") -> str:
        return dict(self.details).get(name, default)


class ActionExecutor(Protocol):
    def execute(self, request: ActionRequest) -> None: ...


class MacOSActionExecutor:
    """Execute narrowly parsed macOS actions without invoking a shell."""

    CREATE_NOTE_SCRIPT = """
on run argv
    set noteTitle to item 1 of argv
    set noteBody to item 2 of argv
    tell application "Notes"
        tell folder "Notes" of default account
            make new note with properties {name:noteTitle, body:noteBody}
        end tell
    end tell
end run
""".strip()

    CREATE_REMINDER_SCRIPT = """
on run argv
    set reminderTitle to item 1 of argv
    set dueSeconds to (item 2 of argv) as real
    tell application "Reminders"
        if dueSeconds < 0 then
            make new reminder with properties {name:reminderTitle}
        else
            set dueDate to (current date) + dueSeconds
            make new reminder with properties {name:reminderTitle, due date:dueDate}
        end if
    end tell
end run
""".strip()

    CREATE_EVENT_SCRIPT = """
on run argv
    set eventTitle to item 1 of argv
    set startSeconds to (item 2 of argv) as real
    set durationSeconds to (item 3 of argv) as real
    set startDate to (current date) + startSeconds
    set endDate to startDate + durationSeconds
    tell application "Calendar"
        tell calendar 1
            make new event with properties {summary:eventTitle, start date:startDate, end date:endDate}
        end tell
    end tell
end run
""".strip()

    def execute(self, request: ActionRequest) -> None:
        if request.kind == "open_app":
            command = ["open", "-a", request.target]
        elif request.kind == "open_url":
            command = ["open", request.target]
        elif request.kind == "open_path":
            path = Path(request.target).expanduser().resolve(strict=True)
            command = ["open", str(path)]
        elif request.kind == "web_search":
            command = [
                "open",
                f"https://duckduckgo.com/?q={quote_plus(request.target)}",
            ]
        elif request.kind == "create_note":
            self._run_osascript(
                self.CREATE_NOTE_SCRIPT,
                request.target,
                request.detail("body"),
            )
            return
        elif request.kind == "create_reminder":
            due_seconds = self._seconds_until(request.detail("due_at"))
            self._run_osascript(
                self.CREATE_REMINDER_SCRIPT,
                request.target,
                str(due_seconds),
            )
            return
        elif request.kind == "create_event":
            start_seconds = self._seconds_until(request.detail("start_at"))
            duration = int(request.detail("duration_minutes", "60")) * 60
            self._run_osascript(
                self.CREATE_EVENT_SCRIPT,
                request.target,
                str(max(0, start_seconds)),
                str(duration),
            )
            return
        else:
            raise ValueError(f"Unsupported action kind: {request.kind}")
        subprocess.run(command, check=True, timeout=15)

    @staticmethod
    def _run_osascript(script: str, *arguments: str) -> None:
        subprocess.run(
            ["/usr/bin/osascript", "-e", script, "--", *arguments],
            check=True,
            timeout=30,
        )

    @staticmethod
    def _seconds_until(value: str) -> int:
        if not value:
            return -1
        target = datetime.fromisoformat(value)
        return int((target - datetime.now()).total_seconds())


class ActionService:
    DEFAULT_APPS = {
        "calendar": "Calendar",
        "finder": "Finder",
        "mail": "Mail",
        "maps": "Maps",
        "messages": "Messages",
        "music": "Music",
        "notes": "Notes",
        "safari": "Safari",
        "system settings": "System Settings",
    }
    _CONFIRM = {"yes", "confirm", "do it", "go ahead"}
    _CANCEL = {"no", "cancel", "stop", "never mind", "nevermind"}
    _WEB_ACTIONS = {"open_url", "web_search"}

    def __init__(
        self,
        settings: SettingsManager,
        executor: ActionExecutor | None = None,
    ) -> None:
        self.settings = settings
        self.executor = executor or MacOSActionExecutor()
        self._pending: ActionRequest | None = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.settings.get("actions.enabled", False)),
            "allow_websites": bool(
                self.settings.get("actions.allow_websites", False)
            ),
            "allowed_apps": self._allowed_apps(),
            "supported_actions": [
                "open_app", "open_url", "open_path", "web_search",
                "create_note", "create_reminder", "create_event",
            ],
            "pending": self._pending.as_dict() if self._pending else None,
        }

    def set_enabled(self, enabled: bool) -> None:
        self.settings.set("actions.enabled", enabled)
        if not enabled:
            self.cancel_pending()

    def set_websites_enabled(self, enabled: bool) -> None:
        self.settings.set("actions.allow_websites", enabled)
        if (
            not enabled
            and self._pending is not None
            and self._pending.kind in self._WEB_ACTIONS
        ):
            self.cancel_pending()

    def process(self, text: str) -> dict[str, Any]:
        normalized = self._normalize(text)
        if self._pending is not None:
            if normalized in self._CONFIRM:
                request = self._pending
                self._pending = None
                try:
                    self.executor.execute(request)
                except (OSError, subprocess.SubprocessError, ValueError) as exc:
                    return self._result(
                        "failed",
                        f"I couldn't {request.description}: {exc}",
                        request,
                    )
                return self._result(
                    "completed",
                    f"Done. I {self._past_tense(request)}.",
                    request,
                )
            if normalized in self._CANCEL:
                request = self._pending
                self._pending = None
                return self._result("cancelled", "Action cancelled.", request)
            self._pending = None

        request = self._parse(text)
        if request is None:
            return {"handled": False}
        if not self.settings.get("actions.enabled", False):
            return self._result(
                "blocked",
                "Computer actions are disabled. Use actions-on to enable them.",
                request,
            )
        if (
            request.kind in self._WEB_ACTIONS
            and not self.settings.get("actions.allow_websites", False)
        ):
            return self._result(
                "blocked",
                "Website actions are disabled. Use action-websites on to enable them.",
                request,
            )
        self._pending = request
        return self._result(
            "pending_confirmation",
            f"Confirm action: {request.description}? Reply yes or no.",
            request,
        )

    def cancel_pending(self) -> None:
        self._pending = None

    def _parse(self, text: str) -> ActionRequest | None:
        for parser in (self._parse_note, self._parse_reminder, self._parse_event):
            request = parser(text)
            if request is not None:
                return request

        path_match = re.fullmatch(
            r"open\s+(?:the\s+)?(?:file|folder)\s+(.+)",
            text.strip(),
            re.I,
        )
        if path_match:
            target = path_match.group(1).strip().strip("\"'")
            if target and "\x00" not in target:
                return ActionRequest(
                    "open_path",
                    target,
                    f"open the path {self._short(target)}",
                )

        search_match = re.fullmatch(
            r"(?:search|look up)\s+(?:the\s+)?"
            r"(?:web|internet|safari)\s+for\s+(.+)",
            text.strip(),
            re.I,
        )
        if search_match:
            query = search_match.group(1).strip().rstrip(".?!")
            if query:
                return ActionRequest(
                    "web_search",
                    query,
                    f"search the web for {self._short(query)}",
                )

        normalized = self._normalize(text)
        app_match = re.fullmatch(r"(?:open|launch|start)\s+(.+)", normalized)
        if app_match:
            requested = app_match.group(1).removeprefix("the ")
            allowed = self._allowed_app_map()
            if requested in allowed:
                app = allowed[requested]
                return ActionRequest("open_app", app, f"open {app}")

        url_match = re.fullmatch(
            r"(?:open|visit|go to)\s+(?:the\s+)?(?:website\s+)?(\S+)",
            text.strip(),
            re.I,
        )
        if not url_match:
            return None
        target = url_match.group(1).rstrip(".!?,")
        if "://" not in target:
            target = f"https://{target}"
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        return ActionRequest("open_url", target, f"open {target}")

    def _parse_note(self, text: str) -> ActionRequest | None:
        match = re.fullmatch(
            r"(?:create|make)\s+(?:a\s+)?note"
            r"(?:\s+called\s+(.+?))?(?:\s+saying|:)\s*(.+)",
            text.strip(),
            re.I,
        )
        if match:
            title = (match.group(1) or "Nova Note").strip()
            body = match.group(2).strip()
        else:
            simple = re.fullmatch(
                r"(?:take|create|make)\s+(?:a\s+)?note\s+(.+)",
                text.strip(),
                re.I,
            )
            if not simple:
                return None
            body = re.sub(r"^that\s+", "", simple.group(1), flags=re.I).strip()
            title = self._short(body, 40)
        if not body or len(body) > 4000 or len(title) > 200:
            return None
        return ActionRequest(
            "create_note",
            title,
            f"create the note {self._short(title)}",
            (("body", body),),
        )

    def _parse_reminder(self, text: str) -> ActionRequest | None:
        match = re.fullmatch(
            r"remind me to\s+(.+?)(?:\s+((?:today|tomorrow|on\s+"
            r"\d{4}-\d{2}-\d{2})(?:\s+at\s+.+)?))?",
            text.strip(),
            re.I,
        )
        if not match:
            return None
        title = match.group(1).strip()
        when = match.group(2)
        due_at = self._parse_when(when) if when else ""
        if when and due_at is None:
            return None
        timing = f" for {when}" if when else ""
        return ActionRequest(
            "create_reminder",
            title,
            f"create a reminder to {self._short(title)}{timing}",
            (("due_at", due_at or ""),),
        )

    def _parse_event(self, text: str) -> ActionRequest | None:
        match = re.fullmatch(
            r"(?:create|add|schedule)\s+(?:a\s+)?(?:calendar\s+)?event\s+"
            r"(?:called\s+)?(.+?)\s+"
            r"((?:today|tomorrow|on\s+\d{4}-\d{2}-\d{2})\s+at\s+.+?)"
            r"(?:\s+for\s+(\d+)\s+minutes?)?",
            text.strip(),
            re.I,
        )
        if not match:
            return None
        title = match.group(1).strip()
        when = match.group(2).strip()
        start_at = self._parse_when(when)
        duration = int(match.group(3) or "60")
        if start_at is None or not 5 <= duration <= 1440:
            return None
        return ActionRequest(
            "create_event",
            title,
            (
                f"create the calendar event {self._short(title)} "
                f"{when} for {duration} minutes"
            ),
            (
                ("start_at", start_at),
                ("duration_minutes", str(duration)),
            ),
        )

    @staticmethod
    def _parse_when(value: str | None) -> str | None:
        if not value:
            return None
        match = re.fullmatch(
            r"(today|tomorrow|on\s+(\d{4}-\d{2}-\d{2}))"
            r"(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?",
            value.strip(),
            re.I,
        )
        if not match:
            return None
        day, date_value, hour_value, minute_value, meridiem = match.groups()
        now = datetime.now()
        if day.lower() == "today":
            target = now
        elif day.lower() == "tomorrow":
            target = now + timedelta(days=1)
        else:
            target = datetime.strptime(str(date_value), "%Y-%m-%d")
        hour = int(hour_value or "9")
        minute = int(minute_value or "0")
        if meridiem:
            if not 1 <= hour <= 12:
                return None
            hour %= 12
            if meridiem.lower() == "pm":
                hour += 12
        if hour > 23 or minute > 59:
            return None
        scheduled = target.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if scheduled <= now:
            return None
        return scheduled.isoformat()

    def _allowed_apps(self) -> list[str]:
        configured = self.settings.get("actions.allowed_apps", None)
        if not isinstance(configured, list):
            return sorted(self.DEFAULT_APPS.values())
        return sorted(
            app.strip()
            for app in configured
            if isinstance(app, str) and app.strip()
        )

    def _allowed_app_map(self) -> dict[str, str]:
        return {self._normalize(app): app for app in self._allowed_apps()}

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.casefold().strip(" \t\r\n.!?"))

    @staticmethod
    def _past_tense(request: ActionRequest) -> str:
        if request.kind == "open_app":
            return f"opened {request.target}"
        if request.kind in {"open_url", "open_path"}:
            return f"opened {request.target}"
        if request.kind == "web_search":
            return f"searched the web for {request.target}"
        if request.kind == "create_note":
            return f"created the note {request.target}"
        if request.kind == "create_reminder":
            return f"created the reminder {request.target}"
        if request.kind == "create_event":
            return f"created the calendar event {request.target}"
        return f"completed {request.description}"

    @staticmethod
    def _short(value: str, limit: int = 80) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        return cleaned if len(cleaned) <= limit else cleaned[:limit - 1] + "…"

    @staticmethod
    def _result(
        status: str,
        response: str,
        request: ActionRequest,
    ) -> dict[str, Any]:
        return {
            "handled": True,
            "intent": "computer_action",
            "action_status": status,
            "action": request.as_dict(),
            "response": response,
        }
