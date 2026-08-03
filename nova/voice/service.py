from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Protocol

from nova.core.settings import SettingsManager
from nova.voice.native import MacOSSpeechInput


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
        data_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.output = output or MacOSSpeechOutput()
        command = settings.get("voice.input_command", [])
        self.input = speech_input
        self.command_input = CommandSpeechInput(
            command if isinstance(command, list) else []
        )
        self.native_input = MacOSSpeechInput(
            data_dir or settings.path.parent,
            locale=self._locale(),
            duration=self._duration(),
            recognition_mode=self._recognition_mode(),
        )

    def status(self) -> dict[str, Any]:
        provider = self._current_input()
        return {
            "enabled": bool(self.settings.get("voice.enabled", False)),
            "auto_speak": bool(self.settings.get("voice.auto_speak", False)),
            "output_available": self.output.available(),
            "input_available": provider.available(),
            "input_provider": self._provider_name(provider),
            "input_installed": (
                self.native_input.installed()
                if provider is self.native_input
                else None
            ),
            "locale": self._locale(),
            "listen_seconds": self._duration(),
            "recognition_mode": self._recognition_mode(),
            "wake_phrase": self._wake_phrase(),
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
        self.command_input.command = cleaned

    def set_locale(self, locale: str) -> None:
        cleaned = locale.strip()
        if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?", cleaned):
            raise ValueError("Voice locale must look like en-US or sv-SE.")
        self.settings.set("voice.locale", cleaned)
        self.native_input.locale = cleaned

    def set_duration(self, seconds: int) -> None:
        duration = min(20, max(2, int(seconds)))
        self.settings.set("voice.listen_seconds", duration)
        self.native_input.duration = duration

    def set_recognition_mode(self, mode: str) -> None:
        cleaned = mode.strip().lower()
        if cleaned not in {"on-device", "automatic"}:
            raise ValueError(
                "Recognition mode must be on-device or automatic."
            )
        self.settings.set("voice.recognition_mode", cleaned)
        self.native_input.recognition_mode = cleaned

    def set_wake_phrase(self, phrase: str) -> None:
        words = re.findall(r"[A-Za-z0-9]+", phrase)
        if not 1 <= len(words) <= 3:
            raise ValueError("Wake phrase must contain one to three words.")
        self.settings.set("voice.wake_phrase", " ".join(words))

    def setup_input(self) -> dict[str, Any]:
        self._refresh_inputs()
        return self.native_input.check()

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
        provider = self._current_input()
        if not provider.available():
            raise RuntimeError(
                "Microphone input is unavailable. Run voice-setup for details."
            )
        return provider.listen()

    def _refresh_inputs(self) -> None:
        command = self.settings.get("voice.input_command", [])
        self.command_input.command = command if isinstance(command, list) else []
        self.native_input.locale = self._locale()
        self.native_input.duration = self._duration()
        self.native_input.recognition_mode = self._recognition_mode()

    def _current_input(self) -> SpeechInput:
        self._refresh_inputs()
        if self.input is not None:
            return self.input
        if self.command_input.command:
            return self.command_input
        return self.native_input

    def _locale(self) -> str:
        configured = self.settings.get("voice.locale", "en-US")
        return str(configured or "en-US")

    def _duration(self) -> int:
        configured = self.settings.get("voice.listen_seconds", 7)
        try:
            return min(20, max(2, int(configured)))
        except (TypeError, ValueError):
            return 7

    def _recognition_mode(self) -> str:
        configured = str(
            self.settings.get("voice.recognition_mode", "on-device")
        ).lower()
        return configured if configured in {"on-device", "automatic"} else "on-device"

    def _wake_phrase(self) -> str:
        configured = str(self.settings.get("voice.wake_phrase", "Nova"))
        words = re.findall(r"[A-Za-z0-9]+", configured)
        return " ".join(words[:3]) if words else "Nova"

    def _provider_name(self, provider: SpeechInput) -> str:
        if provider is self.native_input:
            return f"macos-{self._recognition_mode()}"
        if provider is self.command_input:
            return "local-command"
        return "injected"

    def _rate(self) -> int:
        configured = self.settings.get("voice.rate", 190)
        try:
            return min(500, max(80, int(configured)))
        except (TypeError, ValueError):
            return 190
