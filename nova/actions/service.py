from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

from nova.core.settings import SettingsManager


@dataclass(frozen=True)
class ActionRequest:
    kind: str
    target: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "target": self.target,
            "description": self.description,
        }


class ActionExecutor(Protocol):
    def execute(self, request: ActionRequest) -> None: ...


class MacOSActionExecutor:
    """Execute narrowly allowlisted actions without invoking a shell."""

    def execute(self, request: ActionRequest) -> None:
        if request.kind == "open_app":
            command = ["open", "-a", request.target]
        elif request.kind == "open_url":
            command = ["open", request.target]
        else:
            raise ValueError(f"Unsupported action kind: {request.kind}")
        subprocess.run(command, check=True, timeout=15)


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
            and self._pending.kind == "open_url"
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
            request.kind == "open_url"
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
        return f"opened {request.target}"

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
