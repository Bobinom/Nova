from __future__ import annotations

import shutil
import subprocess
from typing import Any, Protocol

from nova.core.settings import SettingsManager


class SpeechOutput(Protocol):
    def available(self) -> bool: ...
    def speak(self, text: str, *, voice: str | None, rate: int) -> None: ...


class SpeechInput(Protocol):
    def available(self) -> bool: ...
    def listen(self) -> str: ...


class MacOSSpeechOutput:
    def available(self) -> bool:
        return shutil.which("say") is not None

    def speak(self, text: str, *, voice: str | None, rate: int) -> None:
        if not self.available():
            raise RuntimeError("macOS speech output is unavailable.")
        command = ["say", "-r", str(rate)]
        if voice:
            command.extend(["-v", voice])
        try:
            subprocess.run(
                command,
                check=True,
                input=text,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Speech output failed: {exc}") from exc


class CommandSpeechInput:
    """Read one transcript from a configured local command's stdout."""

    def __init__(self, command: list[str] | None = None) -> None:
        self.command = command or []

    def available(self) -> bool:
        return bool(self.command and shutil.which(self.command[0]))

    def listen(self) -> str:
        if not self.available():
            raise RuntimeError(
                "No local microphone transcription command is configured."
            )
        try:
            completed = subprocess.run(
                self.command,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Microphone transcription failed: {exc}") from exc
        transcript = completed.stdout.strip()
        if not transcript:
            raise RuntimeError("The microphone command returned no transcript.")
        return transcript


class VoiceService:
    def __init__(
        self,
        settings: SettingsManager,
        output: SpeechOutput | None = None,
        speech_input: SpeechInput | None = None,
    ) -> None:
        self.settings = settings
        self.output = output or MacOSSpeechOutput()
        command = settings.get("voice.input_command", [])
        self.input = speech_input or CommandSpeechInput(
            command if isinstance(command, list) else []
        )

    def status(self) -> dict[str, Any]:
        self._refresh_command_input()
        return {
            "enabled": bool(self.settings.get("voice.enabled", False)),
            "auto_speak": bool(self.settings.get("voice.auto_speak", False)),
            "output_available": self.output.available(),
            "input_available": self.input.available(),
            "voice": self.settings.get("voice.name", None),
            "rate": self._rate(),
        }

    def set_enabled(self, enabled: bool) -> None:
        self.settings.set("voice.enabled", enabled)

    def set_auto_speak(self, enabled: bool) -> None:
        self.settings.set("voice.auto_speak", enabled)

    def set_input_command(self, command: list[str]) -> None:
        cleaned = [part for part in command if part]
        self.settings.set("voice.input_command", cleaned)
        self._refresh_command_input()

    def speak(self, text: str, *, force: bool = False) -> bool:
        if not force and not self.settings.get("voice.enabled", False):
            return False
        self.output.speak(
            text,
            voice=self.settings.get("voice.name", None),
            rate=self._rate(),
        )
        return True

    def speak_response(self, response: str) -> bool:
        if not self.settings.get("voice.auto_speak", False):
            return False
        return self.speak(response)

    def listen(self) -> str:
        if not self.settings.get("voice.enabled", False):
            raise RuntimeError("Voice mode is disabled. Use voice-on first.")
        self._refresh_command_input()
        return self.input.listen()

    def _refresh_command_input(self) -> None:
        if not isinstance(self.input, CommandSpeechInput):
            return
        command = self.settings.get("voice.input_command", [])
        self.input.command = command if isinstance(command, list) else []

    def _rate(self) -> int:
        configured = self.settings.get("voice.rate", 190)
        try:
            return min(500, max(80, int(configured)))
        except (TypeError, ValueError):
            return 190
