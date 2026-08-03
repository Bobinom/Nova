from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol

import requests

from nova.core.settings import SettingsManager
from nova.voice.native import MacOSSpeechInput


ELEVENLABS_DEFAULT_VOICE_ID = "GmM3ucvssIf0NWKHkiyc"
ELEVENLABS_DEFAULT_MODEL = "eleven_flash_v2_5"


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


class MacOSKeychain:
    """Store the ElevenLabs credential outside Nova's settings and database."""

    service = "com.bobinom.nova.elevenlabs"
    account = "api-key"

    def get(self) -> str | None:
        security = shutil.which("security")
        if security is None:
            return None
        try:
            completed = subprocess.run(
                [
                    security,
                    "find-generic-password",
                    "-s",
                    self.service,
                    "-a",
                    self.account,
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        value = completed.stdout.strip()
        return value if completed.returncode == 0 and value else None

    def set(self, value: str) -> None:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("An ElevenLabs API key is required.")
        security = shutil.which("security")
        if security is None:
            raise RuntimeError("macOS Keychain is unavailable.")
        try:
            subprocess.run(
                [
                    security,
                    "add-generic-password",
                    "-U",
                    "-s",
                    self.service,
                    "-a",
                    self.account,
                    "-w",
                    cleaned,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("Could not save the ElevenLabs key in Keychain.") from exc


class ElevenLabsSpeechOutput:
    def __init__(
        self,
        settings: SettingsManager,
        keychain: MacOSKeychain,
    ) -> None:
        self.settings = settings
        self.keychain = keychain

    def available(self) -> bool:
        return bool(
            shutil.which("afplay")
            and self.keychain.get()
            and self._voice_id()
        )

    def speak(self, text: str, *, voice: str | None, rate: int) -> None:
        del voice, rate
        api_key = self.keychain.get()
        if not api_key:
            raise RuntimeError("Add your ElevenLabs API key in Nova Settings.")
        player = shutil.which("afplay")
        if player is None:
            raise RuntimeError("macOS audio playback is unavailable.")
        voice_id = self._voice_id()
        try:
            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                params={"output_format": "mp3_44100_128"},
                headers={
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                    "xi-api-key": api_key,
                },
                json={
                    "text": text,
                    "model_id": str(
                        self.settings.get(
                            "voice.elevenlabs.model_id",
                            ELEVENLABS_DEFAULT_MODEL,
                        )
                    ),
                },
                timeout=45,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise RuntimeError("ElevenLabs took too long to respond.") from exc
        except requests.RequestException as exc:
            raise RuntimeError("ElevenLabs speech generation failed.") from exc

        if not response.content:
            raise RuntimeError("ElevenLabs returned empty audio.")
        audio_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="nova-elevenlabs-",
                suffix=".mp3",
                delete=False,
            ) as handle:
                handle.write(response.content)
                audio_path = Path(handle.name)
            subprocess.run(
                [player, str(audio_path)],
                check=True,
                capture_output=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("ElevenLabs audio playback failed.") from exc
        finally:
            if audio_path is not None:
                audio_path.unlink(missing_ok=True)

    def _voice_id(self) -> str:
        configured = self.settings.get(
            "voice.elevenlabs.voice_id",
            ELEVENLABS_DEFAULT_VOICE_ID,
        )
        return str(configured or ELEVENLABS_DEFAULT_VOICE_ID)


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
        keychain: MacOSKeychain | None = None,
    ) -> None:
        self.settings = settings
        self.output = output
        self.macos_output = MacOSSpeechOutput()
        self.keychain = keychain or MacOSKeychain()
        self.elevenlabs_output = ElevenLabsSpeechOutput(
            settings,
            self.keychain,
        )
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
        output = self._current_output()
        return {
            "enabled": bool(self.settings.get("voice.enabled", False)),
            "auto_speak": bool(self.settings.get("voice.auto_speak", False)),
            "output_available": output.available(),
            "output_provider": self._output_provider(),
            "elevenlabs_configured": bool(self.keychain.get()),
            "elevenlabs_voice_id": self._elevenlabs_voice_id(),
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

    def set_output_provider(self, provider: str) -> None:
        cleaned = provider.strip().lower()
        if cleaned not in {"macos", "elevenlabs"}:
            raise ValueError("Voice provider must be macos or elevenlabs.")
        self.settings.set("voice.output_provider", cleaned)

    def configure_elevenlabs(self, voice_id: str, api_key: str = "") -> None:
        cleaned = voice_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9]{10,64}", cleaned):
            raise ValueError("ElevenLabs Voice ID is invalid.")
        if api_key.strip():
            self.keychain.set(api_key)
        if not self.keychain.get():
            raise ValueError("An ElevenLabs API key is required.")
        self.settings.set("voice.elevenlabs.voice_id", cleaned)
        self.settings.set("voice.elevenlabs.model_id", ELEVENLABS_DEFAULT_MODEL)
        self.set_output_provider("elevenlabs")

    def test_output(self) -> dict[str, Any]:
        output = self._current_output()
        output.speak(
            "Hello, I'm Nova. Your custom voice is ready.",
            voice=self.settings.get("voice.name", None),
            rate=self._rate(),
        )
        return {"spoken": True, "provider": self._output_provider()}

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
        output = self._current_output()
        try:
            output.speak(
                text,
                voice=self.settings.get("voice.name", None),
                rate=self._rate(),
            )
        except RuntimeError:
            if output is self.elevenlabs_output and self.macos_output.available():
                self.macos_output.speak(
                    text,
                    voice=self.settings.get("voice.name", None),
                    rate=self._rate(),
                )
            else:
                raise
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

    def _current_output(self) -> SpeechOutput:
        if self.output is not None:
            return self.output
        if self._output_provider() == "elevenlabs":
            return self.elevenlabs_output
        return self.macos_output

    def _output_provider(self) -> str:
        if self.output is not None:
            return "injected"
        configured = str(
            self.settings.get("voice.output_provider", "macos")
        ).lower()
        return configured if configured in {"macos", "elevenlabs"} else "macos"

    def _elevenlabs_voice_id(self) -> str:
        configured = self.settings.get(
            "voice.elevenlabs.voice_id",
            ELEVENLABS_DEFAULT_VOICE_ID,
        )
        return str(configured or ELEVENLABS_DEFAULT_VOICE_ID)

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
