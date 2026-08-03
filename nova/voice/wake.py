from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from nova.voice.conversation import ConversationVoice


class WakePhraseSession:
    def __init__(
        self,
        voice: ConversationVoice,
        handle_message: Callable[[str], dict[str, Any]],
        wake_phrase: str = "Nova",
    ) -> None:
        self.voice = voice
        self.handle_message = handle_message
        self.wake_phrase = self.normalize(wake_phrase) or "nova"

    @staticmethod
    def normalize(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

    def request_after_wake_phrase(self, transcript: str) -> str | None:
        words = list(re.finditer(r"[A-Za-z0-9]+", transcript))
        wake_words = self.wake_phrase.split()
        heard = [match.group(0).lower() for match in words[:len(wake_words)]]
        if heard != wake_words:
            return None
        end = words[len(wake_words) - 1].end()
        return transcript[end:].lstrip(" \t,.;:!?-")

    def is_sleep_phrase(self, transcript: str) -> bool:
        normalized = self.normalize(transcript)
        return normalized in {
            f"{self.wake_phrase} stop",
            f"{self.wake_phrase} go to sleep",
            f"{self.wake_phrase} sleep",
        }

    @staticmethod
    def is_silence_error(message: str) -> bool:
        lowered = message.lower()
        return "no speech" in lowered or "no transcript" in lowered

    def run(
        self,
        *,
        on_activation: Callable[[str], None],
        on_transcript: Callable[[str], None],
        on_response: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> str:
        armed = False
        awaiting_confirmation = False
        while True:
            try:
                transcript = self.voice.listen()
            except KeyboardInterrupt:
                return "interrupted"
            except (OSError, RuntimeError, ValueError) as exc:
                if not self.is_silence_error(str(exc)):
                    on_error(str(exc))
                continue

            if self.is_sleep_phrase(transcript):
                self._speak("Wake phrase mode stopped.", on_error)
                return "spoken_stop"

            if awaiting_confirmation or armed:
                request = transcript
                armed = False
            else:
                request = self.request_after_wake_phrase(transcript)
                if request is None:
                    continue
                on_activation(transcript)
                if not request:
                    self._speak("Yes?", on_error)
                    armed = True
                    continue

            on_transcript(request)
            try:
                result = self.handle_message(request)
                response = str(result["response"])
                spoken_response = str(result.get("spoken_response", response))
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                on_error(str(exc))
                awaiting_confirmation = False
                continue

            on_response(response)
            awaiting_confirmation = (
                result.get("action_status") == "pending_confirmation"
            )
            if not bool(self.voice.status()["auto_speak"]):
                self._speak(spoken_response, on_error)

    def _speak(self, text: str, on_error: Callable[[str], None]) -> None:
        try:
            self.voice.speak(text, force=True)
        except (OSError, RuntimeError, ValueError) as exc:
            on_error(f"Speech output failed: {exc}")
